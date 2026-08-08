"""Enterprise authentication: API Key + tenant resolution."""

import os
import secrets
from functools import lru_cache
from fastapi import HTTPException, Header

# Ensure .env is loaded BEFORE reading RAGFORGE_API_KEY (config.py loads it too,
# but auth.py is often imported first — without this the key silently falls back
# to a random value and every request 403s)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ponytail: env var + fallback to generated key
# Rotate in production via RAGFORGE_API_KEY env
_DEFAULT_KEY = os.getenv("RAGFORGE_API_KEY", "ragforge-dev-" + secrets.token_hex(8))


@lru_cache
def get_api_keys() -> dict[str, dict]:
    """Return known API keys with their tenant + role bindings.
    Format: {"key": {"tenant": "default", "role": "admin"}}
    """
    keys = {_DEFAULT_KEY: {"tenant": "default", "role": "admin"}}
    # Read additional keys from env: RAGFORGE_KEYS=key1:tenant1:admin,key2:tenant2:viewer
    extra = os.getenv("RAGFORGE_KEYS", "")
    for entry in extra.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 2:
            keys[parts[0]] = {"tenant": parts[1], "role": parts[2] if len(parts) > 2 else "member"}
    return keys


def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Validate X-API-Key header. Returns tenant_id."""
    if not x_api_key:
        raise HTTPException(401, "X-API-Key header required")
    keys = get_api_keys()
    if x_api_key not in keys:
        raise HTTPException(403, "Invalid API key")
    return keys[x_api_key]["tenant"]


def require_tenant(x_api_key: str = Header(None)) -> str:
    """Dependency: extract tenant from verified API key."""
    return verify_api_key(x_api_key)
