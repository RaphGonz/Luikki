"""The book's reference images, on disk.

Cobra colours from references, and §1.6's whole claim is that the model is a
proposer we can swap. That makes the reference pool *the artist's material*
rather than model state: it belongs to the book, survives a page change, and
must survive the process exiting. `Session` used to hold it as a list of numpy
arrays that died with the process, which was fine while a reference was one
swatch and is not fine now that it is the input the colours actually come
from.

**What a reference is, and why this stores the image whole.** Cobra's own
examples feed it previously-coloured *pages* of the same book, but that is a
convention of their demo, not a requirement of the model: the pipeline's only
hard constraint is that every reference patch is exactly half the query's
width and height (`pipeline_cobra_pixart.py`'s `cond_refs must be twice the
size of cond_input`). A character sheet is an equally valid pool entry.

That is why nothing is cut up here. Reaching that half-size patch means
fitting the reference to the *query's* aspect, and the query is a panel whose
aspect is not known until segmentation has run — measured on the real test
pages, panels range from 0.63:1 to 3.38:1. Cutting a sheet into tiles at
upload time would bake in a guess about a panel that does not exist yet.
Store the artist's image; fit it at proposal time.

`kind` is the one thing the artist knows and we cannot infer, so it is asked
for rather than guessed. It does not change storage. It exists for the
proposal-time fitting step, where a `sheet` wants tiling across its whole area
and a `page` wants Cobra's own path.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

# `page` — a finished coloured page of this book, Cobra's own example input.
# `panel` — one coloured panel.
# `sheet` — a character sheet, the fallback when the book has nothing coloured
#   yet, and the case that needs tiling rather than cropping.
#
# `palette` is stored here too, because a palette image is an image and this is
# what holds images — but it is not a reference and is deliberately absent from
# `KINDS`. It is a strip of swatches, not a drawing: showing it to the proposer
# would hand the model a grid of flat rectangles as an example of how this book
# is coloured. `Session.reference_images` is where that separation is kept.
KINDS = ("page", "panel", "sheet")
PALETTE_KIND = "palette"
STORED_KINDS = (*KINDS, PALETTE_KIND)

INDEX_NAME = "index.json"


class UnknownKind(ValueError):
    """A reference kind outside `KINDS`."""


@dataclass
class Reference:
    """One stored image. `filename` is relative to the store's root."""

    id: int
    filename: str
    label: str
    kind: str
    added: str


def _slug(name: str) -> str:
    stem = Path(name).stem.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return (cleaned or "reference")[:40]


class ReferenceStore:
    """A folder of images plus a JSON index, loaded at startup.

    Ids are monotonic and never reused, so a palette entry or a proposal log
    that names reference 3 still means the same image after reference 2 is
    deleted.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._items: list[Reference] = []
        self._cache: dict[int, np.ndarray] = {}
        self._next_id = 1
        self.reload()

    # -- persistence -----------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    def reload(self) -> None:
        """Read the index, dropping entries whose file has gone missing.

        A missing file is not an error worth refusing to start over: the
        artist may have cleaned the folder by hand, and the alternative is an
        app that will not open.
        """
        self._items = []
        self._cache = {}
        self._next_id = 1
        if not self.index_path.exists():
            return

        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        for record in raw.get("references", []):
            reference = Reference(**record)
            if (self.root / reference.filename).exists():
                self._items.append(reference)
        self._items.sort(key=lambda r: r.id)
        # The counter is persisted rather than derived from the surviving ids:
        # deleting the newest reference and adding another would otherwise
        # hand out an id that has already meant a different image.
        self._next_id = max(
            int(raw.get("next_id", 1)),
            max((r.id for r in self._items), default=0) + 1,
        )

    def _write_index(self) -> None:
        payload = {
            "version": 1,
            "next_id": self._next_id,
            "references": [asdict(r) for r in self._items],
        }
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.index_path)

    # -- contents --------------------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def list(self) -> list[Reference]:
        return list(self._items)

    def get(self, reference_id: int) -> Reference | None:
        return next((r for r in self._items if r.id == reference_id), None)

    def path(self, reference_id: int) -> Path:
        reference = self.get(reference_id)
        if reference is None:
            raise KeyError(f"no reference {reference_id}")
        return self.root / reference.filename

    # -- mutation --------------------------------------------------------

    def add(self, source: str | Path, label: str = "", kind: str = "sheet") -> Reference:
        """Copy an image in and index it. Verifies it decodes before indexing.

        Decoding first means a truncated upload fails here, with the file
        never entering the index, rather than at the first press of Generate
        flats.
        """
        if kind not in STORED_KINDS:
            raise UnknownKind(f"kind must be one of {STORED_KINDS}, got {kind!r}")

        source = Path(source)
        with Image.open(source) as probe:
            probe.verify()

        reference_id = self._next_id
        self._next_id += 1
        filename = f"{reference_id:04d}__{_slug(label or source.name)}{source.suffix.lower()}"
        shutil.copyfile(source, self.root / filename)

        reference = Reference(
            id=reference_id,
            filename=filename,
            label=label or source.name,
            kind=kind,
            added=date.today().isoformat(),
        )
        self._items.append(reference)
        self._write_index()
        return reference

    def remove(self, reference_id: int) -> bool:
        """Delete a reference and its file. False when there was no such id."""
        reference = self.get(reference_id)
        if reference is None:
            return False

        (self.root / reference.filename).unlink(missing_ok=True)
        self._items = [r for r in self._items if r.id != reference_id]
        self._cache.pop(reference_id, None)
        self._write_index()
        return True

    # -- pixels ----------------------------------------------------------

    def image(self, reference_id: int) -> np.ndarray:
        """One reference as HxWx3 uint8 RGB.

        Decoded images are cached, which is right for the tens of references
        an artist uploads by hand and wrong for the 200+ the paper describes:
        a 4000 px page is about 50 MB as an array. The fix when the pool grows
        is not a smaller cache here but the CLIP embedding cache the proposer
        needs anyway — a reference's embeddings are what the model consumes,
        and they are three orders of magnitude smaller than its pixels.
        """
        if reference_id not in self._cache:
            with Image.open(self.path(reference_id)) as handle:
                self._cache[reference_id] = np.asarray(handle.convert("RGB"))
        return self._cache[reference_id]

    def images(self) -> list[np.ndarray]:
        """Every reference, in id order — the list `PanelRequest` takes."""
        return [self.image(r.id) for r in self._items]

    def thumbnail(self, reference_id: int, size: int = 240) -> Image.Image:
        """A small RGB copy for the reference list in the UI."""
        with Image.open(self.path(reference_id)) as handle:
            copy = handle.convert("RGB")
            copy.thumbnail((size, size))
            return copy
