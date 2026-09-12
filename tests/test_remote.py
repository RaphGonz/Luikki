"""The remote proposer and the GPU endpoint, talking to each other.

Cobra does not run here, so the server holds a stand-in proposer that paints
something checkable, and the account gate is a stand-in too (`test_accounts.py`
tests the real one). What is under test is the wire: every pixel that goes up
comes back exact, the zone map never goes up, and the server refuses before
the proposer is touched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np
import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from luikki.cloud.accounts import Refused  # noqa: E402
from luikki.cloud.protocol import MODEL_VERSION_HEADER, PANEL_ROUTE, encode_png  # noqa: E402
from luikki.cloud.server import create_server  # noqa: E402
from luikki.colour.proposer import PanelRequest, ReferenceImage  # noqa: E402
from luikki.colour.remote import REMOTE_URL, RemoteProposer, RemoteUnavailable  # noqa: E402
from luikki.model.masks import UNASSIGNED  # noqa: E402

TOKEN = "session"
PAGE, GENERATION, DEVICE = (str(uuid.uuid4()) for _ in range(3))


@dataclass
class Painter:
    """Inverts the line art and paints the hints over it, and remembers."""

    num_inference_steps: int = 10
    seed: int = 0
    seen: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return "painter"

    def propose(self, request: PanelRequest) -> np.ndarray:
        self.seen.append((request, self.num_inference_steps, self.seed))
        out = 255 - request.line_art
        if request.hint_mask is not None:
            out[request.hint_mask] = request.hint_colours[request.hint_mask]
        return out


class _Door:
    """Lets `TOKEN` in and nothing else."""

    def user(self, token: str) -> str:
        if token != TOKEN:
            raise Refused(401, "unauthorized")
        return "artist"


class _Ledger:
    def start(self, *args) -> None:
        pass

    def finish(self, *args) -> None:
        pass


@dataclass
class _Session:
    """Stands in for `luikki.account.Account`."""

    token: str | None = TOKEN

    def access_token(self) -> str | None:
        return self.token

    def device_id(self) -> str:
        return DEVICE


def _server(painter: Painter) -> TestClient:
    return TestClient(create_server(painter, model_version="painter@1", verifier=_Door(), ledger=_Ledger()))


def _request() -> PanelRequest:
    rng = np.random.default_rng(0)
    # Not square, so a swapped axis anywhere shows.
    line_art = rng.integers(0, 256, (37, 53, 3), dtype=np.uint8)
    mask = np.zeros((37, 53), dtype=bool)
    mask[5:12, 8:30] = True
    return PanelRequest(
        line_art=line_art,
        label_map=np.arange(37 * 53, dtype=np.int32).reshape(37, 53),
        references=[
            ReferenceImage(rng.integers(0, 256, (20, 30, 3), dtype=np.uint8), kind="sheet"),
            ReferenceImage(rng.integers(0, 256, (40, 25, 3), dtype=np.uint8), kind="page"),
        ],
        hint_colours=np.full((37, 53, 3), (200, 30, 90), dtype=np.uint8),
        hint_mask=mask,
        page_id=PAGE,
        generation_id=GENERATION,
    )


def _remote(painter: Painter, **kwargs) -> RemoteProposer:
    options = dict(url="http://testserver", account=_Session(), client=_server(painter), backoff=0)
    return RemoteProposer(**(options | kwargs))


def _post(client: TestClient, protocol: str, line_art: tuple, token: str = TOKEN):
    return client.post(
        PANEL_ROUTE,
        headers={"authorization": f"Bearer {token}"},
        data={"protocol": protocol, "page_id": PAGE, "generation_id": GENERATION, "device_id": DEVICE},
        files={"line_art": line_art},
    )


def test_a_panel_goes_up_and_comes_back_exact():
    painter = Painter()
    request = _request()

    proposal = _remote(painter, num_inference_steps=7, seed=3).propose(request)

    np.testing.assert_array_equal(proposal, Painter().propose(request))
    received, steps, seed = painter.seen[0]
    assert (steps, seed) == (7, 3)
    assert [r.kind for r in received.references] == ["sheet", "page"]
    for sent, got in zip(request.references, received.references):
        np.testing.assert_array_equal(got.pixels, sent.pixels)
    np.testing.assert_array_equal(received.hint_mask, request.hint_mask)


def test_the_zone_map_stays_on_the_artists_machine():
    painter = Painter()
    _remote(painter).propose(_request())

    received = painter.seen[0][0]
    assert (received.label_map == UNASSIGNED).all()


def test_the_page_and_the_press_travel_with_the_panel():
    painter = Painter()
    _remote(painter).propose(_request())

    received = painter.seen[0][0]
    assert (received.page_id, received.generation_id) == (PAGE, GENERATION)


def test_the_model_version_is_kept():
    remote = _remote(Painter())
    remote.propose(_request())
    assert remote.model_version == "painter@1"


@pytest.mark.parametrize("token, code", [("wrong", "unauthorized"), (None, "not_signed_in")])
def test_no_session_never_reaches_the_proposer(token, code):
    painter = Painter()
    with pytest.raises(RemoteUnavailable) as caught:
        _remote(painter, account=_Session(token)).propose(_request())
    assert caught.value.code == code
    assert painter.seen == []


def test_no_account_at_all_is_no_session():
    with pytest.raises(RemoteUnavailable) as caught:
        _remote(Painter(), account=None).propose(_request())
    assert caught.value.code == "not_signed_in"


def test_the_server_is_the_built_in_one_unless_told_otherwise(monkeypatch):
    sent = []

    def handler(request):
        sent.append(str(request.url))
        return httpx.Response(401, json={"code": "unauthorized"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    for elsewhere in (None, "http://elsewhere"):
        if elsewhere:
            monkeypatch.setenv("LUIKKI_REMOTE_URL", elsewhere)
        else:
            monkeypatch.delenv("LUIKKI_REMOTE_URL", raising=False)
        with pytest.raises(RemoteUnavailable):
            RemoteProposer(account=_Session(), client=client, backoff=0).propose(_request())

    assert sent == [REMOTE_URL + PANEL_ROUTE, "http://elsewhere" + PANEL_ROUTE]


def test_a_request_with_no_bearer_is_refused():
    painter = Painter()
    response = _server(painter).post(PANEL_ROUTE, data={"protocol": "1"})
    assert response.status_code == 401
    assert painter.seen == []


def test_an_old_client_is_told_so():
    response = _post(_server(Painter()), "0", ("a.png", encode_png(np.zeros((4, 4, 3), np.uint8)), "image/png"))
    assert response.status_code == 426
    assert response.json()["code"] == "protocol_unsupported"


def test_only_png_is_accepted():
    response = _post(_server(Painter()), "1", ("a.jpg", b"\xff\xd8\xff\xe0 not a png", "image/jpeg"))
    assert response.status_code == 400
    assert response.json()["code"] == "bad_image"


def test_a_5xx_is_retried_and_a_4xx_is_not():
    request = _request()
    answers = iter([503, 502, 200])
    calls = []

    def handler(_request):
        calls.append(1)
        status = next(answers)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, content=encode_png(request.line_art))

    remote = RemoteProposer(
        url="http://gpu",
        account=_Session(),
        backoff=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    np.testing.assert_array_equal(remote.propose(request), request.line_art)
    assert len(calls) == 3

    calls.clear()
    remote.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _r: calls.append(1) or httpx.Response(401, json={"code": "unauthorized"})
        )
    )
    with pytest.raises(RemoteUnavailable):
        remote.propose(request)
    assert len(calls) == 1


def test_no_answer_at_all_gives_up_after_the_attempts():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    remote = RemoteProposer(
        url="http://gpu",
        account=_Session(),
        backoff=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(RemoteUnavailable) as caught:
        remote.propose(_request())
    assert caught.value.code == "unreachable"
