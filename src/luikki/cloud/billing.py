"""Subscriptions: Stripe Checkout, the Customer Portal and Stripe's webhook (B5).

A FastAPI of its own, on a Modal function without a GPU (`modal_app.py`).
Opening a payment page or taking a webhook must never wake the L4, and a
webhook left waiting on a GPU cold start would time out.

The app never pays inside its window: it asks here, with the artist's session,
for a Stripe page, and opens it in the system browser (`luikki/billing.py`).
What the account is then allowed is written by the webhook alone, into
`subscriptions` (`schema.sql`), which `start_panel` reads. The client is never
believed about a subscription.

A tester's code is a Stripe promotion code, typed on the payment page. With
`payment_method_collection="if_required"`, a 100 % code asks for no card.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from ..billing import CHECKOUT_ROUTE, PORTAL_ROUTE
from .accounts import Refused, TokenVerifier, supabase_headers

logger = logging.getLogger("luikki.billing")

WEBHOOK_ROUTE = "/v1/stripe/webhook"
DONE_ROUTE = "/v1/done"
# Found by this key rather than by id, so test and live mode run the same code.
PRICE_LOOKUP_KEY = "luikki_cloud_monthly"
PORTAL_METADATA = ("luikki", "portal")
ACTIVE = ("active", "trialing")
# A renewal arrives by webhook just after the period it extends has begun.
# Access runs this long past the period's end, so a paying artist is never
# refused in between; a cancellation still ends it at once, through `status`.
PERIOD_GRACE = timedelta(days=1)

DONE_PAGE = """<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Luikki</title>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;box-sizing:border-box;
             background:#2b2238;color:#f1edf6;font:16px/1.5 system-ui,sans-serif;text-align:center">
<main>
  <p style="color:#E4A280;font-size:20px;font-weight:600">Luikki</p>
  <p>Vous pouvez fermer cet onglet et revenir dans Luikki.</p>
  <p style="opacity:.7">You can close this tab and go back to Luikki.</p>
</main>
</body>
</html>
"""


def as_dict(stripe_object: Any) -> dict:
    """A Stripe object as plain dicts and lists: `subscription["items"]` is not `dict.items`."""
    return json.loads(str(stripe_object))


def _refuse(status: int, code: str, **params) -> JSONResponse:
    return JSONResponse({"code": code, "params": params}, status_code=status)


def _active(row: dict) -> bool:
    return row.get("status") in ACTIVE and datetime.fromisoformat(row["period_end"]) > datetime.now(timezone.utc)


class Subscriptions:
    """The `subscriptions` table, over the Data API with the secret key."""

    def __init__(self, project_url: str, secret_key: str, client: Any = None):
        import httpx

        self.base = project_url.rstrip("/") + "/rest/v1/subscriptions"
        self.headers = supabase_headers(secret_key)
        self.client = client or httpx.Client(timeout=15.0)

    def get(self, user: str) -> dict | None:
        response = self.client.get(
            self.base,
            params={"user_id": f"eq.{user}", "select": "status,plan,period_end,stripe_customer_id"},
            headers=self.headers,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def put(self, user: str, status: str, period_end: datetime, customer: str) -> None:
        """The account's one row, replaced: a Stripe subscription makes the plan `paid`."""
        response = self.client.post(
            self.base,
            params={"on_conflict": "user_id"},
            json={
                "user_id": user,
                "status": status,
                "plan": "paid",
                "period_end": period_end.isoformat(),
                "stripe_customer_id": customer,
            },
            headers=self.headers | {"prefer": "resolution=merge-duplicates,return=minimal"},
        )
        response.raise_for_status()


def create_billing(
    stripe: Any,
    verifier: TokenVerifier,
    subscriptions: Subscriptions,
    webhook_secret: str,
    base_url: str,
) -> FastAPI:
    """The billing endpoint. `stripe` is the SDK module, its key already set."""
    import httpx

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    found: dict[str, str | None] = {}
    if not webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET is not set: no subscription will be recorded")

    @app.exception_handler(Refused)
    def _refused(_request, refusal: Refused):
        return _refuse(refusal.status, refusal.code, **refusal.params)

    def user_of(request: Request) -> str:
        supplied = request.headers.get("authorization", "")
        if not supplied.startswith("Bearer "):
            raise Refused(401, "unauthorized")
        return verifier.user(supplied[len("Bearer ") :])

    def row_of(user: str) -> dict:
        try:
            return subscriptions.get(user) or {}
        except httpx.HTTPError as exc:
            logger.warning("subscriptions: %s", type(exc).__name__)
            raise Refused(503, "accounts_unreachable") from exc

    def ask_stripe(call, **options):
        try:
            return call(**options)
        except stripe.StripeError as exc:
            # Stripe's message names the parameter at fault, never a key.
            logger.warning("stripe: %s", exc)
            raise Refused(502, "billing_unavailable") from exc

    def price() -> str:
        if "price" not in found:
            prices = ask_stripe(stripe.Price.list, lookup_keys=[PRICE_LOOKUP_KEY], active=True, limit=1).data
            if not prices:
                logger.warning("no price %s in Stripe: run stripe_setup", PRICE_LOOKUP_KEY)
                raise Refused(503, "billing_unavailable")
            found["price"] = prices[0].id
        return found["price"]

    def portal_configuration() -> str | None:
        if "portal" not in found:
            key, value = PORTAL_METADATA
            configurations = ask_stripe(stripe.billing_portal.Configuration.list, active=True, limit=100).data
            found["portal"] = next(
                (each.id for each in configurations if as_dict(each).get("metadata", {}).get(key) == value), None
            )
        return found["portal"]

    @app.post(CHECKOUT_ROUTE)
    def checkout(request: Request):
        user = user_of(request)
        row = row_of(user)
        customer = row.get("stripe_customer_id")
        if customer and _active(row):
            raise Refused(409, "already_subscribed")
        options = {
            "mode": "subscription",
            "line_items": [{"price": price(), "quantity": 1}],
            "client_reference_id": user,
            # Carried by every subscription event, so the webhook knows the
            # account without looking anything up.
            "subscription_data": {"metadata": {"user_id": user}},
            "allow_promotion_codes": True,
            "payment_method_collection": "if_required",
            "success_url": base_url + DONE_ROUTE,
            "cancel_url": base_url + DONE_ROUTE,
        }
        if customer:
            options["customer"] = customer
        return {"url": ask_stripe(stripe.checkout.Session.create, **options).url}

    @app.post(PORTAL_ROUTE)
    def portal(request: Request):
        customer = row_of(user_of(request)).get("stripe_customer_id")
        if not customer:
            raise Refused(404, "no_customer")
        options = {"customer": customer, "return_url": base_url + DONE_ROUTE}
        configuration = portal_configuration()
        if configuration:
            options["configuration"] = configuration
        return {"url": ask_stripe(stripe.billing_portal.Session.create, **options).url}

    @app.post(WEBHOOK_ROUTE)
    async def webhook(request: Request):
        if not webhook_secret:
            # An empty secret would accept a signature anyone can make.
            return _refuse(503, "webhook_unconfigured")
        payload = await request.body()
        try:
            stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), webhook_secret)
        except (ValueError, stripe.SignatureVerificationError):
            return _refuse(400, "bad_signature")
        event = json.loads(payload)
        if event["type"].startswith("customer.subscription."):
            # A failure answers 500, and Stripe sends the event again.
            await run_in_threadpool(record, event["data"]["object"]["id"])
        return {"received": True}

    def record(subscription_id: str) -> None:
        """Write what Stripe holds now. Events arrive out of order and are sent
        again, so the subscription is read afresh, not taken from the event."""
        subscription = as_dict(stripe.Subscription.retrieve(subscription_id))
        user = subscription.get("metadata", {}).get("user_id")
        if not user:
            logger.warning("subscription %s names no account: not made by Luikki's checkout", subscription_id)
            return
        ends = max(item["current_period_end"] for item in subscription["items"]["data"])
        subscriptions.put(
            user,
            subscription["status"],
            datetime.fromtimestamp(ends, timezone.utc) + PERIOD_GRACE,
            subscription["customer"],
        )

    @app.get(DONE_ROUTE, response_class=HTMLResponse)
    def done():
        return DONE_PAGE

    return app
