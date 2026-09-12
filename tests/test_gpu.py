"""Step 5 on the GPU server, as the artist meets it: before the press, and after a refusal.

The server is not here. A proposer that raises what `RemoteProposer` raises
stands in for it, and the account is signed out in the memory vault. What is
under test is the app's side: every refusal arrives in words, and step 5 knows
before it is pressed that it needs a sign-in.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from luikki.account import Account  # noqa: E402
from luikki.colour.proposer import DistinctColourProposer  # noqa: E402
from luikki.colour.remote import RemoteProposer, RemoteUnavailable  # noqa: E402
from luikki.extract.passthrough import PassthroughExtractor  # noqa: E402
from luikki.web.app import create_app  # noqa: E402


class _Refusing(DistinctColourProposer):
    def __init__(self, code: str, **params):
        self.code, self.params = code, params

    def propose(self, request):
        raise RemoteUnavailable("refused", code=self.code, params=self.params)


def _zoned(client: TestClient, tmp_path) -> None:
    art = np.full((400, 600), 255, dtype=np.uint8)
    for x in (20, 320):
        cv2.rectangle(art, (x, 20), (x + 260, 380), 0, 3)
        cv2.circle(art, (x + 80, 140), 50, 0, 3)
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), art)
    with path.open("rb") as handle:
        client.post("/api/page", files={"file": ("page.png", handle, "image/png")})
    client.post("/api/panels")
    assert client.post("/api/zones").status_code == 200


@pytest.mark.parametrize(
    "code, expected, status",
    [
        ("not_signed_in", "gpu_sign_in", 401),
        ("no_subscription", "gpu_no_subscription", 402),
        ("too_many_devices", "gpu_too_many_devices", 403),
        ("job_elsewhere", "gpu_job_elsewhere", 409),
        ("quota_pages", "gpu_quota_pages", 429),
        ("unreachable", "gpu_unreachable", 503),
    ],
)
def test_a_gpu_refusal_reaches_the_artist_in_words(tmp_path, code, expected, status):
    app = create_app(tmp_path / "work", proposer=_Refusing(code), extractor=PassthroughExtractor())
    with TestClient(app) as client:
        _zoned(client, tmp_path)
        refused = client.post("/api/flats")

    assert refused.status_code == status
    assert refused.json()["code"] == expected


def test_a_request_the_app_got_wrong_keeps_its_code_for_the_report(tmp_path):
    app = create_app(tmp_path / "work", proposer=_Refusing("bad_ids"), extractor=PassthroughExtractor())
    with TestClient(app) as client:
        _zoned(client, tmp_path)
        refused = client.post("/api/flats")

    assert refused.json() == {"code": "gpu_refused", "params": {"reason": "bad_ids"}}


def test_step_five_knows_before_the_press_that_it_needs_a_sign_in(tmp_path):
    account = Account()
    proposer = RemoteProposer(url="http://gpu", account=account)
    app = create_app(tmp_path / "work", proposer=proposer, extractor=PassthroughExtractor(), account=account)
    with TestClient(app) as client:
        assert client.get("/api/account/status").json() == {
            "remote": True,
            "signed_in": False,
            "needs_sign_in": True,
            "quota": None,
        }


def test_a_local_proposer_needs_no_account(tmp_path):
    app = create_app(tmp_path / "work", extractor=PassthroughExtractor())
    with TestClient(app) as client:
        assert client.get("/api/account/status").json()["remote"] is False
