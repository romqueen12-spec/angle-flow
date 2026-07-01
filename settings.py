"""
Unified config reader.

Streamlit Community Cloud injects secrets via st.secrets; locally the app uses a
.env file (loaded by python-dotenv in app.py). This helper hides that difference:
get_setting("SUPABASE_URL") returns the value from st.secrets if present, else
from the OS environment, else the supplied default. Nothing here is app-specific,
so token_store / upstox_auth / app.py can all share it.
"""
import os

try:
    import streamlit as st
except Exception:  # pragma: no cover - streamlit always present in this app
    st = None


def get_setting(name: str, default=None):
    # st.secrets raises if no secrets file exists at all, so guard broadly.
    if st is not None:
        try:
            if name in st.secrets:
                return st.secrets[name]
        except Exception:
            pass
    val = os.environ.get(name)
    return val if val not in (None, "") else default
