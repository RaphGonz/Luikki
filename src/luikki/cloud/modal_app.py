"""Luikki on Modal: the billing endpoint, on a CPU.

    # in the dashboard: luikki-supabase (SUPABASE_URL, SUPABASE_SECRET_KEY)
    #                   luikki-stripe (STRIPE_SECRET_KEY, then STRIPE_WEBHOOK_SECRET)
    modal run -m luikki.cloud.modal_app::stripe_setup    # once per Stripe mode, --testers N for codes
    modal deploy -m luikki.cloud.modal_app               # prints the endpoint URL

Then write the URL into `BILLING_URL` (`billing.py`), or set
`LUIKKI_BILLING_URL` to try another deployment.

Cobra and its GPU are gone (ROADMAP G1): Luikki proposes no colour. The app
keeps its old name, `luikki-cobra`, because the endpoint's URL is made from it
and every installed app holds that URL. The `luikki-weights` Volume holds
Cobra's weights and nothing reads it any more: delete it from the dashboard.

Only the standard library and `modal` at module level: Modal imports this file
again inside the container, before anything is known about what it holds.
"""

from __future__ import annotations

import os

import modal

app = modal.App("luikki-cobra")
supabase = modal.Secret.from_name("luikki-supabase", required_keys=["SUPABASE_URL", "SUPABASE_SECRET_KEY"])
stripe_keys = modal.Secret.from_name("luikki-stripe", required_keys=["STRIPE_SECRET_KEY"])

# No torch and no GPU, so a cold start takes seconds.
billing_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "httpx", "pyjwt[crypto]", "stripe==15.6.1")
    .add_local_python_source("luikki")
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
