"""Who is asking the billing server (`cloud/billing.py`).

`TokenVerifier` reads the Supabase session token the app sends. The project
signs with an asymmetric key (ES256), so the check is local: the public key is
fetched once from the project's JWKS and cached. The secret key that reaches
the database lives in the Modal secret `luikki-supabase` and nowhere else.

`jwt` and `httpx` are imported where they are used, so a test can stand its
own verifier in.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("luikki.cloud")

# A device unseen this long gives its seat up to a new one.
DEVICE_DAYS = 30
# Longer than any panel takes, waiting for the GPU included. A lock older than
# this is a container that died holding it.
JOB_SECONDS = 600

_STATUS = {
    "no_subscription": 402,
    "too_many_devices": 403,
    "job_running": 409,
    "job_elsewhere": 409,
    "quota_cases": 429,
}


class Refused(Exception):
    """A request the account may not make, with the code the client words."""

    def __init__(self, status: int, code: str, **params):
        super().__init__(code)
        self.status = status
        self.code = code
        self.params = params


def supabase_headers(secret_key: str) -> dict:
    """A secret key (`sb_secret_…`) is not a JWT and goes on `apikey` alone;
    a legacy `service_role` key is one, and goes on both."""
    headers = {"apikey": secret_key}
    if not secret_key.startswith("sb_"):
        headers["authorization"] = f"Bearer {secret_key}"
    return headers


class TokenVerifier:
    def __init__(self, project_url: str, signing_key: Callable[[str], Any] | None = None):
        """`signing_key` maps a token to the key that must have signed it; tests
        pass their own instead of the project's JWKS."""
        import jwt

        self.issuer = project_url.rstrip("/") + "/auth/v1"
        if signing_key is None:
            keys = jwt.PyJWKClient(self.issuer + "/.well-known/jwks.json", cache_keys=True)
            signing_key = lambda token: keys.get_signing_key_from_jwt(token).key  # noqa: E731
        self._signing_key = signing_key

    def user(self, token: str) -> str:
        """The account id in a valid session token, or `Refused`."""
        import jwt

        try:
            claims = jwt.decode(
                token,
                self._signing_key(token),
                # Pinned, so a token cannot choose a weaker algorithm for itself.
                algorithms=["ES256"],
                audience="authenticated",
                issuer=self.issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWKClientConnectionError as exc:
            # Supabase is down, not the artist's session: signing in again
            # would change nothing.
            raise Refused(503, "accounts_unreachable") from exc
        except jwt.PyJWTError as exc:
            raise Refused(401, "unauthorized") from exc
        return claims["sub"]
