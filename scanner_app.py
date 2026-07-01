"""
Angel One "Inside-Range Coiler" scanner.

DIFFERENCE FROM app.py (the Upstox engine): app.py locks the stocks that BROKE the
previous day's high/low at 09:30. This scanner does the OPPOSITE — it shortlists
the F&O names that did NOT break PDH/PDL and are still coiling INSIDE yesterday's
range, then splits them by where they sit in that range:

  * price in the UPPER half of [PDL, PDH]  -> 📈 Long tab  (leaning toward an up-break)
  * price in the LOWER half                -> 📉 Short tab (leaning toward a down-break)

Each tab shows the SAME per-stock calculations as the Upstox watchlist (RVOL, OI
flow, RS, VWAP hold, ORB, big-player, Power, Quality) plus a Sector column. There
is no sector-matrix / breakout / today-vs-yesterday tab — scanner only.

Data comes from Angel One SmartAPI (angel_api / angel_auth), whose candle feed
carries NO open interest, so OI signals are derived from the live FULL-quote
`opnInterest` snapshot with a per-day intraday baseline (see fut OI handling).

Rate limits (getCandleData 3/s, ~180/min) force a two-stage scan: a cheap
universe-wide bulk-quote sweep selects + ranks every inside-range name using ZERO
candle calls, then the heavy per-stock calc runs only on the TOP-N per side.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

import pytz
import pandas as pd
import streamlit as st

import angel_instruments
import angel_options
import sectors
from settings import get_setting
from angel_auth import create_session, credentials_configured

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pyscan.scanner")

st.set_page_config(page_title="Inside-Range Coiler Scanner", layout="wide", page_icon="🧭")

# ================= CONFIG =================
TESTING_MODE = False
TEST_DAY = "2026-06-19"
TEST_HHMM = "13:30"

TRADING_MINUTES = 375
RECENT_VOL_DAYS = 10
PRIOR_LOOKBACK_DAYS = 20
BIGPLAYER_WINDOW = 30
PER_BAR_CAP = 10.0
BLOCK_MULT = 5.0
DEFAULT_TOP_N = 20          # per side; TOP_N*2*(1 candle) candle calls/refresh
AUTO_REFRESH_MS = 90_000    # 90s keeps candle load under the 180/min cap
STRONG_MIN_RVOL = 1.5
OR_END = "09:30"            # opening-range end used to read the "did it break?" close

ist = pytz.timezone("Asia/Kolkata")
now = datetime.now(ist)
if TESTING_MODE:
    today_date, current_hhmm = TEST_DAY, TEST_HHMM
else:
    today_date, current_hhmm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")

CACHE_DIR = Path(".cache")
OI_BASELINE_PATH = CACHE_DIR / f"angel_oi_baseline_{today_date}.json"

# ================= AUTH =================
@st.cache_resource
def get_session():
    if TESTING_MODE and not credentials_configured():
        return None, "TESTING_MODE without credentials — supply ANGEL_* to fetch data."
    return create_session()

hist, auth_err = get_session()
if hist is None:
    st.markdown("## 🔑 Connect Angel One")
    st.error(auth_err or "Could not create an Angel One session.")
    st.caption("Set ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_MPIN, ANGEL_TOTP_SECRET "
               "in secrets/.env. The TOTP secret is the base32 string from SmartAPI 2FA.")
    st.stop()
hist.intraday_date = None if TESTING_MODE else today_date

# ================= UNIVERSES =================
@st.cache_data(ttl=12 * 3600)
def load_universes():
    fut = angel_instruments.load_fno_futures_universe()
    cash = angel_instruments.load_fno_cash_universe(set(fut))
    return fut, cash

fut_universe, cash_universe = load_universes()

# ================= HELPERS (shared math, mirrors app.py) =================
def oi_weight(side, action):
    if side == "LONG":
        return {"🟢 Long Buildup": 1.5, "🚀 Short Covering": 0.9}.get(action, 0.5)
    return {"🔴 Short Buildup": 1.5, "⚠️ Long Unwinding": 0.9}.get(action, 0.5)

def quality_verdict(vwap_hold, oi_aligned, structure_flag, big_player_active, extending, mtf_aligned):
    score = sum([bool(vwap_hold), bool(oi_aligned), bool(structure_flag),
                 bool(big_player_active), bool(extending)])
    if score >= 4 and mtf_aligned: return f"⭐⭐⭐ Strong ({score}/5)"
    if not mtf_aligned: return f"⚠️ Trap Warning ({score}/5)"
    if score == 3: return f"⭐⭐ Watch ({score}/5)"
    return f"⭐ Weak ({score}/5)"

def hh_ll_signal(minutes, side):
    if not minutes or len(minutes) < 2: return ""
    closes = [c[4] for c in minutes]
    latest, prior = closes[-1], closes[:-1]
    if side == "LONG": return "🆕 HH" if latest > max(prior) else ""
    return "🆕 LL" if latest < min(prior) else ""

def bigplayer_signal(minutes):
    """Volume-based big-player probe. Angel candles have no OI, so the OI-rising
    kicker is unavailable here and treated as False (accum uses the 0.8 factor)."""
    if not minutes: return None
    window = minutes[-BIGPLAYER_WINDOW:]
    prior = minutes[:-BIGPLAYER_WINDOW]
    base_src = prior if len(prior) >= 5 else minutes
    base = sum(c[5] for c in base_src) / len(base_src)
    if base <= 0: return None
    ratios = [c[5] / base for c in window]
    rvol_recent = sum(min(r, PER_BAR_CAP) for r in ratios) / len(ratios)
    accum = rvol_recent * 0.8
    return {"accum": round(accum, 1), "block": max(ratios) >= BLOCK_MULT}

def load_oi_baseline():
    if OI_BASELINE_PATH.exists():
        try: return json.loads(OI_BASELINE_PATH.read_text())
        except Exception: pass
    return {}

def save_oi_baseline(data):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        OI_BASELINE_PATH.write_text(json.dumps(data))
    except Exception: pass

# ================= PRIOR LEVELS =================
@st.cache_data(ttl=12 * 3600)
def load_prior_levels(day_str):
    """{sym: {pdh, pdl, pdc, avg_vol}} from cash daily candles. No OI (Angel candles
    omit it), so downstream OI% uses the live intraday baseline instead."""
    end = (datetime.strptime(day_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.strptime(day_str, "%Y-%m-%d") - timedelta(days=PRIOR_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    levels = {}
    for sym, meta in cash_universe.items():
        days = hist.daily_candles(meta["exchange"], meta["token"], start, end)
        if not days: continue
        last = days[-1]
        recent = days[-RECENT_VOL_DAYS:]
        avg_vol = sum(d[5] for d in recent) / len(recent) if recent else 0.0
        levels[sym] = {"pdh": last[2], "pdl": last[3], "pdc": last[4], "avg_vol": avg_vol}
    return levels

# ================= BULK QUOTES =================
@st.cache_data(ttl=60)
def fetch_cash_quotes(stamp):
    by_tok = hist.bulk_quotes({"NSE": [m["token"] for m in cash_universe.values()]})
    return {sym: by_tok.get(m["token"]) for sym, m in cash_universe.items() if by_tok.get(m["token"])}

@st.cache_data(ttl=60)
def fetch_fut_quotes(stamp):
    by_tok = hist.bulk_quotes({"NFO": [m["token"] for m in fut_universe.values()]})
    return {sym: by_tok.get(m["token"]) for sym, m in fut_universe.items() if by_tok.get(m["token"])}

@st.cache_data(ttl=12 * 3600)
def load_opt_index(day_str):
    return angel_options.load_option_index(day_str)

# ================= SELECTION (bulk, zero candle calls) =================
def select_inside_range(cash_quotes, levels):
    """Return (long_rows, short_rows), each a list of dicts sorted best-first.

    A name qualifies when today's high/low (from the FULL quote) has taken out
    NEITHER prior level -> still inside [PDL, PDH]. Side is decided by position in
    range; rank is proximity to the level it is pressing toward (a coiler hugging
    PDH is the most imminent up-break, so it ranks first in the Long tab)."""
    longs, shorts = [], []
    for sym, q in cash_quotes.items():
        lv = levels.get(sym)
        lp = q.get("last_price")
        if not lv or not lp or lp <= 0: continue
        pdh, pdl = lv["pdh"], lv["pdl"]
        if pdh <= pdl: continue
        dh = q.get("day_high") or lp
        dl = q.get("day_low") or lp
        # Inside-range = neither prior level breached today.
        if dh > pdh or dl < pdl: continue
        pos = (lp - pdl) / (pdh - pdl)          # 0 at PDL, 1 at PDH
        row = {"symbol": sym, "last_price": lp, "pos": pos,
               "sector": sectors.sector_for(sym)}
        if pos >= 0.5:
            row["rank"] = pos                    # nearer PDH -> higher
            longs.append(row)
        else:
            row["rank"] = 1.0 - pos              # nearer PDL -> higher
            shorts.append(row)
    longs.sort(key=lambda r: -r["rank"])
    shorts.sort(key=lambda r: -r["rank"])
    return longs, shorts

# ================= PER-STOCK DETAIL (top-N only) =================
def process_side(candidates, side, levels, fut_quotes, opt_index, nifty_pct, sector_avg, oi_baseline):
    records = []
    for cand in candidates:
        sym = cand["symbol"]
        meta = cash_universe.get(sym)
        lv = levels.get(sym)
        if not meta or not lv or lv["pdc"] <= 0: continue
        minutes = hist.minute_candles(meta["exchange"], meta["token"], today_date)
        if not minutes: continue
        try:
            df = pd.DataFrame(minutes, columns=["ts", "open", "high", "low", "close", "vol", "oi"])
            df["8EMA"] = df["close"].ewm(span=8, adjust=False).mean()
            price = df["close"].iloc[-1]
            ema_8 = df["8EMA"].iloc[-1]

            # 15-min multi-timeframe trend
            d15 = df[["ts", "close"]].copy()
            d15["ts"] = pd.to_datetime(d15["ts"])
            d15 = d15.set_index("ts")["close"].resample("15min").last().dropna().to_frame()
            d15["8EMA"] = d15["close"].ewm(span=8, adjust=False).mean()
            mtf_up = (d15["close"].iloc[-1] > d15["8EMA"].iloc[-1]) if len(d15) else (price > ema_8)
            mtf_aligned = (side == "LONG" and mtf_up) or (side == "SHORT" and not mtf_up)
            mtf_tag = "🟢 15m Aligned" if mtf_aligned else "🔴 15m Opposed"

            pdc = lv["pdc"]
            live_pct = ((price - pdc) / pdc) * 100.0

            cum_vol = float(df["vol"].sum())
            elapsed = max(len(df), 1)
            expected = lv["avg_vol"] * min(elapsed / TRADING_MINUTES, 1.0)
            live_rvol = cum_vol / expected if expected > 0 else 0.0

            # OI flow from the futures live snapshot vs the day's first-seen baseline.
            fq = fut_quotes.get(sym) or {}
            cur_oi = fq.get("oi") or 0
            base_oi = oi_baseline.get(sym)
            if base_oi is None and cur_oi:
                oi_baseline[sym] = base_oi = cur_oi
            oi_chg = ((cur_oi - base_oi) / base_oi * 100.0) if base_oi else 0.0
            if live_pct > 0 and oi_chg > 0: trend = "🟢 Long Buildup"
            elif live_pct < 0 and oi_chg > 0: trend = "🔴 Short Buildup"
            elif live_pct > 0 and oi_chg < 0: trend = "🚀 Short Covering"
            elif live_pct < 0 and oi_chg < 0: trend = "⚠️ Long Unwinding"
            else: trend = "⚪ Neutral"
            oi_aligned = oi_chg > 0

            sec = cand["sector"]
            sec_avg = sector_avg.get(sec, 0.0)
            if side == "LONG":
                rs_mkt, rs_sec, sec_on = live_pct - nifty_pct, live_pct - sec_avg, sec_avg > 0
            else:
                rs_mkt, rs_sec, sec_on = nifty_pct - live_pct, sec_avg - live_pct, sec_avg < 0

            typ = (df["high"] + df["low"] + df["close"]) / 3.0
            vwap = float((typ * df["vol"]).sum() / cum_vol) if cum_vol > 0 else price
            vwap_dist = ((price - vwap) / vwap) * 100.0 if vwap else 0.0
            vwap_hold = price >= vwap if side == "LONG" else price <= vwap
            vwap_tag = f"{'✓' if vwap_hold else '✗'} {vwap_dist:+.1f}%"

            last = df.iloc[-1]
            rng = last["high"] - last["low"]
            if rng > 0:
                cs = ((last["close"] - last["low"]) / rng * 100.0) if side == "LONG" \
                    else ((last["high"] - last["close"]) / rng * 100.0)
            else: cs = 50.0

            or_mins = [c for c in minutes if "09:15" <= c[0][11:16] < OR_END]
            if or_mins:
                or_hi, or_lo = max(c[2] for c in or_mins), min(c[3] for c in or_mins)
                extending = price > or_hi if side == "LONG" else price < or_lo
            else: extending = False
            orb_tag = "🟢 Extend" if extending else "🔵 Inside"

            avg_min_vol = cum_vol / elapsed if elapsed else 0.0
            surge = (float(last["vol"]) / avg_min_vol) if avg_min_vol > 0 else 0.0
            vol_tag = f"{'⚡' if surge >= 2.0 else ''}x{surge:.1f}"

            fav = live_pct if side == "LONG" else -live_pct
            rs_factor = 1.0 + max(-0.4, min(1.0, (rs_mkt + rs_sec) / 8.0))
            power = max(fav, 0.1) * live_rvol * oi_weight(side, trend) * (1.2 if sec_on else 0.7) * rs_factor

            # ATM big-player + PCR from the option FULL quotes (no extra candle call).
            bp_leg, bp_accum, bp_block, pcr_tag, atm_strike = "—", 0.0, "—", "—", None
            legs = angel_options.atm_legs(sym, price, opt_index)
            if legs:
                atm_strike = legs["strike"]
                opt_tokens = [t for t in (legs["CE"], legs["PE"]) if t]
                oq = hist.bulk_quotes({"NFO": opt_tokens}) if opt_tokens else {}
                ce_oi = (oq.get(legs["CE"]) or {}).get("oi", 0) if legs["CE"] else 0
                pe_oi = (oq.get(legs["PE"]) or {}).get("oi", 0) if legs["PE"] else 0
                ce_v = (oq.get(legs["CE"]) or {}).get("volume", 0) if legs["CE"] else 0
                pe_v = (oq.get(legs["PE"]) or {}).get("volume", 0) if legs["PE"] else 0
                leg_vols = {"ATM-CE": ce_v, "ATM-PE": pe_v}
                active = {k: v for k, v in leg_vols.items() if v > 0}
                if active:
                    dom = max(active, key=active.get)
                    if avg_min_vol and active[dom] > avg_min_vol * BLOCK_MULT:
                        bp_leg, bp_block = f"🐳 {dom}", f"⚡ {dom}"
                    bp_accum = round(active[dom] / avg_min_vol, 1) if avg_min_vol else 0.0
                    if bp_accum >= 2.0 and bp_leg == "—": bp_leg = f"🐳 {dom}"
                if ce_oi > 0 and pe_oi > 0:
                    long_ok = trend in ("🟢 Long Buildup", "🚀 Short Covering")
                    short_ok = trend in ("🔴 Short Buildup", "⚠️ Long Unwinding")
                    if side == "LONG" and ce_oi > pe_oi * 1.4:
                        pcr_tag = "⚠️ CE Heavy" if long_ok else "🚨 CE Ceiling (Trap)"
                    elif side == "SHORT" and pe_oi > ce_oi * 1.4:
                        pcr_tag = "⚠️ PE Heavy" if short_ok else "🚨 PE Floor (Trap)"
                    else: pcr_tag = "✅ Clear Path"

            structure = hh_ll_signal(minutes, side)
            big_active = bp_accum >= 2.0 or bp_block != "—"
            hot = "🔥" if (structure and big_active) else ""
            quality = quality_verdict(vwap_hold, oi_aligned, structure, big_active, extending, mtf_aligned)

            records.append({
                "Symbol": sym, "Sector": sec.upper(), "Range Pos %": round(cand["pos"] * 100),
                "Live Price": round(price, 2), "Intraday %": round(live_pct, 2), "8 EMA": round(ema_8, 2),
                "RVOL": round(live_rvol, 2), "OI Δ%": round(oi_chg, 2), "OI Flow": trend,
                "RS Mkt": round(rs_mkt, 2), "RS Sec": round(rs_sec, 2), "VWAP": vwap_tag,
                "Close Str": round(cs), "ORB": orb_tag, "Vol": vol_tag, "15m Trend": mtf_tag,
                "PCR Alert": pcr_tag, "ATM": round(atm_strike, 1) if atm_strike else None,
                "Big Player": bp_leg, "Accum": bp_accum, "Block": bp_block, "Power": round(power, 2),
                "Structure": structure, "🔥": hot, "Quality": quality,
            })
        except Exception as e:
            log.debug("process %s skipped: %s", sym, e)
            continue
    return records

def market_and_sector_context(fut_quotes, cash_quotes, levels):
    """NIFTY % (from its future) + per-sector average % (from cash quotes) — both
    free off the bulk snapshots already fetched, no extra calls."""
    nifty_pct = 0.0
    # NIFTY future has no prior_levels entry (cash-only), so gauge vs its own PDC
    # is unavailable; use cash-universe advance/decline mean as a market proxy.
    pcts, sector_pcts = [], {}
    for sym, q in cash_quotes.items():
        lv = levels.get(sym); lp = q.get("last_price")
        if not lv or lv["pdc"] <= 0 or not lp: continue
        pct = ((lp - lv["pdc"]) / lv["pdc"]) * 100.0
        pcts.append(pct)
        sector_pcts.setdefault(sectors.sector_for(sym), []).append(pct)
    nifty_pct = sum(pcts) / len(pcts) if pcts else 0.0   # breadth mean as market proxy
    sector_avg = {s: sum(v) / len(v) for s, v in sector_pcts.items()}
    return nifty_pct, sector_avg

# ================= UI =================
with st.sidebar:
    st.markdown("### ⚙️ Controls")
    if TESTING_MODE: st.warning(f"🧪 TESTING — replaying {today_date} {current_hhmm}")
    else: st.success(f"🟢 LIVE — {now.strftime('%H:%M:%S')} IST")
    top_n = st.slider("🔎 Detail depth (top-N per side)", 5, 40, DEFAULT_TOP_N, 5,
                      help="How many best-ranked coilers per tab get the full calc. "
                           "Higher = more rows but more candle calls (180/min cap).")
    refresh_secs = st.select_slider("🔄 Auto-refresh", options=[60, 90, 120, 180],
                                    value=AUTO_REFRESH_MS // 1000, format_func=lambda s: f"{s}s",
                                    disabled=TESTING_MODE)
    strong_min_rvol = st.slider("💪 Strong filter — min RVOL", 1.0, 3.0, float(STRONG_MIN_RVOL), 0.1)
    st.caption("Coilers = F&O names still INSIDE yesterday's range. Long = upper "
               "half (nearer PDH), Short = lower half (nearer PDL).")

if not TESTING_MODE and st_autorefresh is not None:
    st_autorefresh(interval=refresh_secs * 1000, key="scanner_refresh")

st.markdown("## 🧭 Inside-Range Coiler Scanner")
st.caption("F&O stocks that have NOT broken the previous day's high/low — coiling "
           "inside the range — split Long (upper half) / Short (lower half).")

# --- pipeline ---
levels = load_prior_levels(today_date)
cash_quotes = fetch_cash_quotes(current_hhmm)
fut_quotes = fetch_fut_quotes(current_hhmm)
opt_index = load_opt_index(today_date)
oi_baseline = load_oi_baseline()

if not cash_quotes:
    st.warning("No live quotes yet (market may be pre-open, or credentials lack data access).")
    st.stop()

nifty_pct, sector_avg = market_and_sector_context(fut_quotes, cash_quotes, levels)
long_cands, short_cands = select_inside_range(cash_quotes, levels)

k1, k2, k3 = st.columns(3)
k1.metric("🕒 Clock (IST)", now.strftime("%H:%M"))
k2.metric("📈 Long coilers", len(long_cands))
k3.metric("📉 Short coilers", len(short_cands))
st.divider()

long_rows = process_side(long_cands[:top_n], "LONG", levels, fut_quotes, opt_index, nifty_pct, sector_avg, oi_baseline)
short_rows = process_side(short_cands[:top_n], "SHORT", levels, fut_quotes, opt_index, nifty_pct, sector_avg, oi_baseline)
save_oi_baseline(oi_baseline)

def render(rows, side_label):
    if not rows:
        st.info(f"No {side_label} coilers with live rows yet.")
        return
    df = pd.DataFrame(rows)
    def _quality_rank(q):
        # "⚠️" is two Unicode code points (base + variation selector), so a
        # fixed str[:3] slice never lines up with "⭐⭐"/"⭐" prefixes reliably —
        # match by startswith instead, most-specific prefix first.
        if q.startswith("⭐⭐⭐"): return 3
        if q.startswith("⭐⭐"): return 2
        if q.startswith("⚠️"): return 1
        return 0
    df["_q"] = df["Quality"].map(_quality_rank)
    df = df.sort_values(["_q", "Power"], ascending=[False, False]).drop(columns="_q")
    strong = st.checkbox(f"💪 Strong only — RVOL ≥ {strong_min_rvol:.1f} + 15m aligned + holding VWAP",
                         key=f"strong_{side_label}")
    if strong:
        df = df[(df["RVOL"] >= strong_min_rvol) & (df["15m Trend"] == "🟢 15m Aligned")
                & (df["VWAP"].str.startswith("✓"))]
    st.caption(f"Showing {len(df)} {side_label} names.")
    if df.empty:
        st.info("No names match the Strong filter — untick to see all.")
        return
    st.dataframe(df.style.background_gradient(cmap="RdYlGn",
                 subset=["Intraday %", "RS Mkt", "RS Sec", "Accum", "Power"]),
                 width="stretch", hide_index=True)

tab_long, tab_short = st.tabs([f"📈 Long Coilers ({len(long_rows)})",
                               f"📉 Short Coilers ({len(short_rows)})"])
with tab_long:
    st.caption("Upper half of yesterday's range — pressing toward PDH.")
    render(long_rows, "LONG")
with tab_short:
    st.caption("Lower half of yesterday's range — pressing toward PDL.")
    render(short_rows, "SHORT")