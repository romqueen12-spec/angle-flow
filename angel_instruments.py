"""
Angel One F&O universe loader (replaces instruments.py's Upstox master).

Source of truth: Angel's public scrip master (no auth, cache 12h):
    https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json

Each row carries: token, symbol (e.g. "SBIN-EQ", "RELIANCE28AUG2025FUT"),
name (base symbol, e.g. "RELIANCE"), expiry ("28AUG2025"), strike, lotsize,
instrumenttype ("FUTSTK"/"OPTSTK"/"FUTIDX"/"OPTIDX"/"AMXIDX"/…), exch_seg
("NSE"/"NFO"/…). Unlike Upstox's "NSE_FO|xxxx" string keys, Angel identifies an
instrument by a numeric `token` string plus its exchange — so every universe here
maps base symbol -> {"token", "exchange"}.
"""
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
CACHE_FILE = Path(".cache/angel_scrip_master.json")
CACHE_MAX_AGE_SECONDS = 12 * 3600


def _download_scrip_master() -> list[dict]:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists() and (time.time() - CACHE_FILE.stat().st_mtime) < CACHE_MAX_AGE_SECONDS:
        return json.loads(CACHE_FILE.read_bytes())
    req = urllib.request.Request(SCRIP_MASTER_URL, headers={"User-Agent": "scanner-script"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    CACHE_FILE.write_bytes(raw)
    return json.loads(raw)


def _parse_expiry(exp: str):
    """Angel expiry is 'DDMMMYYYY' (e.g. '28AUG2025'); return a date or None."""
    if not exp:
        return None
    for fmt in ("%d%b%Y", "%d%b%y"):
        try:
            return datetime.strptime(exp.upper(), fmt).date()
        except ValueError:
            continue
    return None


def load_fno_futures_universe() -> dict[str, dict]:
    """
    {base_symbol: {"token": str, "exchange": "NFO"}} for the NEAR-MONTH futures of
    every F&O underlying (stock + index futures). Near-month = the smallest expiry
    on/after today, so it rolls automatically at expiry.
    """
    master = _download_scrip_master()
    today = datetime.now().date()

    near: dict[str, dict] = {}
    for inst in master:
        if inst.get("exch_seg") != "NFO":
            continue
        if inst.get("instrumenttype") not in ("FUTSTK", "FUTIDX"):
            continue
        name = (inst.get("name") or "").strip()
        exp = _parse_expiry(inst.get("expiry", ""))
        token = inst.get("token")
        if not (name and exp and token) or exp < today:
            continue
        cur = near.get(name)
        if cur is None or exp < cur["_exp"]:
            near[name] = {"token": str(token), "exchange": "NFO", "_exp": exp}

    return {sym: {"token": d["token"], "exchange": d["exchange"]} for sym, d in near.items()}


def load_fno_cash_universe(fno_symbols: set[str] | None = None) -> dict[str, dict]:
    """
    {base_symbol: {"token": str, "exchange": "NSE"}} for the CASH (equity) leg of
    every F&O underlying. Angel NSE equities carry symbol "<SYM>-EQ" and a blank
    instrumenttype. Index futures (NIFTY, BANKNIFTY, …) have no cash row and drop
    out naturally. Pass the futures-universe symbol set to restrict to F&O names.
    """
    master = _download_scrip_master()
    if fno_symbols is None:
        fno_symbols = set(load_fno_futures_universe())

    cash: dict[str, dict] = {}
    for inst in master:
        if inst.get("exch_seg") != "NSE":
            continue
        itype = (inst.get("instrumenttype") or "").strip()
        symbol = (inst.get("symbol") or "").strip()
        # Cash equities: blank instrumenttype and a "-EQ" trading symbol.
        if itype not in ("", "EQ") or not symbol.endswith("-EQ"):
            continue
        base = symbol[:-3]  # strip "-EQ"
        token = inst.get("token")
        if base in fno_symbols and base not in cash and token:
            cash[base] = {"token": str(token), "exchange": "NSE"}
    return cash
