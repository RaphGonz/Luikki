"""The page upload and stage-visibility contract, as tests.

PROJ-02 is "upload pages, add more over time, list preserved" — nothing
already on disk is disturbed by a later batch. PROJ-04 is "see each
page's stage; open any page," which is D-07 (a page is ``panels`` the
instant import completes) and D-11 (the stage chain is a registry an
artist can be shown, not a hardcoded frontend list) made visible over
HTTP. RESEARCH.md Pitfall 3 (server-generated filenames — never trust
``UploadFile.filename`` as a path component) and Pitfall 4 (malformed
uploads get a structured 4xx, never a bare 500) are both named here
because both are upload-handling mistakes this phase's threat model
specifically calls out. These stubs are Wave 0 scaffolding for plan
01-08.
"""

import pytest


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-08")
def test_upload_stores_a_server_generated_filename():
    """PROJ-02, RESEARCH.md Pitfall 3: every uploaded page lands on disk
    under a server-generated filename; the artist's own filename is kept
    for display only, never as a path component."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-08")
def test_upload_rejects_a_non_image_with_4xx():
    """PROJ-02, RESEARCH.md Pitfall 4: a file that is not a readable
    image is rejected with a 400 carrying the UI-SPEC error sentence,
    never a bare 500."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-08")
def test_stage_field_is_panels_after_upload():
    """PROJ-04, D-07: every page reports a single stage value, which is
    ``panels`` the instant its upload completes."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-08")
def test_adding_pages_later_preserves_existing_pages():
    """PROJ-02: uploading a second batch of pages to a volume leaves
    every page from the first batch exactly where it was."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-08")
def test_volume_crud_round_trip():
    """D-03: an artist creates, renames and deletes volumes and files
    pages into them."""
    ...


@pytest.mark.skip(reason="Wave 0 scaffold — filled by plan 01-08")
def test_pipeline_stages_endpoint_lists_eight_stages():
    """PROJ-04, D-11: the eight-stage chain and each stage's runner
    availability are served from the registry, never hardcoded in the
    frontend."""
    ...
