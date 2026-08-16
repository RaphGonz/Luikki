"""The thin runner: stage seams call into ``Store``, no orchestration.

D-10 requires this file to be individually triggerable per stage — it must
never walk the chain, run upstream stages implicitly, or advance a page past
its own gate. The obvious "helpful" change a later contributor would make
here — have ``run_stage`` chase ``next_stage`` and keep going — is exactly
the thing the design forbids: every stage stays individually triggerable and
individually inspectable (flatting-pipeline-spec.md §315).

Only ``run_import`` is implemented this phase (D-11); every other stage is
declared in ``stages.STAGES`` with ``runner=None`` and refuses to run via
``StageNotImplementedError`` until a later phase fills it in.

Imports only from ``..model`` at module level, never from ``.stages`` — the
registry (``stages.py``) imports ``run_import`` from this module at import
time, so a module-level import running the other way would be circular.
``run_stage`` resolves ``stage_for`` with a local import instead, which is
safe because by call time both modules are fully loaded.
"""

from __future__ import annotations

from ..model import Page, Panel, PipelineStage, ProtectedKind, ProtectedMask, Store

# UI-SPEC §4's exact copy for the non-blocking inline banner a detection
# failure surfaces as. Lives in exactly one place so the route layer and this
# module can never drift apart on the wording.
BUBBLE_DETECTION_FAILED_MESSAGE = (
    "Bubble detection failed — you can still draw protected masks by hand."
)


class StageNotImplementedError(RuntimeError):
    """Raised when a stage with no runner (D-11) is asked to run."""


class BubbleDetectionFailed(RuntimeError):
    """Raised when ``detect_bubbles`` itself errors (02-RESEARCH.md Pitfall 6).

    This exists so the *route* layer can turn a detection failure into a
    non-blocking banner (02-UI-SPEC.md §4) instead of a wall the artist is
    trapped behind. It is not an error the artist gets stuck on: PROT-02's
    hand-drawing is the guaranteed fallback, and D-24 already means the
    artist inspects for SFX by hand regardless of whether bubble detection
    succeeded.
    """


def run_import(store: Store, page: Page) -> None:
    """Advance a freshly uploaded page past the import boundary.

    Import means "the file is on disk and the row exists" — there is
    nothing for the artist to review at that boundary yet, so the page
    auto-advances straight to ``panels`` rather than sitting at ``import``
    (01-UI-SPEC.md §1, D-11). This is the whole job: no segmentation, no
    validation beyond what already happened at upload time.
    """
    page.stage = PipelineStage.PANELS
    store.set_page_stage(page.id, PipelineStage.PANELS)


def run_panels(store: Store, page: Page) -> None:
    """Detect panel boxes, seed each as a four-vertex polygon, persist in
    reading order (PAN-01).

    ``segment_panels``'s default ``PanelParams`` already carry D-18's
    lowered ``min_solidity`` floor and UI-SPEC §7's ``reading="ltr"``
    default — both are the dataclass's own defaults, not re-specified here.

    Re-running deletes the page's existing panels first, so a re-run
    replaces rather than accumulates duplicates.

    Does not set ``page.stage``. The registry declares, it never
    orchestrates (D-10, this module's docstring) — ``run_import`` advances
    the page because import has nothing for the artist to review, but
    panels do, and the artist's own "Confirm & Continue" gate is what
    advances a page past this stage, not the runner that produced the
    artefact under review.
    """
    # Imports are local, not module-level: this keeps `pipeline` importable
    # without pulling OpenCV in for every caller, matching this module's
    # existing import-direction discipline (see module docstring).
    from ..segmentation.panels import box_to_polygon, segment_panels
    from ..segmentation.preprocess import load_line_art

    image_path = store.path.parent / page.source_path
    if not image_path.is_file():
        raise FileNotFoundError(
            f"page {page.id}: source image not found at {image_path}"
        )

    line_mask, _grey = load_line_art(image_path)
    boxes = segment_panels(line_mask)  # already reading-ordered

    store.delete_panels_for_page(page.id)
    for index, box in enumerate(boxes):
        store.add_panel(
            Panel(
                page_id=page.id,
                x=box.x,
                y=box.y,
                width=box.width,
                height=box.height,
                reading_order=index,
                polygon=box_to_polygon(box),
            )
        )


def run_protected(store: Store, page: Page) -> None:
    """Detect speech bubbles, trace each into an editable polygon, persist
    as page-scoped protected masks (PROT-01).

    Zero detected bubbles is not a failure — a splash page with no dialogue
    is a legitimate page. A detection *error*, by contrast, is not
    swallowed: it is re-raised as ``BubbleDetectionFailed`` so the route
    layer can distinguish "this page genuinely has no bubbles" from
    "detection broke" and surface the latter as a banner rather than a
    silent empty result.

    Re-running deletes the page's existing protected masks first, so a
    re-run replaces rather than accumulates duplicates.

    Does not set ``page.stage``, for the same reason as ``run_panels``.
    """
    from ..segmentation.bubbles import detect_bubbles, mask_to_polygon
    from ..segmentation.preprocess import load_line_art
    from ..segmentation.protected import protected_bbox_and_area

    image_path = store.path.parent / page.source_path
    if not image_path.is_file():
        raise FileNotFoundError(
            f"page {page.id}: source image not found at {image_path}"
        )

    line_mask, grey = load_line_art(image_path)

    try:
        bubbles = detect_bubbles(grey, line_mask)
    except Exception as exc:
        raise BubbleDetectionFailed(BUBBLE_DETECTION_FAILED_MESSAGE) from exc

    height, width = line_mask.shape
    store.delete_protected_for_page(page.id)
    for mask in bubbles:
        polygon = mask_to_polygon(mask)
        if len(polygon) < 3:
            continue
        area, bbox = protected_bbox_and_area(polygon, width, height)
        store.add_protected_mask(
            ProtectedMask(
                page_id=page.id,
                # D-24: detector-proposed masks are always bubbles by
                # construction — SFX gets no automatic proposal this phase,
                # and the artist picks the kind only when hand-drawing.
                kind=ProtectedKind.BUBBLE,
                polygon=polygon,
                # UI-SPEC §3: detector output renders with a dashed outline
                # until the artist reshapes it.
                touched=False,
                area=area,
                bbox=bbox,
            )
        )


def run_stage(store: Store, page: Page, name: PipelineStage) -> None:
    """Run exactly the named stage. Never walks the chain (D-10).

    Looks the stage up in the registry, raises ``StageNotImplementedError``
    if it has no runner yet, and otherwise calls that runner and stops. Does
    not run upstream stages implicitly and does not advance the page past
    this stage's own gate — the registry declares, it does not orchestrate
    (flatting-pipeline-spec.md §315).
    """
    from .stages import stage_for  # local: avoids a module-level cycle with stages.py

    stage = stage_for(name)
    if stage.runner is None:
        raise StageNotImplementedError(f"stage {name.value!r} has no runner yet")
    stage.runner(store, page)
