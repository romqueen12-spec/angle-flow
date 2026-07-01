"""
Angel One SmartAPI session helper (replaces upstox_auth.py + token_store.py).

Angel logins are TOTP-based, not OAuth-redirect: generateSession(client, mpin,
pyotp.TOTP(secret).now()) returns the day's jwtToken directly. Because the TOTP is
derived from a stored secret, the app can log itself in on every boot with NO
browser round-trip and NO daily paste — far simpler than the Upstox flow.

Credentials come from st.secrets / env via settings.get_setting:
    ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_MPIN, ANGEL_TOTP_SECRET
"""
import logging

from settings import get_setting
from angel_api import AngelData

log = logging.getLogger("pyscan.angel_auth")

try:
    from SmartApi import SmartConnect
except Exception:  # pragma: no cover
    SmartConnect = None

try:
    import pyotp
except Exception:  # pragma: no cover
    pyotp = None

_REQUIRED = ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_MPIN", "ANGEL_TOTP_SECRET")


def credentials_configured() -> bool:
    return all(get_setting(k) for k in _REQUIRED)


def create_session() -> tuple[AngelData | None, str | None]:
    """
    Log in and return (AngelData, error). On success error is None.

    The MPIN is Angel's login PIN; the TOTP secret is the base32 string shown when
    you enable external 2FA in the SmartAPI portal. pyotp turns it into the live
    6-digit code generateSession expects.
    """
    if SmartConnect is None:
        return None, "smartapi-python not installed (pip install smartapi-python)."
    if pyotp is None:
        return None, "pyotp not installed (pip install pyotp)."
    if not credentials_configured():
        missing = [k for k in _REQUIRED if not get_setting(k)]
        return None, f"Missing Angel One credentials: {', '.join(missing)}"

    api_key = get_setting("ANGEL_API_KEY")
    client_code = get_setting("ANGEL_CLIENT_CODE")
    mpin = str(get_setting("ANGEL_MPIN"))
    totp_secret = get_setting("ANGEL_TOTP_SECRET")

    try:
        client = SmartConnect(api_key=api_key)
        otp = pyotp.TOTP(totp_secret).now()
        resp = client.generateSession(client_code, mpin, otp)
        if not (isinstance(resp, dict) and resp.get("status")):
            msg = resp.get("message") if isinstance(resp, dict) else str(resp)
            return None, f"Login failed: {msg}"
        return AngelData(client), None
    except Exception as e:
        log.warning("Angel session creation failed: %s", e)
        return None, str(e)