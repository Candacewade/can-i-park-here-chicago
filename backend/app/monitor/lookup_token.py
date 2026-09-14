"""Short-lived proof that someone controls an email address, for the "find my
watches" home-screen feature (enter an email -> get a link -> see/manage every
active watch for that address).

No accounts, no passwords: knowing a secret link mailed to an address is the
same trust level every other watch-management link in this app already uses
(see docs/monitoring.md). This just extends that to "all my watches" instead
of "this one watch".

Stateless by design: the token is a signed, self-contained payload (email +
expiry) -- no server-side store to write, expire, or clean up. The signing key
is generated once per process start, so a Render restart invalidates any
outstanding link; the user just requests a new one (a ~15 minute window, so
this is a minor inconvenience, not a correctness issue).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

_SECRET = secrets.token_bytes(32)
_TTL_SECONDS = 900  # 15 minutes


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_lookup_token(email: str) -> str:
    payload = json.dumps(
        {"email": email.strip().lower(), "exp": int(time.time()) + _TTL_SECONDS}
    ).encode()
    body = _b64(payload)
    sig = hmac.new(_SECRET, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_lookup_token(token: str) -> str | None:
    """The verified, normalized email the token was issued for, or None if the
    token is malformed, tampered with, or expired."""
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_SECRET, body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or "email" not in payload or "exp" not in payload:
        return None
    try:
        if int(payload["exp"]) < int(time.time()):
            return None
    except (TypeError, ValueError):
        return None
    return str(payload["email"])
