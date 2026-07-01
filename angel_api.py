"""
Angel One SmartAPI data wrapper — the Upstox-free data layer for scanner_app.py.

Mirrors the shape of upstox_history.UpstoxHistory so the scan/scoring math in
scanner_app.py can stay almost identical: candle rows come back as
    [timestamp_str, open, high, low, close, volume, open_interest]
(oldest-first), and bulk_quotes() returns
    {token: {"last_price", "volume", "oi", "day_high", "day_low"}}.

Two Angel-One realities shape this module:

1. **getCandleData carries NO open interest** (Upstox candles did). We still emit a
   7th column so downstream code is unchanged, but it is 0 for equities/futures
   candles. Live OI instead comes from getMarketData("FULL") -> `opnInterest`
   (see bulk_quotes), and prior-day OI from oi_snapshot()/getCandleData is not
   available — callers degrade the OI-flow tag to neutral when OI is missing.

2. **Rate limits are tight**: getCandleData is 3 req/s AND ~180 req/min; the quote
   endpoint is a separate, roughly 1 req/s bucket. We pace candle calls across all
   worker threads (a shared min-interval gate) and back off on 403/429, exactly the
   pattern upstox_history uses for Cloudflare 1015 on the shared cloud IP.
"""
import logging
import random
import threading
import time

log = logging.getLogger("pyscan.angel")

# SmartConnect is optional at import time so `python -m py_compile` and the
# offline instrument dry-run work without the SDK installed. It is only actually
# needed when a live session is created.
try:
    from SmartApi import SmartConnect
except Exception:  # pragma: no cover - exercised only when the SDK is absent
    SmartConnect = None

# --- Rate-limit shaping (getCandleData: 3/s, ~180/min) --------------------------
# A hard floor of ~0.34s between ANY two candle requests keeps us under 3/s across
# every ThreadPoolExecutor worker. The per-minute cap (180) is respected by the
# caller budgeting how many symbols it fetches per refresh (top-N), not here.
_CANDLE_MIN_INTERVAL = 0.34
_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_BACKOFF = 1.0
_BACKOFF_CAP = 12.0

_pace_lock = threading.Lock()
_last_candle_at = [0.0]


def _pace_candle():
    """Serialize candle requests to <= 1 per _CANDLE_MIN_INTERVAL across threads."""
    with _pace_lock:
        now = time.monotonic()
        wait = _CANDLE_MIN_INTERVAL - (now - _last_candle_at[0])
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _last_candle_at[0] = now


def _is_throttled(resp) -> bool:
    """Angel returns errorcode 'AB1004'/message 'exceeding access rate' or a bare
    non-success dict when throttled. Treat any non-status success as retryable."""
    if not isinstance(resp, dict):
        return True
    msg = str(resp.get("message", "")).lower()
    return ("access rate" in msg) or (resp.get("errorcode") in ("AB1004", "AG8001"))


class AngelData:
    """Thin, thread-safe-enough wrapper over an authenticated SmartConnect client.

    `intraday_date` exists only for API symmetry with UpstoxHistory; Angel serves
    the current day through the same getCandleData endpoint, so no routing is
    needed. It is kept so scanner_app.py can share TESTING_MODE plumbing.
    """

    def __init__(self, smart_client, intraday_date: str | None = None):
        self.client = smart_client
        self.intraday_date = intraday_date

    # -- candle helpers ---------------------------------------------------------
    def _get_candles(self, exchange: str, token: str, interval: str,
                     from_dt: str, to_dt: str, label: str) -> list:
        """Return oldest-first [ts, o, h, l, c, v, oi(=0)] rows, [] on failure.

        `from_dt`/`to_dt` are 'YYYY-MM-DD HH:MM' (Angel's required format).
        """
        if self.client is None:
            return []
        params = {
            "exchange": exchange,
            "symboltoken": str(token),
            "interval": interval,
            "fromdate": from_dt,
            "todate": to_dt,
        }
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            _pace_candle()
            try:
                resp = self.client.getCandleData(params)
            except Exception as e:
                log.debug("Angel candle %s raised: %s", label, e)
                if attempt < _RATE_LIMIT_RETRIES:
                    time.sleep(min(_RATE_LIMIT_BACKOFF * (2 ** attempt), _BACKOFF_CAP)
                               + random.uniform(0, 0.4))
                    continue
                return []
            if isinstance(resp, dict) and resp.get("status") and resp.get("data") is not None:
                break
            if _is_throttled(resp) and attempt < _RATE_LIMIT_RETRIES:
                time.sleep(min(_RATE_LIMIT_BACKOFF * (2 ** attempt), _BACKOFF_CAP)
                           + random.uniform(0, 0.4))
                continue
            log.debug("Angel candle %s -> %s", label,
                      resp.get("message") if isinstance(resp, dict) else resp)
            return []

        rows = resp.get("data") or []
        out = []
        for r in rows:
            # Angel row: [timestamp, open, high, low, close, volume]
            try:
                out.append([r[0], float(r[1]), float(r[2]), float(r[3]),
                            float(r[4]), int(r[5]), 0])
            except (IndexError, TypeError, ValueError):
                continue
        # Ensure chronological (oldest-first) — Angel is usually already ascending.
        out.sort(key=lambda c: c[0])
        return out

    def minute_candles(self, exchange: str, token: str, date_str: str) -> list:
        """1-minute candles for a single date (YYYY-MM-DD), 09:15..15:30 IST."""
        return self._get_candles(exchange, token, "ONE_MINUTE",
                                 f"{date_str} 09:15", f"{date_str} 15:30",
                                 f"{token} 1m {date_str}")

    def minute_candles_range(self, exchange: str, token: str,
                             from_date: str, to_date: str) -> list:
        return self._get_candles(exchange, token, "ONE_MINUTE",
                                 f"{from_date} 09:15", f"{to_date} 15:30",
                                 f"{token} 1m {from_date}..{to_date}")

    def daily_candles(self, exchange: str, token: str,
                      from_date: str, to_date: str) -> list:
        """Daily candles over [from_date, to_date] inclusive, oldest-first."""
        return self._get_candles(exchange, token, "ONE_DAY",
                                 f"{from_date} 00:00", f"{to_date} 23:59",
                                 f"{token} 1d {from_date}..{to_date}")

    # -- quote helpers ----------------------------------------------------------
    def bulk_quotes(self, exchange_tokens: dict) -> dict:
        """LIVE full-quote snapshot via getMarketData('FULL', {exch: [tokens]}).

        `exchange_tokens` maps an Angel exchange ("NSE"/"NFO") to a list of numeric
        token strings. Angel accepts up to ~50 tokens per exchange per call, so we
        chunk. Returns {token(str): {last_price, volume, oi, day_high, day_low}}
        keyed by the SAME token strings passed in.
        """
        if self.client is None or not exchange_tokens:
            return {}
        out = {}
        for exch, tokens in exchange_tokens.items():
            tokens = [str(t) for t in tokens]
            for i in range(0, len(tokens), 50):
                chunk = tokens[i:i + 50]
                try:
                    resp = self.client.getMarketData("FULL", {exch: chunk})
                except Exception as e:
                    log.debug("Angel bulk quote (%s) raised: %s", exch, e)
                    continue
                if not (isinstance(resp, dict) and resp.get("status")):
                    log.debug("Angel bulk quote (%s) -> %s", exch,
                              resp.get("message") if isinstance(resp, dict) else resp)
                    continue
                fetched = (resp.get("data") or {}).get("fetched") or []
                for e in fetched:
                    tok = str(e.get("symbolToken") or e.get("symboltoken") or "")
                    if not tok:
                        continue
                    out[tok] = {
                        "last_price": e.get("ltp"),
                        "volume": e.get("tradeVolume") or 0,
                        "oi": e.get("opnInterest") or 0,
                        "day_high": e.get("high"),
                        "day_low": e.get("low"),
                    }
        return out

    def probe(self, exchange: str, token: str) -> bool:
        """Lightweight auth/access self-check: True if a single LTP quote succeeds."""
        if self.client is None:
            return False
        try:
            resp = self.client.getMarketData("LTP", {exchange: [str(token)]})
            return bool(isinstance(resp, dict) and resp.get("status"))
        except Exception as e:
            log.warning("Angel probe failed: %s", e)
            return False
