"""The palette-construction contract, as tests.

The first three stubs (PAL-01, PAL-03, PAL-04) are the swatch-and-hand
half of palette construction — extraction from a single flat swatch,
manual CRUD, and D-09's "recolour is never a stage regression." The
final four (PROJ-03, PAL-02) are the character-sheet proposal half:
D-05's zero-prompt upload with binding deferred to accept time, and the
resolved Open Question 2 answer that unaccepted sheets live only on
disk, as files, until accepted. ``test_sheet_id_with_path_separators_is_rejected``
covers Security Domain V12 (T-01-PATH): 01-VALIDATION.md's
``::test_sheet_upload`` reference in its Requirement → Test Map resolves
to ``test_sheet_upload_returns_unpersisted_proposals`` below — the two
documents stay reconcilable under that name, not a separate alias.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-09")
def test_swatch_upload_creates_colour_n_entries():
    """PAL-01, D-16: an artist uploads a swatch image and gets named
    palette entries built from its colour chips, auto-named
    ``Colour 1..N``."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-09")
def test_hand_crud_round_trip():
    """PAL-03: an artist can create, rename, recolour and delete a
    palette entry entirely by hand, on the same screen as the extraction
    result."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-09")
def test_recolour_reports_affected_pages_and_leaves_stage_alone():
    """PAL-04, D-09: changing a palette entry's colour returns the
    number of pages affected and touches no region row and no page
    stage — a recolour is never a stage regression."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_sheet_upload_returns_unpersisted_proposals():
    """PROJ-03, PAL-02, D-05: uploading a character sheet is one
    drag-and-drop with zero prompts; the app proposes palette entries
    extracted from it, and nothing is written to the database until the
    artist accepts — proposals live only in the HTTP response."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_accept_creates_entity_and_labelled_entries():
    """PAL-02, D-05: the artist accepts a proposal by naming the
    character and the part; the entry lands as ``{character} / {part}``
    and only then gets a database row."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_reject_discards_the_pending_sheet():
    """PAL-02: rejecting a proposal discards it; nothing about a
    rejected proposal persists anywhere."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-10")
def test_sheet_id_with_path_separators_is_rejected():
    """Security Domain V12, T-01-PATH: a sheet id containing a path
    separator or traversal segment is rejected before it touches the
    filesystem."""
    ...
