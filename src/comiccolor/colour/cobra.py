"""Cobra as a `ColourProposer`. §1.6 — wrap as a black box, do not modify the DiT.

**Status: written against Cobra @ 48d6168, never executed.** This machine has
a 6 GB GTX 1660 Ti and no `diffusers`/`transformers`/`peft` installed; the
model was deliberately not installed here. Everything below mirrors Cobra's
own `app.py` (`load_ckpt` and `colorize_image`) with gradio and the shadow
refinement pass removed. Treat it as a wiring diagram that compiles, and
verify it on the GPU machine before trusting a single pixel.

**What was removed, and why it is safe to remove.** Cobra's `colorize_image`
follows the pipeline call with a `MultiHiddenResNetModel` pass that re-encodes
the result at 1.5x through the VAE to recover high-frequency detail. We read
one modal colour per zone (`snap.zone_modes`) and throw the raster away, so
high-frequency detail is exactly the part that cannot reach the output. Both
the `shadow_GSRP` weights and that pass are skipped. `expand_under_lines`
already handles what happens at line edges.

**Resolution.** §1.6 argued for 384-512px on the grounds that mode extraction
is all we do with the raster, so pixel detail past that is wasted compute. That
reasoning is sound and the default still ignores it, because it assumes the
raster is *usable*. Measured on `diagonal_page.jpg` panel 0 (1065x493, aspect
2.16) the 512 proposal is RGB noise and the 1024 one is correct flats; a
near-square panel survives 512, so the failure tracks how far the panel is from
the buckets' own aspect range.

Upstream `get_rate` returns its bucket *unscaled*, at ~1024. `_target_resolution`
scales the long side toward `resolution`, so a wide panel at 512 lands near
512x320 — far below anything the DiT trained on, and it collapses. A mode taken
over noise is noise, so the cheaper raster is not cheaper at all.

**Licence.** `pretrained_model_name_or_path` below is pinned to the diffusers
repo `PixArt-alpha/PixArt-XL-2-1024-MS`, which is `openrail++`. The
`hf.co/PixArt-alpha/PixArt-alpha` raw-`.pth` mirror is `agpl-3.0` and
"research purpose only". Do not repoint this string.

## Plugging it in on the GPU machine

    git clone https://github.com/zhuang2002/Cobra.git third_party/Cobra
    pip install -e third_party/Cobra/diffusers   # the patched fork, required
    pip install -r third_party/Cobra/requirements.txt

    from comiccolor.colour.cobra import CobraProposer
    proposer = CobraProposer()          # downloads JunhaoZhuang/Cobra on first use
    session.proposer = proposer

The web layer takes `COMICCOLOR_PROPOSER=cobra` to do the same thing without
an edit.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path

import cv2
import numpy as np

from .proposer import PanelRequest, ReferenceImage

_REPO_DIR = Path(__file__).resolve().parents[3] / "third_party" / "Cobra"

# Cobra's own bucket list (app.py `ratio_list`), used at its native 1024-class
# scale. `_target_resolution` picks from these and then scales down.
_RATIO_BUCKETS = (
    (800, 800), (768, 896), (704, 928), (672, 960), (640, 1024),
    (608, 1056), (576, 1088), (576, 1184),
    (896, 768), (928, 704), (960, 672), (1024, 640),
    (1056, 608), (1088, 576), (1184, 576),
)


# Exactly the keys Cobra's `load_ckpt` forwards into CausalSparseDiTModel and
# CausalSparseDiTControlModel. Kept as a list rather than **config because
# `get_pixart_config` also returns `_class_name`, `_diffusers_version` and
# friends, which the constructors do not accept.
_DIT_CONFIG_KEYS = (
    "num_attention_heads", "attention_head_dim", "in_channels", "out_channels",
    "num_layers", "dropout", "norm_num_groups", "cross_attention_dim",
    "attention_bias", "sample_size", "patch_size", "activation_fn",
    "num_embeds_ada_norm", "upcast_attention", "norm_type",
    "norm_elementwise_affine", "norm_eps", "caption_channels", "attention_type",
)


@contextmanager
def _vendored_prompt_tensors(repo_dir: Path):
    """Resolve Cobra's hardcoded `./prompt_tensor/` loads against `repo_dir`.

    `pipeline_cobra_pixart.py` loads its fixed prompt embedding with a literal
    relative path, so the pipeline only runs when the process CWD happens to be
    the vendored repo. We serve HTTP from wherever the artist started us, and a
    process-global `os.chdir` around a GPU call is not something a server can
    do safely, so the two paths are redirected for the duration of the call and
    nothing else is touched.

    Cobra takes no prompt — the embedding is a constant baked in upstream,
    which is why the pipeline loads no text encoder at all.
    """
    import torch

    original = torch.load

    def load(f, *args, **kwargs):
        if isinstance(f, str) and "prompt_tensor" in f and not Path(f).is_absolute():
            f = str(repo_dir / "prompt_tensor" / Path(f).name)
        return original(f, *args, **kwargs)

    torch.load = load
    try:
        yield
    finally:
        torch.load = original
# Cobra's own tolerance (`cobra_utils.utils.process_image`): an aspect within
# 15% of the target is close enough to resize outright. Reused rather than
# invented, so a page-shaped reference against a page-shaped query keeps
# taking exactly the path Cobra's own app takes.
_ASPECT_TOLERANCE = 0.15

# How many tiles one reference may contribute. A sheet is a montage of
# separate drawings and earns more of them; a page or a panel is one
# composition. Unvalidated starting values in the sense `colour/extract.py`
# uses the phrase -- hypotheses to measure on the GPU machine, not spec.
_TILE_BUDGET = {"sheet": 6, "page": 3, "panel": 3}

# -- finding the drawings on a character sheet ------------------------------
# Closing radius as a fraction of the sheet's shorter side, used to join the
# strokes of one drawing. Small on purpose: measured on `laurine_ref.jpg`,
# 0.002 finds the 13 drawings the artist put there, while 0.012 fuses the
# whole sheet into 2 blobs.
_SUBJECT_MERGE_FRAC = 0.002
# Anything under this share of the sheet is a stray mark, not a drawing.
_SUBJECT_MIN_AREA_FRAC = 0.002
# Anything this far from paper white counts as drawn.
_SUBJECT_INK_DELTA = 18
# Breathing room around a drawing before its window is fitted to the target.
_SUBJECT_MARGIN = 1.15
# Two windows overlapping by more than this are the same view twice.
_SUBJECT_MAX_OVERLAP = 0.6
# Below this many drawings the sheet is not a montage -- one big drawing, or a
# photograph -- and the grid is the honest fallback.
_MIN_SUBJECTS = 2


# Both knobs above are read through these, not used directly, so a run can
# change them without a code edit. `COMICCOLOR_TILE_OVERLAP=1.1` keeps every
# window a sheet offers, since IoU never exceeds 1; `COMICCOLOR_TILE_BUDGET=12`
# raises the ceiling on how many tiles one reference contributes. They exist to
# answer one question — whether the retrieval pool is what makes a page come
# back bland — and the answer belongs in `reports/`, not in a default.
def _max_overlap() -> float:
    return float(os.environ.get("COMICCOLOR_TILE_OVERLAP", _SUBJECT_MAX_OVERLAP))


def _budget_for(kind: str) -> int:
    override = os.environ.get("COMICCOLOR_TILE_BUDGET")
    if override:
        return int(override)
    return _TILE_BUDGET.get(kind, _TILE_BUDGET["sheet"])


def _letterbox(image, target_w: int, target_h: int):
    """Fit an image into the target frame on white, without distorting it.

    Returns `(canvas, box)`, where `box` is where the image landed so the
    coloured result can be cropped back out of it.

    This replaces a plain `resize` to the bucket, and the reason is measured.
    Cobra quantises to a fixed list of aspect buckets topping out at 2.06:1,
    while real panels on the test pages run from 0.63:1 to 3.38:1: thirteen of
    twenty-three were being squashed by more than 5% and one by 1.69x. A
    squashed face is a face the model has to recognise through a distortion
    that never occurs in comics, and recognising faces is what we are paying
    it for. White costs a little resolution instead, and resolution is the one
    thing this pipeline does not need -- the raster is reduced to one modal
    colour per zone and thrown away.

    It is also what makes a non-rectangular panel work. `PanelRequest.line_art`
    arrives masked to the panel's polygon, so an L-shaped or a round panel is
    already white outside its own outline; letterboxing is the same operation
    one level out, where the shape happens to be the bounding box.
    """
    from PIL import Image

    width, height = image.size
    scale = min(target_w / width, target_h / height)
    inner = (max(1, round(width * scale)), max(1, round(height * scale)))
    left = (target_w - inner[0]) // 2
    top = (target_h - inner[1]) // 2

    canvas = Image.new("RGB", (target_w, target_h), "white")
    canvas.paste(image.resize(inner, Image.BICUBIC), (left, top))
    return canvas, (left, top, left + inner[0], top + inner[1])


def _subjects(image) -> list[tuple[int, int, int, int, float, float]]:
    """The separate drawings on a character sheet.

    A sheet is drawings with paper between them, so the drawings are the
    connected components of not-paper — the same reasoning the bubble detector
    uses for what white encloses, one level up. Returns
    `(x, y, width, height, centre_x, centre_y)` per drawing, largest first.
    """
    pixels = np.asarray(image.convert("RGB")).astype(np.int16)
    drawn = (255 - pixels).max(axis=2) > _SUBJECT_INK_DELTA

    radius = max(1, int(_SUBJECT_MERGE_FRAC * min(drawn.shape)))
    kernel = np.ones((2 * radius + 1,) * 2, np.uint8)
    merged = cv2.morphologyEx(drawn.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    merged = cv2.dilate(merged, kernel)

    count, _, stats, centroids = cv2.connectedComponentsWithStats(merged, connectivity=8)
    floor = _SUBJECT_MIN_AREA_FRAC * drawn.size

    found = []
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] < floor:
            continue
        found.append(
            (
                int(stats[i, cv2.CC_STAT_LEFT]),
                int(stats[i, cv2.CC_STAT_TOP]),
                int(stats[i, cv2.CC_STAT_WIDTH]),
                int(stats[i, cv2.CC_STAT_HEIGHT]),
                float(centroids[i][0]),
                float(centroids[i][1]),
            )
        )
    return sorted(found, key=lambda s: -s[2] * s[3])


def _window_for(subject, target_ratio: float, size: tuple[int, int]):
    """A target-shaped window around one drawing, centred on it and clipped.

    The window is grown to the target's aspect rather than the drawing being
    padded to it, so the patch stays full of artwork: whatever else on the
    sheet falls inside the window comes along, which is context, not waste.
    """
    _, _, width, height, centre_x, centre_y = subject
    sheet_w, sheet_h = size

    need_w, need_h = width * _SUBJECT_MARGIN, height * _SUBJECT_MARGIN
    if need_w / need_h > target_ratio:
        window_w, window_h = need_w, need_w / target_ratio
    else:
        window_h, window_w = need_h, need_h * target_ratio

    # Clip to the sheet, keeping the aspect exact.
    window_w = min(window_w, sheet_w, sheet_h * target_ratio)
    window_h = window_w / target_ratio

    left = int(round(min(max(centre_x - window_w / 2, 0), sheet_w - window_w)))
    top = int(round(min(max(centre_y - window_h / 2, 0), sheet_h - window_h)))
    return (left, top, left + int(round(window_w)), top + int(round(window_h)))


def _overlap(a, b) -> float:
    """Intersection over union of two boxes."""
    inner_w = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    inner_h = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = inner_w * inner_h
    if not intersection:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / (area_a + area_b - intersection)


def _subject_tiles(image, target_w: int, target_h: int, budget: int) -> list:
    """Tiles placed on the drawings rather than on a grid.

    A grid stride over a character sheet gives bands: against a tall panel the
    Laurine sheet comes back as two vertical halves, each a wall of seven
    figures too small to match anything. Placing the windows on the drawings
    instead gives one character per patch at a readable size, which is the
    unit the CLIP retrieval is actually comparing against a panel.

    Returns `[]` when the sheet is not a montage — one large drawing, or a
    photograph — and the caller falls back to the grid.
    """
    found = _subjects(image)
    if len(found) < _MIN_SUBJECTS:
        return []

    from PIL import Image

    target_ratio = target_w / target_h
    kept: list = []
    for subject in found:
        window = _window_for(subject, target_ratio, image.size)
        if any(_overlap(window, other) > _max_overlap() for other in kept):
            continue
        kept.append(window)
        if len(kept) >= budget:
            break

    return [image.crop(w).resize((target_w, target_h), Image.BICUBIC) for w in kept]


def _tiles(image, target_w: int, target_h: int, budget: int, kind: str = "sheet") -> list:
    """Cut a reference into patches the model can read.

    A `sheet` is a montage, so its tiles are placed on the drawings
    (`_subject_tiles`). A `page` or a `panel` is one composition with no paper
    between its subjects, so there is nothing to place tiles on and the grid
    below is used instead.

    The grid path covers the reference with target-shaped tiles, losing
    nothing.

    Cobra's `process_image` centre-crops a reference whose aspect is far from
    the query's, which for a tall character sheet against a wide panel keeps a
    horizontal band through the middle and throws away the heads and the feet.
    That is a preprocessing choice in a helper, not a property of the model --
    the pipeline only ever requires a patch to be half the query's size -- so
    it is replaced here rather than inherited.

    A reference is *not* letterboxed. White padding would put white in the
    patches the retrieval step ranks and the DiT reads, and a reference exists
    to supply colour. Tiling keeps every pixel of it at full scale instead.

    Tiles overlap by half, so a face landing on a seam still falls whole in
    the neighbouring tile. Retrieval then picks whichever tiles match; that is
    what retrieval is for.
    """
    from PIL import Image

    if kind == "sheet":
        placed = _subject_tiles(image, target_w, target_h, budget)
        if placed:
            return placed

    width, height = image.size
    target_ratio = target_w / target_h
    ratio = width / height

    if abs(ratio - target_ratio) / target_ratio < _ASPECT_TOLERANCE:
        return [image.resize((target_w, target_h), Image.BICUBIC)]

    if ratio > target_ratio:  # source is wider: cut vertical slices
        extent = max(1, round(height * target_ratio))
        span = width
    else:  # source is taller: cut horizontal bands
        extent = max(1, round(width / target_ratio))
        span = height

    stride = max(1, extent // 2)
    starts = list(range(0, max(1, span - extent + 1), stride))
    if starts[-1] + extent < span:
        starts.append(span - extent)

    # Keep the tiles nearest the middle: on a character sheet the outer edge
    # is margin, and on a page it is usually gutter.
    if len(starts) > budget:
        middle = (span - extent) / 2
        starts = sorted(sorted(starts, key=lambda s: abs(s - middle))[:budget])

    boxes = (
        [(s, 0, s + extent, height) for s in starts]
        if ratio > target_ratio
        else [(0, s, width, s + extent) for s in starts]
    )
    return [image.crop(box).resize((target_w, target_h), Image.BICUBIC) for box in boxes]


class CobraUnavailable(RuntimeError):
    """Raised when the repo, the patched diffusers fork, or a GPU is missing.

    A distinct type so the web layer can answer "Cobra is not installed on this
    machine" instead of surfacing an ImportError traceback to the artist.
    """


def _target_resolution(width: int, height: int, resolution: int) -> tuple[int, int]:
    """Closest-aspect Cobra bucket, scaled so the long side is ~`resolution`."""
    aspect = width / max(height, 1)
    bucket = min(_RATIO_BUCKETS, key=lambda wh: abs(wh[0] / wh[1] - aspect))
    scale = resolution / max(bucket)
    # The VAE is 8x and the DiT patches on top of that; keep both sides on a
    # multiple of 32 so nothing downstream has to pad.
    return (
        max(32, int(round(bucket[0] * scale / 32)) * 32),
        max(32, int(round(bucket[1] * scale / 32)) * 32),
    )


@dataclass
class CobraProposer:
    """Cobra behind the `ColourProposer` protocol.

    Weights load once, on the first `propose`, not in `__init__` — constructing
    the proposer must stay free so the web layer can select it at import time
    without pulling 5 GB.
    """

    repo_dir: Path = _REPO_DIR
    # 1024, not §1.6's 384-512 — see the Resolution note above: wide panels
    # come back as noise at 512.
    resolution: int = 1024
    num_inference_steps: int = 10
    top_k: int = 3
    seed: int = 0
    device: str = "cuda"

    _loaded: bool = False

    @property
    def name(self) -> str:
        return "cobra"

    # -- loading ---------------------------------------------------------

    def _import_cobra(self):
        """Put Cobra's repo (and its patched diffusers) on the path."""
        if not self.repo_dir.exists():
            raise CobraUnavailable(
                f"Cobra not vendored at {self.repo_dir}. "
                "git clone https://github.com/zhuang2002/Cobra.git"
            )
        if str(self.repo_dir) not in sys.path:
            sys.path.insert(0, str(self.repo_dir))
        try:
            import torch  # noqa: F401
            from diffusers import CausalSparseDiTModel  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise CobraUnavailable(
                "Cobra needs its patched diffusers fork: "
                f"pip install -e {self.repo_dir / 'diffusers'}"
            ) from exc

    def load(self) -> None:
        """Mirrors Cobra's `load_ckpt`, minus the shadow refinement model."""
        if self._loaded:
            return

        self._import_cobra()

        import torch
        from diffusers import (
            CausalSparseDiTControlModel,
            CausalSparseDiTModel,
            CobraPixArtAlphaPipeline,
            PixArtTransformer2DModel,
        )
        from huggingface_hub import snapshot_download
        from peft import LoraConfig
        from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection

        from cobra_utils.utils import get_pixart_config, init_causal_dit

        if self.device == "cuda" and not torch.cuda.is_available():
            raise CobraUnavailable("Cobra requires an NVIDIA GPU; there is no CPU path.")

        weights = Path(
            snapshot_download(repo_id="JunhaoZhuang/Cobra", repo_type="model")
        )
        dtype = torch.float16

        # Pinned to the diffusers repo — see the licence note in the module
        # docstring. Do not repoint.
        base = "PixArt-alpha/PixArt-XL-2-1024-MS"
        # `get_pixart_config` carries diffusers bookkeeping keys the model
        # constructors reject, so take only the ones upstream passes through.
        raw = get_pixart_config()
        config = {key: raw[key] for key in _DIT_CONFIG_KEYS}

        transformer = PixArtTransformer2DModel.from_pretrained(base, subfolder="transformer")
        causal_dit = init_causal_dit(CausalSparseDiTModel(**config), transformer)
        controlnet = CausalSparseDiTControlModel(cond_chanels=9, **config)
        del transformer

        lora_rank = 128
        causal_dit.add_adapter(
            LoraConfig(
                r=lora_rank,
                lora_alpha=lora_rank,
                init_lora_weights="gaussian",
                target_modules=[
                    "to_k", "to_q", "to_v", "to_out.0", "proj_in", "proj_out",
                    "ff.net.0.proj", "ff.net.2", "proj", "linear", "linear_1", "linear_2",
                ],
            )
        )
        causal_dit.load_state_dict(
            torch.load(weights / "line_ckpt" / "transformer_lora_pos.bin", map_location="cpu"),
            strict=False,
        )
        controlnet.load_state_dict(
            torch.load(weights / "line_ckpt" / "controlnet.bin", map_location="cpu"),
            strict=True,
        )

        causal_dit.to(self.device, dtype=dtype)
        controlnet.to(self.device, dtype=dtype)

        self._pipeline = CobraPixArtAlphaPipeline.from_pretrained(
            base,
            transformer=causal_dit,
            controlnet=controlnet,
            safety_checker=None,
            torch_dtype=dtype,
        ).to(self.device)

        self._image_processor = CLIPImageProcessor()
        self._image_encoder = CLIPVisionModelWithProjection.from_pretrained(
            weights / "image_encoder"
        ).to(self.device)
        self._loaded = True

    # -- inference -------------------------------------------------------

    def propose(self, request: PanelRequest) -> np.ndarray:
        """Mirrors Cobra's `colorize_image`, minus gradio and the shadow pass."""
        import torch
        import torch.nn.functional as F
        from PIL import Image

        # Must precede the `cobra_utils` import: `load` -> `_import_cobra` is
        # what puts the vendored repo on `sys.path`, so importing from it
        # first is a ModuleNotFoundError on every call but the second.
        self.load()

        from cobra_utils.utils import (
            process_image_Q_varres,
            process_image_ref_varres,
        )

        height, width = request.size
        target_w, target_h = _target_resolution(width, height, self.resolution)

        line_art = Image.fromarray(request.line_art).convert("L").convert("RGB")
        query, inner = _letterbox(line_art, target_w, target_h)

        if not request.references:
            raise CobraUnavailable(
                "Cobra colours from reference images; upload at least one character sheet."
            )
        references: list = []
        for reference in request.references:
            references += _tiles(
                Image.fromarray(reference.pixels).convert("RGB"),
                target_w,
                target_h,
                _budget_for(reference.kind),
                reference.kind,
            )

        # Retrieval: rank reference patches against query patches by CLIP
        # cosine similarity and keep the top k per query patch. This is the
        # "broader references" half of the paper — the DiT only ever sees the
        # patches this step selected.
        with torch.no_grad():
            query_patches = process_image_Q_varres(query, target_w, target_h)
            reference_patches: list = []
            for reference in references:
                reference_patches += process_image_ref_varres(reference, target_w, target_h)

            def embed(images):
                pixels = self._image_processor(images=images, return_tensors="pt").pixel_values
                pixels = pixels.to(self._image_encoder.device, dtype=self._image_encoder.dtype)
                return self._image_encoder(pixels).image_embeds

            similarity = F.cosine_similarity(
                embed(query_patches).unsqueeze(1),
                embed([p.convert("RGB") for p in reference_patches]).unsqueeze(0),
                dim=-1,
            )
            ranked = torch.argsort(similarity, descending=True, dim=1).tolist()
            selected = [
                [
                    reference_patches[index].resize((target_w // 2, target_h // 2)).convert("RGB")
                    for index in row[: self.top_k]
                ]
                for row in ranked
            ]

        generator = torch.Generator(device=self.device).manual_seed(self.seed)
        # No colour hints in the barebone version. An all-black *mask* is
        # right — `draw_square` sets 255 where the artist painted, so 0 is
        # "nothing is hinted".
        #
        # The hint *colour* is not a blank canvas though. Upstream binds it to
        # the line drawing itself and paints swatches onto that, so it is
        # always mostly-white line art; the pipeline VAE-encodes it and
        # concatenates it into the control input ungated by the mask
        # (`pipeline_cobra_pixart.py` L739/L791). Passing black feeds the
        # controlnet a confident "this panel is black" and the generation
        # comes back dark and desaturated whatever the references say.
        hint_mask = Image.new("RGB", (target_w // 8, target_h // 8), "black")
        hint_colour = query

        if request.hint_mask is not None and request.hint_mask.any():
            # Paint the hinted colours onto the line art, exactly as
            # `draw_square` paints swatches onto the drawing upstream, and mark
            # the same pixels in the mask.
            #
            # The hints arrive in the panel's frame, so they have to be
            # letterboxed exactly as the line art was: scaled to `inner` and
            # pasted at the same offset. Resizing them to the full target
            # instead would stretch every hint across the white margin and
            # misalign it with the art it marks.
            #
            # NEAREST throughout: interpolating a hint invents colours nobody
            # asked for and softens the mask edge onto pixels that were never
            # hinted. The mask reaches the pipeline at latent resolution, so a
            # hint thinner than 8 panel-pixels cannot be expressed at all.
            inner_size = (inner[2] - inner[0], inner[3] - inner[1])

            mask_img = Image.new("L", (target_w, target_h), 0)
            mask_img.paste(
                Image.fromarray(
                    np.where(request.hint_mask.astype(bool), 255, 0).astype(np.uint8)
                ).resize(inner_size, Image.NEAREST),
                inner[:2],
            )
            colours_img = Image.new("RGB", (target_w, target_h), "white")
            colours_img.paste(
                Image.fromarray(
                    np.ascontiguousarray(request.hint_colours, dtype=np.uint8)
                ).resize(inner_size, Image.NEAREST),
                inner[:2],
            )

            where = np.asarray(mask_img, dtype=np.uint8) > 0
            painted = np.asarray(query, dtype=np.uint8).copy()
            painted[where] = np.asarray(colours_img, dtype=np.uint8)[where]

            hint_colour = Image.fromarray(painted)
            hint_mask = mask_img.convert("RGB").resize(
                (target_w // 8, target_h // 8), Image.NEAREST
            )

        with _vendored_prompt_tensors(self.repo_dir):
            coloured = self._pipeline(
                cond_input=query,
                cond_refs=selected,
                hint_mask=hint_mask,
                hint_color=hint_colour,
                num_inference_steps=self.num_inference_steps,
                generator=generator,
            )[0][0]

        # Back to the panel's own frame: mode extraction indexes the raster by
        # the label map, so the two must agree pixel for pixel. The white
        # margin `_letterbox` added comes off first -- whatever the model
        # painted out there is not part of this panel.
        panel = coloured.convert("RGB").crop(inner)
        return np.asarray(panel.resize((width, height), Image.BICUBIC))
