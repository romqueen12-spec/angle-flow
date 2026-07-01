"""
Angel One near-expiry ATM option resolver (replaces options.py).

Built from the SAME scrip master angel_instruments.py caches — no extra fetch.
Each NFO option row carries name (base symbol), instrumenttype ("OPTSTK"/"OPTIDX"),
expiry ("28AUG2025"), strike, symbol ("...CE"/"...PE") and token. Angel encodes
`strike` in paise (×100), e.g. a 2800 strike appears as "280000.000000" — we
divide by 100 to recover rupee strikes.
"""
import logging
from datetime import datetime

import angel_instruments

log = logging.getLogger("pyscan.angel_options")


def load_option_index(ref_day_str: str) -> dict:
    """
    {base_symbol: {"expiry_date": str, "CE": {strike: token}, "PE": {strike: token}}}
    for the NEAREST expiry on/after ref_day_str (current/near series).
    """
    ref_date = datetime.strptime(ref_day_str, "%Y-%m-%d").date()
    master = angel_instruments._download_scrip_master()

    # symbol -> expiry_date -> {"CE": {strike: token}, "PE": {strike: token}}
    by_symbol: dict[str, dict] = {}
    for inst in master:
        if inst.get("exch_seg") != "NFO":
            continue
        itype = inst.get("instrumenttype")
        if itype not in ("OPTSTK", "OPTIDX"):
            continue
        sym = (inst.get("name") or "").strip()
        exp = angel_instruments._parse_expiry(inst.get("expiry", ""))
        token = inst.get("token")
        symbol = (inst.get("symbol") or "").strip()
        try:
            strike = float(inst.get("strike", 0)) / 100.0
        except (TypeError, ValueError):
            strike = 0.0
        if not (sym and exp and token and strike > 0) or exp < ref_date:
            continue
        side = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else None
        if side is None:
            continue
        exp_map = by_symbol.setdefault(sym, {}).setdefault(exp, {"CE": {}, "PE": {}})
        exp_map[side][strike] = str(token)

    index = {}
    for sym, expiries in by_symbol.items():
        near = min(expiries)
        legs = expiries[near]
        if not legs["CE"] and not legs["PE"]:
            continue
        index[sym] = {"expiry_date": near.isoformat(), "CE": legs["CE"], "PE": legs["PE"]}
    log.info("angel options: ATM index for %d underlyings (ref %s)", len(index), ref_day_str)
    return index


def atm_legs(symbol: str, price: float, opt_index: dict) -> dict | None:
    """{"strike": s, "CE": ce_token, "PE": pe_token} for the strike nearest `price`,
    or None if the symbol has no current-expiry options / no usable price."""
    entry = opt_index.get(symbol)
    if not entry or not price or price <= 0:
        return None
    strikes = set(entry["CE"]) | set(entry["PE"])
    if not strikes:
        return None
    strike = min(strikes, key=lambda s: abs(s - price))
    return {"strike": strike, "CE": entry["CE"].get(strike), "PE": entry["PE"].get(strike)}
