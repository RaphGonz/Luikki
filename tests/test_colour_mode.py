"""Step 5's colours are the artist's choice: Cobra on the GPU, or distinct colours.

Distinct colours are never a silent fallback (ROADMAP B2): the app that runs
Cobra remotely offers both, the artist picks one, and the pick is kept.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from luikki.extract.passthrough import PassthroughExtractor  # noqa: E402
from luikki.web.app import create_app  # noqa: E402


class _Remote:
    """Stands in for `RemoteProposer`: only its name matters here."""

    name = "remote"

    def propose(self, request):
        raise AssertionError("step 5 is not pressed in these tests")


def _client(workdir) -> TestClient:
    return TestClient(create_app(workdir, proposer=_Remote(), extractor=PassthroughExtractor()))


def test_the_app_that_runs_cobra_remotely_offers_distinct_colours_too(tmp_path):
    state = _client(tmp_path / "work").get("/api/state").json()
    assert (state["proposer"], state["proposers"]) == ("remote", ["distinct", "remote"])


def test_the_choice_is_the_artists_and_survives_a_restart(tmp_path):
    work = tmp_path / "work"
    assert _client(work).put("/api/proposer", json={"name": "distinct"}).json()["proposer"] == "distinct"
    assert _client(work).get("/api/state").json()["proposer"] == "distinct"


def test_a_mode_the_app_does_not_have_is_refused(tmp_path):
    answer = _client(tmp_path / "work").put("/api/proposer", json={"name": "cobra"})
    assert (answer.status_code, answer.json()["code"]) == (409, "proposer_unknown")


def test_a_development_proposer_stands_alone(tmp_path):
    client = TestClient(create_app(tmp_path / "work", extractor=PassthroughExtractor()))
    state = client.get("/api/state").json()
    assert state["proposers"] == [state["proposer"]]
