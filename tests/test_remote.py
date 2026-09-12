"""The remote proposer and the GPU endpoint, talking to each other.

Cobra does not run here, so the server holds a stand-in proposer that paints
something checkable. What is under test is the wire: every pixel that goes up
comes back exact, the zone map never goes up, and the server refuses before
the proposer is touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from luikki.cloud.protocol import MODEL_VERSION_HEADER, PANEL_ROUTE, encode_png  # noqa: E402
from luikki.cloud.server import create_server  # noqa: E402
from luikki.colour.proposer import PanelRequest, ReferenceImage  # noqa: E402
from luikki.colour.remote import RemoteProposer, RemoteUnavailable  # noqa: E402
from luikki.model.masks import UNASSIGNED  # noqa: E402

TOKEN = "secret"


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
    )


def _remote(painter: Painter, **kwargs) -> RemoteProposer:
    client = TestClient(create_server(painter, token=TOKEN, model_version="painter@1"))
    options = dict(url="http://testserver", token=TOKEN, client=client, backoff=0)
    return RemoteProposer(**(options | kwargs))


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
    request = _request()
    request.page_id, request.generation_id = "page-uuid", "press-uuid"
    _remote(painter).propose(request)

    received = painter.seen[0][0]
    assert (received.page_id, received.generation_id) == ("page-uuid", "press-uuid")


def test_the_model_version_is_kept():
    remote = _remote(Painter())
    remote.propose(_request())
    assert remote.model_version == "painter@1"


@pytest.mark.parametrize("token", ["wrong", ""])
def test_a_bad_token_never_reaches_the_proposer(token, monkeypatch):
    # No token means none at all: the real one in the machine's environment
    # would otherwise stand in for it.
    monkeypatch.delenv("LUIKKI_REMOTE_TOKEN", raising=False)
    painter = Painter()
    with pytest.raises(RemoteUnavailable) as caught:
        _remote(painter, token=token or None).propose(_request())
    assert caught.value.code == ("unauthorized" if token else "not_configured")
    assert painter.seen == []


def test_a_server_without_a_token_refuses_everyone():
    painter = Painter()
    client = TestClient(create_server(painter, token="", model_version="x"))
    response = client.post(
        PANEL_ROUTE,
        headers={"authorization": "Bearer "},
        data={"protocol": "1"},
        files={"line_art": ("a.png", encode_png(np.zeros((4, 4, 3), np.uint8)), "image/png")},
    )
    assert response.status_code == 401
    assert painter.seen == []


def test_an_old_client_is_told_so():
    client = TestClient(create_server(Painter(), token=TOKEN, model_version="x"))
    response = client.post(
        PANEL_ROUTE,
        headers={"authorization": f"Bearer {TOKEN}"},
        data={"protocol": "0"},
        files={"line_art": ("a.png", encode_png(np.zeros((4, 4, 3), np.uint8)), "image/png")},
    )
    assert response.status_code == 426
    assert response.json()["code"] == "protocol_unsupported"


def test_only_png_is_accepted():
    client = TestClient(create_server(Painter(), token=TOKEN, model_version="x"))
    response = client.post(
        PANEL_ROUTE,
        headers={"authorization": f"Bearer {TOKEN}"},
        data={"protocol": "1"},
        files={"line_art": ("a.jpg", b"\xff\xd8\xff\xe0 not a png", "image/jpeg")},
    )
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
        url="http://gpu", token=TOKEN, backoff=0, client=httpx.Client(transport=httpx.MockTransport(handler))
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
        url="http://gpu", token=TOKEN, backoff=0, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(RemoteUnavailable) as caught:
        remote.propose(_request())
    assert caught.value.code == "unreachable"
