# 🧭 Inside-Range Coiler Scanner (Angel One)

A **second, standalone scanner** that lives beside the Upstox engine (`app.py`) and
does the **opposite selection**: instead of tracking stocks that *broke* the prior
day's high/low at 09:30, it shortlists the F&O names that did **not** break — the
ones still **coiling inside yesterday's range** — and splits them into two tabs.

Entry point: `scanner_app.py` → `streamlit run scanner_app.py`.

---

## What it does

1. **Prior levels** — cash daily candles give each F&O stock its PDH / PDL / PDC /
   avg volume (cached 12h).
2. **Selection (cheap, zero candle calls)** — one batched `getMarketData("FULL")`
   sweep over the ~200 cash names. A stock qualifies as a **coiler** when today's
   high ≤ PDH **and** today's low ≥ PDL (it has broken neither prior level).
3. **Side by range position** — `pos = (LTP − PDL) / (PDH − PDL)`:
   - `pos ≥ 0.5` (upper half, nearer PDH) → **📈 Long tab**
   - `pos < 0.5`  (lower half, nearer PDL) → **📉 Short tab**
   Rank within each tab = proximity to the level it is pressing toward.
4. **Detail (top-N per side)** — the full per-stock calc runs only on the best N
   coilers per side (slider, default 20): RVOL, OI flow, RS (mkt + sector), VWAP
   hold, ORB extension, big-player (ATM CE/PE), Power, Quality — **plus a Sector
   column**. Same math as the Upstox watchlist (`app.py:process_live_watchlist`).

No sector-matrix / breakout / today-vs-yesterday tabs — **scanner only**.

---

## Files

| File | Role |
|---|---|
| `scanner_app.py` | The 2-tab Streamlit app + all selection/scoring |
| `angel_api.py` | SmartConnect wrapper (`minute_candles`, `daily_candles`, `bulk_quotes`) with rate-limit pacing |
| `angel_instruments.py` | Angel scrip-master → `{symbol: {token, exchange}}` futures & cash universes |
| `angel_options.py` | Near-expiry ATM CE/PE token resolver |
| `angel_auth.py` | TOTP login → cached `AngelData` session |
| `sectors.py`, `settings.py` | reused from the Upstox app (sector labels, secret/env reader) |

---

## Credentials

Set these in `.env` (local) or `st.secrets` (Streamlit Cloud) — see `settings.py`:

```
ANGEL_API_KEY      = "your-smartapi-key"
ANGEL_CLIENT_CODE  = "your-client-code"     # Angel login ID
ANGEL_MPIN         = "your-mpin"            # login PIN
ANGEL_TOTP_SECRET  = "BASE32SECRET"         # from SmartAPI portal → enable TOTP/2FA
```

Login is fully automatic (TOTP generated via `pyotp` on every boot) — **no OAuth
redirect and no daily paste**, unlike the Upstox flow.

---

## ⚠️ Angel One constraints (baked into the design)

- **Candles carry NO open interest.** OI signals use the live `FULL`-quote
  `opnInterest` with a per-day intraday **baseline** (first-seen OI); OI% and OI
  flow read as neutral until OI moves. `bigplayer_signal`'s OI-rising kicker is
  therefore unavailable and treated as off.
- **Rate limits:** `getCandleData` = 3/s and **~180/min**. The bulk-scan-then-top-N
  design keeps candle calls to `2 × top_n` per refresh — at the default N=20 that's
  ~40 candle calls, comfortably under the cap even at a 60s refresh. Raising N or
  lowering the refresh interval eats into that budget; the slider defaults are safe.
- Quote endpoint is a separate (~1/s) bucket; universe sweeps are batched 50
  tokens/exchange/call.

---

## Quick start

```bash
pip install -r requirements.txt -r requirements-angel.txt
# put ANGEL_* in .env
streamlit run scanner_app.py
```

Set `TESTING_MODE = True` (top of `scanner_app.py`) to replay a past day
(`TEST_DAY` / `TEST_HHMM`); it still needs valid ANGEL_* credentials because Angel
serves historical candles through the same authenticated endpoint.
