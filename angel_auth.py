"""
Angel One SmartAPI session helper.

Angel logins are TOTP-based, not OAuth-redirect:
generateSession(client, mpin, pyotp.TOTP(secret).now()) returns the day's
jwtToken directly. Because the TOTP is derived from a stored secret, the app
can log itself in on every boot with no browser round-trip.

Credentials come from st.secrets / env via settings.get_setting:
ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_MPIN, ANGEL_TOTP_SECRET
"""
from **future** import annotations

import logging
from typing import Optional

from settings import get_setting
from angel_api import AngelData

log = logging.getLogger("pyscan.angel_auth")

_REQUIRED = ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_MPIN", "ANGEL_TOTP_SECRET")

_SMARTAPI_IMPORT_ERROR: Optional[BaseException] = None
_PYOTP_IMPORT_ERROR: Optional[BaseException] = None

try:
# Prefer the module path used by the current SmartAPI package.
from SmartApi.smartConnect import SmartConnect
except Exception as e1:  # pragma: no cover
try:
# Fallback for older install layouts.
from SmartApi import SmartConnect
except Exception as e2:  # pragma: no cover
SmartConnect = None  # type: ignore[assignment]
_SMARTAPI_IMPORT_ERROR = RuntimeError(
f"SmartAPI import failed: {type(e1).**name**}: {e1} | {type(e2).**name**}: {e2}"
)

try:
import pyotp
except Exception as e:  # pragma: no cover
pyotp = None  # type: ignore[assignment]
_PYOTP_IMPORT_ERROR = e

def credentials_configured() -> bool:
return all(get_setting(k) for k in _REQUIRED)

def _missing_credentials() -> list[str]:
return [k for k in _REQUIRED if not get_setting(k)]

def create_session() -> tuple[Optional[AngelData], Optional[str]]:
"""
Log in and return (AngelData, error).

```
On success, error is None.
On failure, AngelData is None and error contains the exact reason.
"""
if SmartConnect is None:
    msg = str(_SMARTAPI_IMPORT_ERROR) if _SMARTAPI_IMPORT_ERROR else (
        "smartapi-python import failed. Install smartapi-python."
    )
    return None, msg

if pyotp is None:
    msg = str(_PYOTP_IMPORT_ERROR) if _PYOTP_IMPORT_ERROR else (
        "pyotp import failed. Install pyotp."
    )
    return None, msg

missing = _missing_credentials()
if missing:
    return None, f"Missing Angel One credentials: {', '.join(missing)}"

api_key = str(get_setting("ANGEL_API_KEY"))
client_code = str(get_setting("ANGEL_CLIENT_CODE"))
mpin = str(get_setting("ANGEL_MPIN"))
totp_secret = str(get_setting("ANGEL_TOTP_SECRET"))

try:
    client = SmartConnect(api_key=api_key)
    otp = pyotp.TOTP(totp_secret).now()
    resp = client.generateSession(client_code, mpin, otp)

    if not isinstance(resp, dict):
        return None, f"Login failed: unexpected response type: {type(resp).__name__}"

    if not resp.get("status"):
        msg = resp.get("message") or resp.get("error") or "Unknown SmartAPI login failure"
        return None, f"Login failed: {msg}"

    return AngelData(client), None

except Exception as e:
    log.exception("Angel session creation failed")
    return None, f"{type(e).__name__}: {e}"
```
