"""Signing in on this machine: an emailed code once, then a session that keeps itself.

Supabase Auth is an httpx transport here, and the system's password store is
the memory vault `conftest.py` gives every test. What is under test is what
the artist feels: the code, staying signed in across a restart, the session
renewing itself, and a session that has ended saying so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from luikki import account as account_module  # noqa: E402
from luikki.account import Account, AccountError  # noqa: E402
from luikki.cloud.protocol import encode_png  # noqa: E402
from luikki.colour.proposer import PanelRequest  # noqa: E402
from luikki.colour.remote import RemoteProposer  # noqa: E402
from luikki.extract.passthrough import PassthroughExtractor  # noqa: E402
from luikki.web.app import create_app  # noqa: E402

EMAIL = "artist@example.com"


@dataclass
class _Auth:
    """Supabase Auth, as far as signing in by code goes."""

    code: str = "123456"
    refusing_refresh: bool = False
    too_soon: bool = False
    down: bool = False
    issued: int = 0
    calls: list = field(default_factory=list)

    def _session(self) -> dict:
        self.issued += 1
        return {
            "access_token": f"access-{self.issued}",
            "refresh_token": f"refresh-{self.issued}",
            "expires_in": 3600,
            "user": {"email": EMAIL},
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down", request=request)
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.url.path, body, request.headers))
        if request.url.path == "/auth/v1/otp":
            return httpx.Response(429 if self.too_soon else 200, json={})
        if request.url.path == "/auth/v1/verify":
            if body["token"] != self.code:
                return httpx.Response(403, json={"error_code": "otp_expired"})
            return httpx.Response(200, json=self._session())
        if request.url.path == "/auth/v1/token":
            if self.refusing_refresh:
                return httpx.Response(400, json={"error_code": "refresh_token_not_found"})
            return httpx.Response(200, json=self._session())
        if request.url.path == "/auth/v1/logout":
            return httpx.Response(204)
        if request.url.path == "/rest/v1/rpc/my_status":
            return httpx.Response(200, json={"active": True, "pages_used": 3})
        return httpx.Response(404)


def _account(auth: _Auth, vault=None) -> Account:
    return Account(
        url="https://project.supabase.co",
        key="sb_publishable_test",
        vault=vault if vault is not None else account_module.KeyringVault(),
        client=httpx.Client(transport=httpx.MockTransport(auth)),
    )


def _signed_in(auth: _Auth, vault=None) -> Account:
    account = _account(auth, vault)
    account.send_code(EMAIL)
    account.verify(EMAIL, auth.code)
    return account


def test_a_code_by_email_signs_the_artist_in():
    auth = _Auth()
    account = _signed_in(auth)

    assert account.email == EMAIL
    assert account.access_token() == "access-1"
    path, body, headers = auth.calls[0]
    assert (path, body) == ("/auth/v1/otp", {"email": EMAIL, "create_user": True})
    assert headers["apikey"] == "sb_publishable_test"


def test_the_computer_stays_signed_in_across_a_restart():
    vault = account_module.KeyringVault()
    auth = _Auth()
    _signed_in(auth, vault)

    restarted = _account(auth, vault)
    assert restarted.email == EMAIL
    assert restarted.access_token() == "access-2", "a new process renews from the kept token"
    assert vault.get("refresh_token") == "refresh-2", "Supabase rotates it, and the new one is kept"


def test_a_wrong_code_signs_nobody_in():
    account = _account(_Auth())
    with pytest.raises(AccountError) as caught:
        account.verify(EMAIL, "000000")

    assert caught.value.code == "code_wrong"
    assert account.email is None and account.access_token() is None


def test_asking_again_too_soon_says_so():
    with pytest.raises(AccountError) as caught:
        _account(_Auth(too_soon=True)).send_code(EMAIL)
    assert caught.value.code == "code_too_soon"


def test_an_address_without_an_at_never_leaves_the_machine():
    auth = _Auth()
    with pytest.raises(AccountError) as caught:
        _account(auth).send_code("artist")
    assert caught.value.code == "email_invalid"
    assert auth.calls == []


def test_a_session_ended_elsewhere_ends_here(monkeypatch):
    auth = _Auth()
    account = _signed_in(auth)
    auth.refusing_refresh = True
    monkeypatch.setattr(account, "_expires", 0.0)

    with pytest.raises(AccountError) as caught:
        account.access_token()
    assert caught.value.code == "signed_out"
    assert account.email is None


def test_signing_out_forgets_the_session_but_not_the_computer():
    auth = _Auth()
    account = _signed_in(auth)
    device = account.device_id()

    account.sign_out()

    assert account.email is None and account.access_token() is None
    assert auth.calls[-1][0] == "/auth/v1/logout"
    assert account.device_id() == device


def test_what_is_left_is_asked_as_the_artist_for_this_page():
    auth = _Auth()
    account = _signed_in(auth)

    assert account.status("page-uuid") == {"active": True, "pages_used": 3}
    path, body, headers = auth.calls[-1]
    assert (path, body) == ("/rest/v1/rpc/my_status", {"p_page": "page-uuid"})
    assert headers["authorization"] == "Bearer access-1"


def test_a_signed_out_computer_asks_nothing():
    auth = _Auth()
    assert _account(auth).status("page-uuid") is None
    assert auth.calls == []


def test_an_auth_server_that_does_not_answer_is_named():
    with pytest.raises(AccountError) as caught:
        _account(_Auth(down=True)).send_code(EMAIL)
    assert caught.value.code == "accounts_unreachable"


def test_step_five_goes_up_as_the_signed_in_artist(monkeypatch):
    monkeypatch.delenv("LUIKKI_REMOTE_TOKEN", raising=False)
    account = _signed_in(_Auth())
    sent = []

    def gpu(request: httpx.Request) -> httpx.Response:
        request.read()
        sent.append(request)
        return httpx.Response(200, content=encode_png(np.zeros((4, 5, 3), dtype=np.uint8)))

    remote = RemoteProposer(
        url="http://gpu", client=httpx.Client(transport=httpx.MockTransport(gpu)), account=account
    )
    remote.propose(
        PanelRequest(line_art=np.zeros((4, 5, 3), dtype=np.uint8), label_map=np.zeros((4, 5), dtype=np.int32))
    )

    assert sent[0].headers["authorization"] == "Bearer access-1"
    assert account.device_id().encode() in sent[0].content


def test_the_rail_signs_in_and_out_through_the_api(tmp_path):
    auth = _Auth()
    app = create_app(tmp_path / "work", extractor=PassthroughExtractor(), account=_account(auth))
    with TestClient(app) as client:
        assert client.get("/api/state").json()["account"] == {"email": None}
        assert client.post("/api/account/code", json={"email": EMAIL}).status_code == 200

        refused = client.post("/api/account", json={"email": EMAIL, "code": "999999"})
        assert refused.status_code == 409
        assert refused.json()["code"] == "code_wrong"

        signed = client.post("/api/account", json={"email": EMAIL, "code": auth.code})
        assert signed.json()["account"] == {"email": EMAIL}
        assert client.request("DELETE", "/api/account").json()["account"] == {"email": None}
