"""The artist's account on this machine: a code by email once, then stay signed in.

The app signs in without a password. Supabase emails a code, the artist types
it here, and the session that comes back is what `POST /v1/panel` checks
(`cloud/accounts.py`). Only the refresh token is kept, in the system's own
password store through `keyring` (Credential Manager, Keychain): closing the
app signs nobody out, and nothing readable sits in the project folder. The
access token lives in memory and is renewed shortly before it lapses.

The project URL and its publishable key are written here. They name the
project and grant nothing on their own — every table is closed to them — and
every copy of the app carries them anyway.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger("luikki.account")

SUPABASE_URL = "https://wuqgjbrkymmvvxftkeyi.supabase.co"
SUPABASE_KEY = "sb_publishable_9pz49jbpKr74dsSE4--juQ_4rFDfMaz"
# Renewed this many seconds early, so a panel never goes up with a token that
# lapses on the way.
_MARGIN = 60


class AccountError(RuntimeError):
    """Signing in did not work, named by a code the browser words (`error.<code>`)."""

    def __init__(self, code: str, status: int = 409, **params):
        super().__init__(code)
        self.code = code
        self.status = status
        self.params = params


class KeyringVault:
    """The system's password store, under the service name `Luikki`."""

    SERVICE = "Luikki"

    def get(self, name: str) -> str | None:
        import keyring
        from keyring.errors import KeyringError

        try:
            return keyring.get_password(self.SERVICE, name)
        except KeyringError:
            return None

    def set(self, name: str, value: str) -> None:
        import keyring
        from keyring.errors import KeyringError

        try:
            keyring.set_password(self.SERVICE, name, value)
        except KeyringError as exc:
            raise AccountError("vault_unavailable") from exc

    def delete(self, name: str) -> None:
        import keyring
        from keyring.errors import KeyringError

        try:
            keyring.delete_password(self.SERVICE, name)
        except KeyringError:
            pass


class Account:
    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        vault: Any = None,
        client: Any = None,
    ):
        """`LUIKKI_SUPABASE_URL` and `LUIKKI_SUPABASE_KEY` point a build at
        another project. `client` is an `httpx.Client` to send through; tests
        pass one with a mock transport."""
        self.url = (url or os.environ.get("LUIKKI_SUPABASE_URL") or SUPABASE_URL).rstrip("/")
        self.key = key or os.environ.get("LUIKKI_SUPABASE_KEY") or SUPABASE_KEY
        self.vault = vault if vault is not None else KeyringVault()
        self.client = client
        self._lock = threading.Lock()
        self._loaded = False
        self._email: str | None = None
        self._refresh: str | None = None
        self._access = ""
        self._expires = 0.0
        self._device: str | None = None

    def _load(self) -> None:
        # Read on first use rather than at start: the vault can be slow to
        # answer, and a session that never touches the account never asks it.
        if not self._loaded:
            self._email = self.vault.get("email")
            self._refresh = self.vault.get("refresh_token")
            self._loaded = True

    @property
    def email(self) -> str | None:
        """Who is signed in on this machine, or None."""
        with self._lock:
            self._load()
            return self._email if self._refresh else None

    def send_code(self, email: str) -> None:
        """Have Supabase email a sign-in code. A new address gets an account."""
        email = email.strip()
        if "@" not in email:
            raise AccountError("email_invalid")
        response = self._post("/auth/v1/otp", {"email": email, "create_user": True})
        if response.status_code == 429:
            raise AccountError("code_too_soon")
        if response.status_code in (400, 422):
            raise AccountError("email_invalid")
        if response.status_code >= 300:
            raise AccountError("accounts_unreachable", status=503)

    def verify(self, email: str, code: str) -> None:
        """Trade the emailed code for a session, and keep it."""
        response = self._post(
            "/auth/v1/verify", {"type": "email", "email": email.strip(), "token": code.strip()}
        )
        if response.status_code >= 300:
            raise AccountError("code_wrong")
        with self._lock:
            self._adopt(response.json(), fallback_email=email.strip())

    def access_token(self) -> str | None:
        """A live session token, renewed if it is about to lapse; None when signed out."""
        with self._lock:
            self._load()
            if not self._refresh:
                return None
            if self._access and time.time() < self._expires - _MARGIN:
                return self._access
            response = self._post(
                "/auth/v1/token?grant_type=refresh_token", {"refresh_token": self._refresh}
            )
            if response.status_code in (400, 401, 403):
                # Revoked, or signed out from elsewhere: the session is over,
                # and pretending otherwise would fail every panel after this.
                self._forget()
                raise AccountError("signed_out")
            if response.status_code >= 300:
                raise AccountError("accounts_unreachable", status=503)
            self._adopt(response.json())
            return self._access

    def sign_out(self) -> None:
        with self._lock:
            self._load()
            if self._access and time.time() < self._expires:
                # Ends the session on Supabase's side too. Best effort: the
                # local half is what signs this computer out.
                try:
                    self._post("/auth/v1/logout", None, bearer=self._access)
                except AccountError:
                    pass
            self._forget()

    def status(self, page: str = "") -> dict | None:
        """The plan and what is left of it this month, for step 5 before it is
        pressed (`my_status` in `schema.sql`). None when signed out or when the
        database will not say: the GPU server still decides at the press."""
        token = self.access_token()
        if not token:
            return None
        response = self._post("/rest/v1/rpc/my_status", {"p_page": page or None}, bearer=token)
        if response.status_code >= 300:
            logger.warning("my_status answered %s: %s", response.status_code, response.text[:200])
            return None
        return response.json()

    def device_id(self) -> str:
        """This installation's uuid, made once. Kept through signing out: it is
        the computer, not the session, that an account's two places count."""
        with self._lock:
            if self._device is None:
                self._device = self.vault.get("device_id")
            if self._device is None:
                self._device = str(uuid.uuid4())
                try:
                    self.vault.set("device_id", self._device)
                except AccountError:
                    pass
            return self._device

    def _adopt(self, session: dict, fallback_email: str | None = None) -> None:
        # Supabase rotates the refresh token on every use: the new one is kept
        # before the old is dropped, or a crash here would sign the artist out.
        refresh = session["refresh_token"]
        email = (session.get("user") or {}).get("email") or fallback_email or self._email
        self.vault.set("refresh_token", refresh)
        if email:
            self.vault.set("email", email)
        self._loaded = True
        self._refresh, self._email = refresh, email
        self._access = session["access_token"]
        self._expires = time.time() + float(session.get("expires_in", 3600))

    def _forget(self) -> None:
        for name in ("refresh_token", "email"):
            self.vault.delete(name)
        self._refresh = self._email = None
        self._access, self._expires = "", 0.0

    def _post(self, path: str, body: dict | None, bearer: str | None = None):
        import httpx

        headers = {"apikey": self.key}
        if bearer:
            headers["authorization"] = f"Bearer {bearer}"
        client = self.client or httpx.Client(timeout=20.0)
        try:
            response = client.post(self.url + path, json=body, headers=headers)
        except httpx.TransportError as exc:
            logger.warning("Supabase Auth %s: %s", path.split("?")[0], type(exc).__name__)
            raise AccountError("accounts_unreachable", status=503) from exc
        finally:
            if self.client is None:
                client.close()
        if response.status_code >= 500:
            # The artist reads one sentence; whoever runs the server needs
            # Supabase's own reason, which is usually the email that could not
            # be sent. The body names no secret.
            logger.warning(
                "Supabase Auth %s answered %s: %s",
                path.split("?")[0],
                response.status_code,
                response.text[:300],
            )
            raise AccountError("accounts_unreachable", status=503)
        return response
