"""The account gate on the GPU endpoint: session tokens, then the database.

Supabase does not run here. The token is signed with a key made for the test,
and the database is an httpx transport that answers `start_panel` the way the
SQL function would. What is under test is the server's side of it: who gets
through, what reaches the GPU, and what gets charged. `schema.sql` itself is
checked in the Supabase SQL editor.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field

import numpy as np
import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
jwt = pytest.importorskip("jwt")

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from luikki.cloud.accounts import Ledger, Refused, TokenVerifier, client_ip  # noqa: E402
from luikki.cloud.server import create_server  # noqa: E402
from luikki.colour.proposer import PanelRequest  # noqa: E402
from luikki.colour.remote import RemoteProposer, RemoteUnavailable  # noqa: E402

PROJECT = "https://project.supabase.co"
SHARED = "shared-token"
USER = str(uuid.uuid4())
PAGE, GENERATION, DEVICE = (str(uuid.uuid4()) for _ in range(3))
KEY = ec.generate_private_key(ec.SECP256R1())


def _token(**claims) -> str:
    base = {"sub": USER, "aud": "authenticated", "iss": PROJECT + "/auth/v1", "exp": int(time.time()) + 3600}
    return jwt.encode(base | claims, KEY, algorithm="ES256")


def _verifier() -> TokenVerifier:
    return TokenVerifier(PROJECT, signing_key=lambda token: KEY.public_key())


@dataclass
class _Painter:
    fail: bool = False
    num_inference_steps: int = 10
    seed: int = 0
    seen: list = field(default_factory=list)
    name = "painter"

    def propose(self, request: PanelRequest) -> np.ndarray:
        self.seen.append(request)
        if self.fail:
            raise RuntimeError("no references")
        return 255 - request.line_art


@dataclass
class _Database:
    """Answers `start_panel` with `answer`, and remembers every call."""

    answer: str = "ok"
    down: bool = False
    calls: list = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down", request=request)
        function = request.url.path.rsplit("/", 1)[-1]
        self.calls.append((function, json.loads(request.content), request.headers))
        if function == "start_panel":
            return httpx.Response(200, json=self.answer)
        return httpx.Response(204)


def _gate(database: _Database, painter: _Painter, key: str = "sb_secret_test") -> TestClient:
    ledger = Ledger(PROJECT, key, client=httpx.Client(transport=httpx.MockTransport(database)))
    server = create_server(painter, token=SHARED, model_version="painter@1", verifier=_verifier(), ledger=ledger)
    return TestClient(server)


def _send(client: TestClient, token: str, device: str = DEVICE) -> np.ndarray:
    request = PanelRequest(
        line_art=np.full((9, 13, 3), 40, dtype=np.uint8),
        label_map=np.zeros((9, 13), dtype=np.int32),
        page_id=PAGE,
        generation_id=GENERATION,
    )
    remote = RemoteProposer(url="http://testserver", token=token, client=client, backoff=0, device_id=device)
    return remote.propose(request)


def test_a_signed_in_artist_is_charged_once_the_panel_is_painted():
    database, painter = _Database(), _Painter()
    _send(_gate(database, painter), _token())

    assert [call[0] for call in database.calls] == ["start_panel", "finish_panel"]
    started = database.calls[0][1]
    assert (started["p_user"], started["p_page"], started["p_generation"], started["p_device"]) == (
        USER,
        PAGE,
        GENERATION,
        DEVICE,
    )
    assert database.calls[1][1]["p_succeeded"] is True
    assert len(painter.seen) == 1


@pytest.mark.parametrize("answer", ["no_subscription", "quota_pages", "job_elsewhere", "too_many_devices"])
def test_a_refusal_never_reaches_the_gpu(answer):
    database, painter = _Database(answer=answer), _Painter()
    with pytest.raises(RemoteUnavailable) as caught:
        _send(_gate(database, painter), _token())

    assert caught.value.code == answer
    assert painter.seen == []
    assert [call[0] for call in database.calls] == ["start_panel"], "no lock was taken, none to lift"


def test_a_panel_the_gpu_could_not_paint_lifts_the_lock_and_costs_nothing():
    database, painter = _Database(), _Painter(fail=True)
    with pytest.raises(RemoteUnavailable) as caught:
        _send(_gate(database, painter), _token())

    assert caught.value.code == "proposer_refused"
    assert database.calls[-1][0] == "finish_panel"
    assert database.calls[-1][1]["p_succeeded"] is False


def test_an_account_request_names_its_device():
    database, painter = _Database(), _Painter()
    with pytest.raises(RemoteUnavailable) as caught:
        _send(_gate(database, painter), _token(), device="")

    assert caught.value.code == "bad_ids"
    assert database.calls == [] and painter.seen == []


@pytest.mark.parametrize(
    "token",
    [
        _token(exp=int(time.time()) - 10),
        _token(aud="anon"),
        _token(iss="https://another.supabase.co/auth/v1"),
        jwt.encode({"sub": USER, "aud": "authenticated", "exp": int(time.time()) + 60}, "guess", algorithm="HS256"),
        "not a token",
    ],
    ids=["expired", "audience", "issuer", "hs256", "garbage"],
)
def test_anything_short_of_a_valid_session_stops_at_the_door(token):
    database, painter = _Database(), _Painter()
    with pytest.raises(RemoteUnavailable) as caught:
        _send(_gate(database, painter), token)

    assert caught.value.code == "unauthorized"
    assert database.calls == [] and painter.seen == []


def test_the_shared_token_still_works_and_touches_no_account():
    database, painter = _Database(), _Painter()
    _send(_gate(database, painter), SHARED, device="")

    assert database.calls == []
    assert len(painter.seen) == 1


def test_a_database_that_does_not_answer_spends_no_gpu():
    database, painter = _Database(down=True), _Painter()
    with pytest.raises(RemoteUnavailable) as caught:
        _send(_gate(database, painter), _token())

    # 503 is worth retrying, so the client tries its three times first.
    assert caught.value.code == "unreachable"
    assert painter.seen == []


def test_a_secret_key_goes_on_apikey_alone_and_a_legacy_key_on_both():
    new, legacy = _Database(), _Database()
    _send(_gate(new, _Painter(), key="sb_secret_abc"), _token())
    _send(_gate(legacy, _Painter(), key="eyJlegacy"), _token())

    assert new.calls[0][2]["apikey"] == "sb_secret_abc"
    assert "authorization" not in new.calls[0][2]
    assert legacy.calls[0][2]["authorization"] == "Bearer eyJlegacy"


def test_the_verifier_reads_the_account_id():
    assert _verifier().user(_token()) == USER
    with pytest.raises(Refused):
        _verifier().user(_token(sub=None))


def test_the_callers_address_is_the_first_forwarded_hop():
    assert client_ip("203.0.113.7, 10.0.0.1", "10.0.0.1") == "203.0.113.7"
    assert client_ip(None, "198.51.100.2") == "198.51.100.2"
    assert client_ip("nonsense", "testclient") == "0.0.0.0"
