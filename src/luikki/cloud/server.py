"""`POST /v1/panel`: one panel in, one proposal raster out.

The FastAPI that runs next to the GPU. It holds no state between requests and
writes nothing to disk: the panel arrives, the proposer paints it, the raster
goes back. Everything that decides whether a request may cost GPU time is
checked here, before the proposer is touched — the client is open source and
is not trusted with any of it.

B1 has one check, a shared token. Accounts, quota and devices are B2.

Errors are `{"code", "params"}`, never sentences: the words belong to the
artist's locale, on the artist's machine.
"""

from __future__ import annotations

import hmac
import threading

import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from ..colour.proposer import ColourProposer, PanelRequest, ReferenceImage
from ..model.masks import UNASSIGNED
from .protocol import MODEL_VERSION_HEADER, PANEL_ROUTE, PROTOCOL, decode_png, encode_png

# Cobra runs 10 steps. The ceiling only stops one request from holding the GPU
# for minutes.
MAX_STEPS = 50


def _refuse(status: int, code: str, **params) -> JSONResponse:
    return JSONResponse({"code": code, "params": params}, status_code=status)


def create_server(proposer: ColourProposer, token: str, model_version: str) -> FastAPI:
    """The endpoint around one loaded proposer.

    `proposer` must expose `num_inference_steps` and `seed`, which each request
    sets. An empty `token` refuses every request rather than none.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    # One panel on the GPU at a time. The steps and seed are set on the shared
    # proposer, so two requests interleaving would paint with each other's.
    gpu = threading.Lock()

    @app.middleware("http")
    async def _authorise(request: Request, call_next):
        # Middleware rather than a dependency: it answers before the body is
        # read, so an unauthorised upload costs a header, not the upload.
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not token or not hmac.compare_digest(supplied.encode(), expected.encode()):
            return _refuse(401, "unauthorized")
        return await call_next(request)

    @app.post(PANEL_ROUTE)
    def panel(
        protocol: int = Form(...),
        steps: int = Form(10),
        seed: int = Form(0),
        line_art: UploadFile = File(...),
        references: list[UploadFile] = File(default=[]),
        kinds: list[str] = Form(default=[]),
        hint_colours: UploadFile | None = File(None),
        hint_mask: UploadFile | None = File(None),
    ):
        if protocol != PROTOCOL:
            return _refuse(426, "protocol_unsupported", supported=PROTOCOL)
        if not 1 <= steps <= MAX_STEPS:
            return _refuse(400, "bad_steps", max=MAX_STEPS)
        if len(kinds) != len(references):
            return _refuse(400, "bad_references")
        if (hint_colours is None) != (hint_mask is None):
            return _refuse(400, "bad_hints")

        try:
            art = decode_png(line_art.file.read())
            refs = [
                ReferenceImage(pixels=decode_png(upload.file.read()), kind=kind)
                for upload, kind in zip(references, kinds)
            ]
            colours = mask = None
            if hint_mask is not None:
                colours = decode_png(hint_colours.file.read())
                mask = decode_png(hint_mask.file.read(), grey=True) > 0
        except ValueError:
            return _refuse(400, "bad_image")

        request = PanelRequest(
            line_art=art,
            # The zone map stays on the artist's machine. Cobra never reads it.
            label_map=np.full(art.shape[:2], UNASSIGNED, dtype=np.int32),
            references=refs,
            hint_colours=colours,
            hint_mask=mask,
        )
        with gpu:
            proposer.num_inference_steps = steps
            proposer.seed = seed
            try:
                proposal = proposer.propose(request)
            except RuntimeError as exc:
                # CobraUnavailable: a panel with no references, most often.
                return _refuse(422, "proposer_refused", detail=str(exc))

        return Response(
            encode_png(proposal),
            media_type="image/png",
            headers={MODEL_VERSION_HEADER: model_version},
        )

    return app
