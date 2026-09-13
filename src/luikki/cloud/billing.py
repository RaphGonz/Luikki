"""Selling colours and panels: Stripe Checkout, the Customer Portal, Stripe's webhook (B5, B5b).

A FastAPI of its own, on a Modal function without a GPU (`modal_app.py`).
Opening a payment page or taking a webhook must never wake the L4, and a
webhook left waiting on a GPU cold start would time out.

The app never pays inside its window: it asks here, with the artist's session,
for a Stripe page, and opens it in the system browser (`luikki/billing.py`).
What the account is then allowed is written by the webhook alone, through the
functions of `schema.sql` that `start_panel` reads. The client is never
believed about a payment.

What is sold is `LINES` (business-plan.md §4.3): colours for a year, bought
once; panels that never expire; and Studio, the one subscription. A code is a
Stripe promotion code, typed on the payment page.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..billing import CHECKOUT_ROUTE, PORTAL_ROUTE
from .accounts import Refused, TokenVerifier, supabase_headers

logger = logging.getLogger("luikki.billing")

WEBHOOK_ROUTE = "/v1/stripe/webhook"
DONE_ROUTE = "/v1/done"
PORTAL_METADATA = ("luikki", "portal")
# A renewal arrives by webhook just after the period it extends has begun.
# Access runs this long past the period's end, so a paying studio is never
# refused in between; a cancellation still ends it at once, through `status`.
PERIOD_GRACE = timedelta(days=1)
FOUNDERS = 100


@dataclass(frozen=True)
class Line:
    """One thing Luikki sells. The server finds its price by `lookup_key`, so
    test and live mode run the same code; `cents` is only what `stripe_setup`
    creates the price with."""

    lookup_key: str
    product: str
    name: str
    cents: int
    # Years of Cobra's colours, and bought panels, which never expire.
    years: int = 0
    cases: int = 0
    monthly: bool = False


LINES = {
    "luikki": Line("luikki_colours_year", "luikki_colours", "Luikki", 6900, years=1),
    "pass": Line("luikki_pass_year", "luikki_pass", "Luikki colour pass", 3900, years=1),
    "pack": Line("luikki_pack_1000", "luikki_pack", "Luikki panel pack (1 000 panels)", 1900, cases=1000),
    "founder": Line("luikki_founder", "luikki_founder", "Luikki founder licence", 24900, years=1, cases=5000),
    "studio": Line("luikki_studio_monthly", "luikki_studio", "Luikki Studio", 14900, monthly=True),
}

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


class Purchase(BaseModel):
    line: str


def as_dict(stripe_object: Any) -> dict:
    """A Stripe object as plain dicts and lists: `subscription["items"]` is not `dict.items`."""
    return json.loads(str(stripe_object))


def checkout_options(line: str, price: str, user: str, base_url: str, customer: str | None = None) -> dict:
    """The Checkout Session a purchase starts from. `stripe_setup` opens one
    per line with these same options, so what Stripe refuses shows at setup,
    not when an artist presses Buy."""
    sold = LINES[line]
    options: dict = {
        "mode": "subscription" if sold.monthly else "payment",
        "line_items": [{"price": price, "quantity": 1}],
        "client_reference_id": user,
        # Read back by the webhook from the session Stripe holds, never from
        # the event: what was bought, and for whom.
        "metadata": {"user_id": user, "line": line},
        "allow_promotion_codes": True,
        "success_url": base_url + DONE_ROUTE,
        "cancel_url": base_url + DONE_ROUTE,
    }
    if sold.monthly:
        options["subscription_data"] = {"metadata": {"user_id": user}}
        options["payment_method_collection"] = "if_required"
    else:
        options["invoice_creation"] = {"enabled": True}
        if not customer:
            options["customer_creation"] = "always"
    if customer:
        options["customer"] = customer
    return options


def refusal(line: str, buyer: dict) -> tuple[int, str] | None:
    """Why this account may not buy this line now, or None."""
    if line not in LINES:
        return 400, "bad_line"
    if line == "studio" and buyer.get("studio"):
        return 409, "already_subscribed"
    if line == "luikki" and buyer.get("bought"):
        return 409, "already_bought"
    if line == "pass" and not buyer.get("bought"):
        # 39 € extends Luikki; it is not a cheaper way in.
        return 409, "needs_luikki"
    if line == "founder":
        if buyer.get("founder"):
            return 409, "already_bought"
        if buyer.get("founders_sold", 0) >= FOUNDERS:
            return 410, "sold_out"
    return None


def _refuse(status: int, code: str, **params) -> JSONResponse:
    return JSONResponse({"code": code, "params": params}, status_code=status)


class Store:
    """The billing functions of `schema.sql`, over the Data API with the secret key."""

    def __init__(self, project_url: str, secret_key: str, client: Any = None):
        import httpx

        self.base = project_url.rstrip("/") + "/rest/v1/rpc/"
        self.headers = supabase_headers(secret_key)
        self.client = client or httpx.Client(timeout=15.0)

    def buyer(self, user: str) -> dict:
        return self._call("buyer_status", {"p_user": user}) or {}

    def purchase(self, user: str, line: str, session: str, payment_intent: str | None, customer: str | None) -> bool:
        sold = LINES[line]
        arguments = {
            "p_user": user,
            "p_line": line,
            "p_session": session,
            "p_payment_intent": payment_intent,
            "p_customer": customer,
            "p_cases": sold.cases,
            "p_years": sold.years,
        }
        return bool(self._call("record_purchase", arguments))

    def refund(self, payment_intent: str) -> bool:
        return bool(self._call("record_refund", {"p_payment_intent": payment_intent}))

    def studio(self, user: str, status: str, period_end: datetime, customer: str) -> None:
        arguments = {"p_user": user, "p_status": status, "p_period_end": period_end.isoformat(), "p_customer": customer}
        self._call("record_studio", arguments)

    def _call(self, function: str, arguments: dict):
        response = self.client.post(self.base + function, json=arguments, headers=self.headers)
        response.raise_for_status()
        return response.json() if response.content else None


def create_billing(
    stripe: Any,
    verifier: TokenVerifier,
    store: Store,
    webhook_secret: str,
    base_url: str,
) -> FastAPI:
    """The billing endpoint. `stripe` is the SDK module, its key already set."""
    import httpx

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    found: dict[str, str | None] = {}
    if not webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET is not set: no purchase will be recorded")

    @app.exception_handler(Refused)
    def _refused(_request, refused: Refused):
        return _refuse(refused.status, refused.code, **refused.params)

    def user_of(request: Request) -> str:
        supplied = request.headers.get("authorization", "")
        if not supplied.startswith("Bearer "):
            raise Refused(401, "unauthorized")
        return verifier.user(supplied[len("Bearer ") :])

    def buyer_of(user: str) -> dict:
        try:
            return store.buyer(user)
        except httpx.HTTPError as exc:
            logger.warning("buyer_status: %s", type(exc).__name__)
            raise Refused(503, "accounts_unreachable") from exc

    def ask_stripe(call, **options):
        try:
            return call(**options)
        except stripe.StripeError as exc:
            # Stripe's message names the parameter at fault, never a key.
            logger.warning("stripe: %s", exc)
            raise Refused(502, "billing_unavailable") from exc

    def price(line: str) -> str:
        if line not in found:
            key = LINES[line].lookup_key
            prices = ask_stripe(stripe.Price.list, lookup_keys=[key], active=True, limit=1).data
            if not prices:
                logger.warning("no price %s in Stripe: run stripe_setup", key)
                raise Refused(503, "billing_unavailable")
            found[line] = prices[0].id
        return found[line]

    def portal_configuration() -> str | None:
        if "portal" not in found:
            key, value = PORTAL_METADATA
            configurations = ask_stripe(stripe.billing_portal.Configuration.list, active=True, limit=100).data
            found["portal"] = next(
                (each.id for each in configurations if as_dict(each).get("metadata", {}).get(key) == value), None
            )
        return found["portal"]

    @app.post(CHECKOUT_ROUTE)
    def checkout(request: Request, body: Purchase):
        user = user_of(request)
        buyer = buyer_of(user)
        refused = refusal(body.line, buyer)
        if refused:
            raise Refused(*refused)
        options = checkout_options(body.line, price(body.line), user, base_url, buyer.get("customer"))
        return {"url": ask_stripe(stripe.checkout.Session.create, **options).url}

    @app.post(PORTAL_ROUTE)
    def portal(request: Request):
        customer = buyer_of(user_of(request)).get("customer")
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
        kind, target = event["type"], event["data"]["object"]["id"]
        # A failure answers 500, and Stripe sends the event again.
        if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            await run_in_threadpool(record_session, target)
        elif kind.startswith("customer.subscription."):
            await run_in_threadpool(record_subscription, target)
        elif kind == "charge.refunded":
            await run_in_threadpool(record_refund, target)
        return {"received": True}

    # Each reads what Stripe holds now rather than what the event says: events
    # arrive out of order and are sent again, and only Stripe's copy is signed
    # by nobody but Stripe.

    def record_session(session_id: str) -> None:
        session = as_dict(stripe.checkout.Session.retrieve(session_id))
        if session.get("mode") != "payment":
            return  # Studio arrives by its subscription's own events.
        if session.get("payment_status") not in ("paid", "no_payment_required"):
            return  # Paid later, by `async_payment_succeeded`, or never.
        metadata = session.get("metadata") or {}
        line, user = metadata.get("line"), metadata.get("user_id")
        if line not in LINES or LINES[line].monthly or not user:
            logger.warning("session %s names no Luikki purchase", session_id)
            return
        store.purchase(user, line, session["id"], session.get("payment_intent"), session.get("customer"))

    def record_subscription(subscription_id: str) -> None:
        subscription = as_dict(stripe.Subscription.retrieve(subscription_id))
        user = subscription.get("metadata", {}).get("user_id")
        if not user:
            logger.warning("subscription %s names no account: not made by Luikki's checkout", subscription_id)
            return
        ends = max(item["current_period_end"] for item in subscription["items"]["data"])
        store.studio(
            user,
            subscription["status"],
            datetime.fromtimestamp(ends, timezone.utc) + PERIOD_GRACE,
            subscription["customer"],
        )

    def record_refund(charge_id: str) -> None:
        charge = as_dict(stripe.Charge.retrieve(charge_id))
        if not charge.get("refunded"):
            # Part of the payment: the purchase stands, and whoever refunded
            # it decides by hand what it still gives.
            logger.warning("charge %s partly refunded: nothing taken back", charge_id)
            return
        if charge.get("payment_intent"):
            store.refund(charge["payment_intent"])

    @app.get(DONE_ROUTE, response_class=HTMLResponse)
    def done():
        return DONE_PAGE

    return app
