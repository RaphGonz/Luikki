"""The Stripe objects Luikki Cloud is sold through, made once per mode (B5, B6).

    modal run -m luikki.cloud.modal_app::stripe_setup --testers 5

Run in Modal with the `luikki-stripe` secret, so the key never sits on a
laptop. Safe to rerun: each object is looked up before it is made, except the
testers' promotion codes, of which every run makes `--testers` new ones. Live
mode (B6) is the same run once the secret holds the live key.

Not made here: the webhook endpoint. Its signing secret is shown once, and
belongs in the Modal secret (`STRIPE_WEBHOOK_SECRET`), not in a run's log.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from .billing import PORTAL_METADATA, PRICE_LOOKUP_KEY, as_dict

PRODUCT_ID = "luikki_cloud"
# Provisional, like the quota: fixed once a page's real cost is measured (ROADMAP C).
MONTHLY_CENTS = 1500
CURRENCY = "eur"
TESTER_COUPON = "testeur-3-mois"
TESTER_MONTHS = 3
# How long a tester has to use a code, not how long its coupon lasts.
CODE_DAYS = 60


def ensure(stripe: Any, testers: int = 0, log: Callable[[str], None] = print) -> list[str]:
    """Make whatever is missing; return the new testers' codes."""
    product = _product(stripe)
    log(f"product {product.id} ({'live' if product.livemode else 'test'} mode)")
    log(f"price {_price(stripe).id} ({PRICE_LOOKUP_KEY})")
    log(f"portal {_portal(stripe, live=product.livemode).id}")
    coupon = _coupon(stripe)
    log(f"coupon {coupon.id}")
    codes = [_code(stripe, coupon.id) for _ in range(testers)]
    for code in codes:
        log(f"code {code}")
    return codes


def _product(stripe: Any):
    try:
        return stripe.Product.retrieve(PRODUCT_ID)
    except stripe.InvalidRequestError:
        return stripe.Product.create(id=PRODUCT_ID, name="Luikki Cloud")


def _price(stripe: Any):
    prices = stripe.Price.list(lookup_keys=[PRICE_LOOKUP_KEY], limit=1).data
    if prices:
        return prices[0]
    return stripe.Price.create(
        product=PRODUCT_ID,
        unit_amount=MONTHLY_CENTS,
        currency=CURRENCY,
        recurring={"interval": "month"},
        lookup_key=PRICE_LOOKUP_KEY,
    )


def _portal(stripe: Any, live: bool):
    key, value = PORTAL_METADATA
    for configuration in stripe.billing_portal.Configuration.list(active=True, limit=100).data:
        if as_dict(configuration).get("metadata", {}).get(key) == value:
            return configuration
    return stripe.billing_portal.Configuration.create(
        business_profile={"headline": "Luikki Cloud"},
        features={
            "customer_update": {"enabled": True, "allowed_updates": ["email", "address"]},
            "invoice_history": {"enabled": True},
            "payment_method_update": {"enabled": True},
            # A test must see access end the moment the tester cancels; a
            # paying artist keeps what they paid for until the period ends.
            "subscription_cancel": {"enabled": True, "mode": "at_period_end" if live else "immediately"},
        },
        metadata={key: value},
    )


def _coupon(stripe: Any):
    try:
        return stripe.Coupon.retrieve(TESTER_COUPON)
    except stripe.InvalidRequestError:
        return stripe.Coupon.create(
            id=TESTER_COUPON,
            name=f"Testeur ({TESTER_MONTHS} mois)",
            percent_off=100,
            duration="repeating",
            duration_in_months=TESTER_MONTHS,
        )


def _code(stripe: Any, coupon: str) -> str:
    """One code, for one tester, used once."""
    code = "TESTEUR-" + secrets.token_hex(3).upper()
    stripe.PromotionCode.create(
        promotion={"type": "coupon", "coupon": coupon},
        code=code,
        max_redemptions=1,
        expires_at=int(time.time()) + CODE_DAYS * 86400,
    )
    return code
