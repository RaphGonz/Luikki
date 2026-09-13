"""The Stripe objects Luikki is sold through, made once per mode (B5, B5b, B6).

    modal run -m luikki.cloud.modal_app::stripe_setup --testers 5

Run in Modal with the `luikki-stripe` secret, so the key never sits on a
laptop. Safe to rerun: each object is looked up before it is made, except the
promotion codes, of which every run makes `--testers` new ones. Live mode (B6)
is the same run once the secret holds the live key. Last, it opens a checkout
per line with the server's own options and expires it unused, so whatever
Stripe refuses shows here and not when an artist presses Buy.

Not made here: the webhook endpoint. Its signing secret is shown once, and
belongs in the Modal secret (`STRIPE_WEBHOOK_SECRET`), not in a run's log.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from ..billing import BILLING_URL
from .billing import LINES, PORTAL_METADATA, Line, as_dict, checkout_options

# What Luikki is, for tax: a downloaded app whose colours are made by a service
# in the cloud, sold to professionals ("SaaS - electronic download - business
# use"). Managed Payments, on by default on the account, refuses a checkout for
# a product without an eligible code
# (docs.stripe.com/payments/managed-payments/eligibility). Business or personal
# use only matters for sales in the US.
TAX_CODE = "txcd_10103101"
CURRENCY = "eur"
# B5's monthly subscription, sold before panels were the unit.
RETIRED_PRICES = ("luikki_cloud_monthly",)
# A code is 100 % off, once: a free Luikki, for someone Raph chooses.
CODE_COUPON = "code-luikki-offert"
# How long someone has to use a code.
CODE_DAYS = 60


def ensure(stripe: Any, testers: int = 0, log: Callable[[str], None] = print) -> list[str]:
    """Make whatever is missing; return the new codes."""
    live = False
    prices = {}
    for name, line in LINES.items():
        product = _product(stripe, line)
        live = bool(product.livemode)
        prices[name] = _price(stripe, line).id
        log(f"{name}: product {product.id}, price {prices[name]} ({line.lookup_key})")
    log(f"mode: {'live' if live else 'test'}, tax code {TAX_CODE}")
    for key in RETIRED_PRICES:
        for price in stripe.Price.list(lookup_keys=[key], limit=1).data:
            if price.active:
                stripe.Price.modify(price.id, active=False)
                log(f"retired price {price.id} ({key})")
    log(f"portal {_portal(stripe, live).id}")
    coupon = _coupon(stripe)
    for name, price in prices.items():
        _try_checkout(stripe, name, price)
        log(f"{name}: checkout accepted")
    codes = [_code(stripe, coupon.id) for _ in range(testers)]
    for code in codes:
        log(f"code {code}")
    return codes


def _product(stripe: Any, line: Line):
    try:
        product = stripe.Product.retrieve(line.product)
    except stripe.InvalidRequestError:
        return stripe.Product.create(id=line.product, name=line.name, tax_code=TAX_CODE)
    if product.tax_code != TAX_CODE:
        product = stripe.Product.modify(line.product, tax_code=TAX_CODE)
    return product


def _price(stripe: Any, line: Line):
    prices = stripe.Price.list(lookup_keys=[line.lookup_key], limit=1).data
    if prices:
        return prices[0]
    options: dict = {
        "product": line.product,
        "unit_amount": line.cents,
        "currency": CURRENCY,
        "lookup_key": line.lookup_key,
    }
    if line.monthly:
        options["recurring"] = {"interval": "month"}
    return stripe.Price.create(**options)


def _portal(stripe: Any, live: bool):
    key, value = PORTAL_METADATA
    for configuration in stripe.billing_portal.Configuration.list(active=True, limit=100).data:
        if as_dict(configuration).get("metadata", {}).get(key) == value:
            return configuration
    return stripe.billing_portal.Configuration.create(
        business_profile={"headline": "Luikki"},
        features={
            "customer_update": {"enabled": True, "allowed_updates": ["email", "address"]},
            "invoice_history": {"enabled": True},
            "payment_method_update": {"enabled": True},
            # A test must see access end the moment the studio cancels; a
            # paying studio keeps what it paid for until the period ends.
            "subscription_cancel": {"enabled": True, "mode": "at_period_end" if live else "immediately"},
        },
        metadata={key: value},
    )


def _coupon(stripe: Any):
    try:
        return stripe.Coupon.retrieve(CODE_COUPON)
    except stripe.InvalidRequestError:
        return stripe.Coupon.create(
            id=CODE_COUPON,
            name="Luikki offert",
            percent_off=100,
            duration="once",
            applies_to={"products": [LINES["luikki"].product]},
        )


def _try_checkout(stripe: Any, line: str, price: str) -> None:
    """Open a checkout the way the server does, then expire it unused."""
    session = stripe.checkout.Session.create(**checkout_options(line, price, "stripe-setup-check", BILLING_URL))
    stripe.checkout.Session.expire(session.id)


def _code(stripe: Any, coupon: str) -> str:
    """One code, for one person, used once."""
    code = "LUIKKI-" + secrets.token_hex(3).upper()
    stripe.PromotionCode.create(
        promotion={"type": "coupon", "coupon": coupon},
        code=code,
        max_redemptions=1,
        expires_at=int(time.time()) + CODE_DAYS * 86400,
    )
    return code
