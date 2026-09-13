"""Who is asking, and whether their account may spend GPU time (ROADMAP §B, B2).

Two halves, both on the server:

- `TokenVerifier` reads the Supabase session token the app sends. The project
  signs with an asymmetric key (ES256), so the check is local: the public key
  is fetched once from the project's JWKS and cached, and a panel never waits
  on Supabase to learn who sent it.
- `Ledger` asks the database the rest — subscription, quota, devices, the
  one-job lock — through `start_panel` and `finish_panel` (`schema.sql`), one
  transaction each, with the secret key. That key lives in the Modal secret
  `luikki-supabase` and nowhere else.

`jwt` and `httpx` are imported where they are used, so `server.py` imports
without them and a test can stand its own verifier in.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("luikki.cloud")

# Stand-ins for a plan with no row in `plans` (`schema.sql`), which is where
# the limits live. Provisional, fixed for good once measured (ROADMAP §C).
PAGES_PER_MONTH = 100
GENERATIONS_PER_PAGE = 10
DEVICES = 2
# A device unseen this long gives its place up to a new one.
DEVICE_DAYS = 30
# Longer than any panel takes, waiting for the GPU included. A lock older than
# this is a container that died holding it.
JOB_SECONDS = 600

_STATUS = {
    "no_subscription": 402,
    "too_many_devices": 403,
    "job_running": 409,
    "job_elsewhere": 409,
    "quota_pages": 429,
    "quota_generations": 429,
}


class Refused(Exception):
    """A request the account may not make, with the code the client words."""

    def __init__(self, status: int, code: str, **params):
        super().__init__(code)
        self.status = status
        self.code = code
        self.params = params


def client_ip(forwarded: str | None, peer: str | None) -> str:
    """The caller's address for the job lock's log, never trusted for more.

    The first `x-forwarded-for` hop when there is one — the proxy in front of
    the container is not the artist — else the peer, else a placeholder.
    """
    for candidate in ((forwarded or "").split(",")[0].strip(), peer or ""):
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return "0.0.0.0"


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


class Ledger:
    """`start_panel` and `finish_panel`, over the Data API with the secret key."""

    def __init__(self, project_url: str, secret_key: str, client: Any = None, attempts: int = 3):
        import httpx

        self.base = project_url.rstrip("/") + "/rest/v1/rpc/"
        self.headers = supabase_headers(secret_key)
        self.client = client or httpx.Client(timeout=15.0)
        self.attempts = attempts

    def start(self, user: str, page: str, generation: str, device: str, ip: str) -> None:
        """Take the account's job lock, or raise `Refused` with the reason."""
        response = self._post(
            "start_panel",
            {
                "p_user": user,
                "p_page": page,
                "p_generation": generation,
                "p_device": device,
                "p_ip": ip,
                "p_pages_per_month": PAGES_PER_MONTH,
                "p_generations_per_page": GENERATIONS_PER_PAGE,
                "p_devices": DEVICES,
                "p_device_days": DEVICE_DAYS,
                "p_job_seconds": JOB_SECONDS,
            },
        )
        if response is None:
            raise Refused(503, "accounts_unreachable")
        code = str(response.json())
        if code == "ok":
            return
        if code == "job_elsewhere":
            # Refused either way; logged because it is what a shared login
            # looks like.
            logger.warning("job_elsewhere: account %s, second request from %s", user, ip)
        raise Refused(_STATUS.get(code, 403), code)

    def finish(self, user: str, page: str, generation: str, painted: bool) -> None:
        """Lift the lock, and charge the panel if it was painted.

        Never raises: the GPU time is already spent, and a lock left behind
        expires on its own after `JOB_SECONDS`.
        """
        arguments = {"p_user": user, "p_page": page, "p_generation": generation, "p_succeeded": painted}
        for _ in range(self.attempts):
            if self._post("finish_panel", arguments) is not None:
                return
        logger.warning("finish_panel failed for account %s; its lock expires in %s s", user, JOB_SECONDS)

    def _post(self, function: str, arguments: dict):
        """The database's answer, or None when it could not be asked."""
        import httpx

        try:
            response = self.client.post(self.base + function, json=arguments, headers=self.headers)
        except httpx.TransportError as exc:
            logger.warning("%s: %s", function, type(exc).__name__)
            return None
        if response.status_code >= 300:
            logger.warning("%s answered %s: %s", function, response.status_code, response.text[:200])
            return None
        return response
