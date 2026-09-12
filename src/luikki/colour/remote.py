"""Cobra on a GPU somewhere else, behind the same `ColourProposer` seam.

Each `propose` is one `POST /v1/panel` (`cloud/server.py`): the panel's line
art, the references and any hints go up as PNG, the proposal raster comes
back. The zone map does not travel — Cobra never reads it, and the artist's
segmentation has no business on a server.

`LUIKKI_REMOTE_URL` and `LUIKKI_REMOTE_TOKEN` say where and as whom, read at
call time like the other `LUIKKI_*` switches.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..cloud.protocol import MODEL_VERSION_HEADER, PANEL_ROUTE, PROTOCOL, decode_png, encode_png
from .proposer import PanelRequest


class RemoteUnavailable(RuntimeError):
    """The server could not be reached, or refused the panel.

    `code` and `params` are the server's own (`cloud/server.py`), or a local
    one when no answer came back, so the web layer can put them in words.
    """

    def __init__(self, message: str, code: str, params: dict | None = None):
        super().__init__(message)
        self.code = code
        self.params = params or {}


@dataclass
class RemoteProposer:
    url: str | None = None
    token: str | None = None
    # Sent with every panel; the server mirrors `CobraProposer`'s defaults.
    num_inference_steps: int = 10
    seed: int = 0
    attempts: int = 3
    # Seconds before the second attempt, doubled for each one after.
    backoff: float = 2.0
    # An `httpx.Client` to send through instead of a fresh one; tests pass
    # FastAPI's `TestClient` here.
    client: Any = None
    # What produced the last proposal, as the server reported it.
    model_version: str = ""
    # This installation's uuid; an account may use two. Taken from `account`
    # when this is left empty.
    device_id: str = ""
    # `luikki.account.Account`: when signed in, its session replaces the
    # shared token.
    account: Any = None

    @property
    def name(self) -> str:
        return "remote"

    def propose(self, request: PanelRequest) -> np.ndarray:
        import httpx

        url = self.url or os.environ.get("LUIKKI_REMOTE_URL", "")
        # A signed-in artist goes up as themselves, and the server holds them
        # to their quota. The shared token is B1's, until every copy signs in.
        token, device = self.token, self.device_id
        if not token and self.account is not None:
            session = self.account.access_token()
            if session:
                token, device = session, device or self.account.device_id()
        token = token or os.environ.get("LUIKKI_REMOTE_TOKEN", "")
        if not url or not token:
            raise RemoteUnavailable(
                "The remote proposer needs LUIKKI_REMOTE_URL and LUIKKI_REMOTE_TOKEN.",
                code="not_configured",
            )

        files = [("line_art", ("line_art.png", encode_png(request.line_art), "image/png"))]
        files += [
            ("references", (f"reference{i}.png", encode_png(reference.pixels), "image/png"))
            for i, reference in enumerate(request.references)
        ]
        if request.hint_mask is not None and request.hint_mask.any():
            mask = np.where(request.hint_mask.astype(bool), 255, 0).astype(np.uint8)
            files += [
                ("hint_colours", ("hint_colours.png", encode_png(request.hint_colours), "image/png")),
                ("hint_mask", ("hint_mask.png", encode_png(mask), "image/png")),
            ]
        data = {
            "protocol": str(PROTOCOL),
            "steps": str(self.num_inference_steps),
            "seed": str(self.seed),
            "kinds": [reference.kind for reference in request.references],
            "page_id": request.page_id,
            "generation_id": request.generation_id,
            "device_id": device,
        }

        # A cold start loads gigabytes onto the GPU. Modal answers a request
        # that outlives 150 s with a 303 to a result URL, so redirects are
        # followed and each hop gets its own read timeout.
        client = self.client or httpx.Client(
            timeout=httpx.Timeout(180.0, connect=30.0), follow_redirects=True
        )
        try:
            response = self._send(client, url.rstrip("/") + PANEL_ROUTE, token, data, files)
        finally:
            if self.client is None:
                client.close()

        if response.status_code != 200:
            try:
                body = response.json()
                code, params = body["code"], body.get("params", {})
            except (ValueError, KeyError, TypeError):
                code, params = "http_error", {"status": response.status_code}
            raise RemoteUnavailable(
                f"The GPU server refused the panel ({code}).", code=code, params=params
            )

        proposal = decode_png(response.content)
        if proposal.shape[:2] != request.size:
            raise RemoteUnavailable(
                "The GPU server sent back a raster of the wrong size.", code="bad_response"
            )
        self.model_version = response.headers.get(MODEL_VERSION_HEADER, "")
        return proposal

    def _send(self, client, url: str, token: str, data: dict, files: list):
        """POST, retrying what may pass on a second try: no answer, or a 5xx.

        A 4xx is the server's decision about this request and is returned
        as-is — sending it again changes nothing.
        """
        import httpx

        failure = ""
        for attempt in range(self.attempts):
            if attempt:
                time.sleep(self.backoff * 2 ** (attempt - 1))
            try:
                response = client.post(
                    url, data=data, files=files, headers={"authorization": f"Bearer {token}"}
                )
            except httpx.TransportError as exc:
                failure = type(exc).__name__
                continue
            if response.status_code < 500:
                return response
            failure = f"HTTP {response.status_code}"
        raise RemoteUnavailable(
            f"The GPU server did not answer after {self.attempts} attempts ({failure}).",
            code="unreachable",
            params={"attempts": self.attempts},
        )
