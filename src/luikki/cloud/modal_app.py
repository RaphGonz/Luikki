"""Luikki on Modal: Cobra on an L4, and the billing endpoint on a CPU.

    # in the dashboard: luikki-supabase (SUPABASE_URL, SUPABASE_SECRET_KEY)
    #                   luikki-stripe (STRIPE_SECRET_KEY, then STRIPE_WEBHOOK_SECRET)
    modal run -m luikki.cloud.modal_app::download        # once: weights into the Volume
    modal run -m luikki.cloud.modal_app::stripe_setup    # once per Stripe mode, --testers N for codes
    modal deploy -m luikki.cloud.modal_app               # prints both endpoint URLs

Then write the URLs into `REMOTE_URL` (`colour/remote.py`) and `BILLING_URL`
(`billing.py`), or set `LUIKKI_REMOTE_URL` / `LUIKKI_BILLING_URL` to try another
deployment, and sign in from Account.

Only the standard library and `modal` at module level: Modal imports this file
again inside the container, before anything is known about what it holds.
"""

from __future__ import annotations

import os
from pathlib import Path

import modal

_REPO = Path(__file__).resolve().parents[3]
COBRA_DIR = "/root/Cobra"
WEIGHTS_DIR = "/weights"

app = modal.App("luikki-cobra")
weights = modal.Volume.from_name("luikki-weights", create_if_missing=True)
supabase = modal.Secret.from_name("luikki-supabase", required_keys=["SUPABASE_URL", "SUPABASE_SECRET_KEY"])
stripe_keys = modal.Secret.from_name("luikki-stripe", required_keys=["STRIPE_SECRET_KEY"])

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # Cobra's own pins (`third_party/Cobra/requirements.txt`), minus what
        # only its gradio demo uses. `cobra_utils` imports matplotlib.
        "torch==2.5.1",
        "torchvision==0.20.1",
        "accelerate==1.5.2",
        "einops==0.8.1",
        "huggingface-hub==0.30.2",
        "matplotlib==3.10.1",
        "numpy==1.26.4",
        "peft==0.15.0",
        "Pillow==11.1.0",
        "safetensors==0.5.3",
        "transformers==4.48.3",
        # Luikki's side: `colour/__init__` pulls scikit-image, and the server.
        "opencv-python-headless==4.11.0.86",
        "scikit-image",
        "fastapi",
        "python-multipart",
        # Accounts: session tokens and the database (`cloud/accounts.py`).
        "httpx",
        "pyjwt[crypto]",
    )
    .add_local_dir(
        _REPO / "third_party" / "Cobra", COBRA_DIR, copy=True, ignore=[".git", "examples", "figs"]
    )
    .run_commands(f"pip install -e {COBRA_DIR}/diffusers")
    .env({"HF_HOME": f"{WEIGHTS_DIR}/huggingface"})
    .add_local_python_source("luikki")
)

# The billing endpoint's: no torch and no GPU, so a cold start takes seconds.
billing_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "httpx", "pyjwt[crypto]", "stripe==15.6.1")
    .add_local_python_source("luikki")
)


@app.function(image=image, volumes={WEIGHTS_DIR: weights}, timeout=3600)
def download() -> None:
    """Put exactly the files `CobraProposer.load` reads into the Volume."""
    from huggingface_hub import snapshot_download

    from luikki.colour.cobra import WEIGHT_FILES

    for repo, patterns in WEIGHT_FILES.items():
        print(snapshot_download(repo_id=repo, allow_patterns=patterns))
    weights.commit()


@app.cls(
    image=image,
    gpu="L4",
    volumes={WEIGHTS_DIR: weights},
    secrets=[supabase],
    # Serving reads the Volume and nothing else: a missing file fails the
    # load instead of quietly downloading on a paid GPU.
    env={"HF_HUB_OFFLINE": "1"},
    # How long an idle GPU stays up, billed, waiting for the next panel. Long
    # enough to cover a pause between presses in a session. At 300 s one page
    # (teddy, 3 panels) held the container 6 min: ~1 min of cold start and
    # generation, 5 min idle — ~$0.08 on an L4, five sixths of it waiting.
    scaledown_window=120,
    # The quota caps each account; the GPUs cap the whole bill. Two, so a
    # tester is not left waiting behind another's whole page.
    max_containers=2,
    timeout=600,
    startup_timeout=900,
)
class Cobra:
    @modal.enter()
    def load(self) -> None:
        from luikki.colour.cobra import CobraProposer

        self.proposer = CobraProposer(repo_dir=Path(COBRA_DIR))
        self.proposer.load()

    @modal.asgi_app()
    def web(self):
        from luikki.cloud.accounts import Ledger, TokenVerifier
        from luikki.cloud.server import create_server

        project = os.environ["SUPABASE_URL"]
        return create_server(
            self.proposer,
            model_version=f"cobra-line@{self.proposer.revision[:12]}",
            verifier=TokenVerifier(project),
            ledger=Ledger(project, os.environ["SUPABASE_SECRET_KEY"]),
        )


@app.function(image=billing_image, secrets=[supabase, stripe_keys])
@modal.asgi_app()
def billing():
    import stripe

    from luikki.billing import BILLING_URL
    from luikki.cloud.accounts import TokenVerifier
    from luikki.cloud.billing import Store, create_billing

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    project = os.environ["SUPABASE_URL"]
    return create_billing(
        stripe,
        verifier=TokenVerifier(project),
        store=Store(project, os.environ["SUPABASE_SECRET_KEY"]),
        webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        base_url=BILLING_URL,
    )


@app.function(image=billing_image, secrets=[stripe_keys])
def stripe_setup(testers: int = 0) -> None:
    import stripe

    from luikki.cloud.stripe_setup import ensure

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    ensure(stripe, testers)
