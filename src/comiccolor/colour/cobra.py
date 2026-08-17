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

**Resolution.** §1.6 runs at 384-512px: mode extraction is all we do with the
raster, so pixel detail past that is wasted compute — roughly an order of
magnitude off cost and latency versus full resolution. Cobra quantises to a
fixed bucket list; `_target_resolution` picks the closest-aspect bucket and
scales it down toward `resolution`.

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
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .proposer import PanelRequest

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
    resolution: int = 512
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

        from cobra_utils.utils import (
            process_image,
            process_image_Q_varres,
            process_image_ref_varres,
        )

        self.load()

        height, width = request.size
        target_w, target_h = _target_resolution(width, height, self.resolution)

        line_art = Image.fromarray(request.line_art).convert("L").convert("RGB")
        query = line_art.resize((target_w, target_h), Image.BICUBIC)

        if not request.references:
            raise CobraUnavailable(
                "Cobra colours from reference images; upload at least one character sheet."
            )
        references = [
            process_image(Image.fromarray(ref).convert("RGB"), target_w, target_h)
            for ref in request.references
        ]

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
        # No colour hints in the barebone version: an all-black mask means
        # "nothing is hinted", which is what Cobra's own app passes when the
        # artist has not painted a hint.
        hint_mask = Image.new("RGB", (target_w // 8, target_h // 8), "black")
        hint_colour = Image.new("RGB", (target_w, target_h), "black")

        coloured = self._pipeline(
            cond_input=query,
            cond_refs=selected,
            hint_mask=hint_mask,
            hint_color=hint_colour,
            num_inference_steps=self.num_inference_steps,
            generator=generator,
        )[0][0]

        # Back to the panel's own frame: mode extraction indexes the raster by
        # the label map, so the two must agree pixel for pixel.
        return np.asarray(coloured.convert("RGB").resize((width, height), Image.BICUBIC))
