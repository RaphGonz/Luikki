"""Selling colours and panels: the billing server's doors, and the app's buttons.

Stripe does not run here. `_Stripe` answers the SDK calls the server makes
with real `StripeObject`s, and webhooks are signed the way Stripe signs them,
with a secret made for the test. The database is an httpx transport that
answers the billing functions of `schema.sql` and remembers every call; the
SQL itself is checked in the Supabase SQL editor, and `stripe_setup.py`
against Stripe in test mode.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
jwt = pytest.importorskip("jwt")
stripe = pytest.importorskip("stripe")

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from luikki import billing  # noqa: E402
from luikki.account import AccountError  # noqa: E402
from luikki.cloud.accounts import TokenVerifier  # noqa: E402
from luikki.cloud.billing import FOUNDERS, LINES, PERIOD_GRACE, WEBHOOK_ROUTE, Store, create_billing  # noqa: E402

PROJECT = "https://project.supabase.co"
USER = str(uuid.uuid4())
KEY = ec.generate_private_key(ec.SECP256R1())
WEBHOOK_SECRET = "whsec_test"
BASE = "https://billing.test"
PERIOD_END = int(time.time()) + 30 * 86400


def _bearer() -> dict:
    claims = {"sub": USER, "aud": "authenticated", "iss": PROJECT + "/auth/v1", "exp": int(time.time()) + 3600}
    return {"authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="ES256")}


def _object(values: dict):
    return stripe.StripeObject.construct_from(values, "sk_test")


class _Database:
    """The billing functions of `schema.sql`, answered from `buyer`."""

    def __init__(self, **buyer):
        self.buyer = {"customer": None, "studio": False, "bought": False, "founder": False, "founders_sold": 0} | buyer
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        function = request.url.path.rsplit("/", 1)[-1]
        arguments = json.loads(request.content)
        if function == "buyer_status":
            return httpx.Response(200, json=self.buyer)
        self.calls.append((function, arguments))
        if function == "record_studio":
            return httpx.Response(204)
        return httpx.Response(200, json=True)


class _Stripe:
    """The part of the SDK the server calls. Webhook signatures are checked for real."""

    StripeError = stripe.StripeError
    SignatureVerificationError = stripe.SignatureVerificationError
    Webhook = stripe.Webhook

    def __init__(self, session: dict | None = None, subscription: dict | None = None, charge: dict | None = None):
        self.sessions: list[dict] = []
        self.portals: list[dict] = []
        configurations = [{"id": "bpc_other", "metadata": {}}, {"id": "bpc_luikki", "metadata": {"luikki": "portal"}}]
        self.Price = SimpleNamespace(list=lambda lookup_keys, **_: _object({"data": [{"id": "price_" + lookup_keys[0]}]}))
        self.Subscription = SimpleNamespace(retrieve=lambda _id: _object(subscription))
        self.Charge = SimpleNamespace(retrieve=lambda _id: _object(charge))
        self.checkout = SimpleNamespace(
            Session=SimpleNamespace(create=self._checkout, retrieve=lambda _id: _object(session))
        )
        self.billing_portal = SimpleNamespace(
            Session=SimpleNamespace(create=self._portal),
            Configuration=SimpleNamespace(list=lambda **_: _object({"data": configurations})),
        )

    def _checkout(self, **options):
        self.sessions.append(options)
        return _object({"url": "https://checkout.stripe.test/c/1"})

    def _portal(self, **options):
        self.portals.append(options)
        return _object({"url": "https://billing.stripe.test/p/1"})


def _server(fake: _Stripe, database: _Database, secret: str = WEBHOOK_SECRET) -> TestClient:
    store = Store(PROJECT, "sb_secret_test", client=httpx.Client(transport=httpx.MockTransport(database)))
    verifier = TokenVerifier(PROJECT, signing_key=lambda token: KEY.public_key())
    return TestClient(create_billing(fake, verifier=verifier, store=store, webhook_secret=secret, base_url=BASE))


def _buy(fake: _Stripe, database: _Database, line: str):
    return _server(fake, database).post("/v1/checkout", headers=_bearer(), json={"line": line})


def _signed(kind: str, target: str, secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict]:
    # Only an id: the server reads the object again from Stripe.
    event = {"id": "evt_1", "type": kind, "data": {"object": {"id": target}}}
    payload = json.dumps(event).encode()
    stamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return payload, {"stripe-signature": f"t={stamp},v1={signature}", "content-type": "application/json"}


def _session(**changes) -> dict:
    return {
        "id": "cs_1",
        "mode": "payment",
        "payment_status": "paid",
        "payment_intent": "pi_1",
        "customer": "cus_1",
        "metadata": {"user_id": USER, "line": "pack"},
    } | changes


def _subscription(**changes) -> dict:
    return {
        "id": "sub_1",
        "status": "active",
        "customer": "cus_1",
        "metadata": {"user_id": USER},
        "items": {"data": [{"current_period_end": PERIOD_END}]},
    } | changes


# -- opening a payment page ----------------------------------------------------


def test_a_one_time_purchase_is_a_payment_for_this_account_with_an_invoice():
    fake = _Stripe()
    answer = _buy(fake, _Database(), "luikki")

    assert answer.json() == {"url": "https://checkout.stripe.test/c/1"}
    [session] = fake.sessions
    assert session["mode"] == "payment"
    assert session["line_items"] == [{"price": "price_luikki_colours_year", "quantity": 1}]
    assert session["metadata"] == {"user_id": USER, "line": "luikki"}
    assert session["client_reference_id"] == USER
    assert session["allow_promotion_codes"] is True
    assert session["invoice_creation"] == {"enabled": True}
    assert session["customer_creation"] == "always"
    assert "subscription_data" not in session


def test_studio_is_the_one_subscription():
    fake = _Stripe()
    _buy(fake, _Database(), "studio")

    [session] = fake.sessions
    assert session["mode"] == "subscription"
    assert session["subscription_data"] == {"metadata": {"user_id": USER}}
    assert session["payment_method_collection"] == "if_required"
    assert "invoice_creation" not in session


def test_a_second_purchase_is_made_by_the_same_customer():
    fake = _Stripe()
    _buy(fake, _Database(customer="cus_1", bought=True), "pack")
    assert fake.sessions[0]["customer"] == "cus_1"
    assert "customer_creation" not in fake.sessions[0]


def test_buying_needs_a_session():
    fake = _Stripe()
    answer = _server(fake, _Database()).post("/v1/checkout", json={"line": "luikki"})
    assert answer.status_code == 401
    assert fake.sessions == []


@pytest.mark.parametrize(
    ("line", "buyer", "status", "code"),
    [
        ("studio", {"studio": True}, 409, "already_subscribed"),
        ("luikki", {"bought": True}, 409, "already_bought"),
        ("pass", {"bought": False}, 409, "needs_luikki"),
        ("founder", {"founder": True, "bought": True}, 409, "already_bought"),
        ("founder", {"founders_sold": FOUNDERS}, 410, "sold_out"),
        ("lifetime", {}, 400, "bad_line"),
    ],
)
def test_what_an_account_may_not_buy_never_reaches_stripe(line, buyer, status, code):
    fake = _Stripe()
    answer = _buy(fake, _Database(**buyer), line)
    assert (answer.status_code, answer.json()["code"]) == (status, code)
    assert fake.sessions == []


def test_the_pass_extends_luikki_and_packs_need_nothing():
    fake = _Stripe()
    assert _buy(fake, _Database(bought=True), "pass").status_code == 200
    assert _buy(fake, _Database(), "pack").status_code == 200


def test_the_portal_needs_a_stripe_customer():
    answer = _server(_Stripe(), _Database()).post("/v1/portal", headers=_bearer())
    assert (answer.status_code, answer.json()["code"]) == (404, "no_customer")


def test_the_portal_opens_with_luikkis_configuration():
    fake = _Stripe()
    answer = _server(fake, _Database(customer="cus_1")).post("/v1/portal", headers=_bearer())
    assert answer.json() == {"url": "https://billing.stripe.test/p/1"}
    assert fake.portals == [{"customer": "cus_1", "return_url": BASE + "/v1/done", "configuration": "bpc_luikki"}]


# -- the webhook ----------------------------------------------------------------


@pytest.mark.parametrize("line", ["luikki", "pass", "pack", "founder"])
def test_a_paid_session_records_what_its_line_gives(line):
    database = _Database()
    payload, headers = _signed("checkout.session.completed", "cs_1")
    fake = _Stripe(session=_session(metadata={"user_id": USER, "line": line}))
    assert _server(fake, database).post(WEBHOOK_ROUTE, content=payload, headers=headers).status_code == 200

    [(function, arguments)] = database.calls
    assert function == "record_purchase"
    assert arguments == {
        "p_user": USER,
        "p_line": line,
        "p_session": "cs_1",
        "p_payment_intent": "pi_1",
        "p_customer": "cus_1",
        "p_cases": LINES[line].cases,
        "p_years": LINES[line].years,
    }


def test_founders_get_panels_that_never_expire_and_packs_a_thousand():
    assert (LINES["founder"].cases, LINES["founder"].years) == (5000, 1)
    assert (LINES["pack"].cases, LINES["pack"].years) == (1000, 0)


@pytest.mark.parametrize(
    "session",
    [_session(payment_status="unpaid"), _session(mode="subscription"), _session(metadata={})],
    ids=["unpaid", "studio", "not-luikki"],
)
def test_a_session_that_bought_nothing_records_nothing(session):
    database = _Database()
    payload, headers = _signed("checkout.session.completed", "cs_1")
    assert _server(_Stripe(session=session), database).post(WEBHOOK_ROUTE, content=payload, headers=headers).status_code == 200
    assert database.calls == []


def test_a_studio_subscription_is_written_as_stripe_holds_it():
    database = _Database()
    payload, headers = _signed("customer.subscription.updated", "sub_1")
    _server(_Stripe(subscription=_subscription()), database).post(WEBHOOK_ROUTE, content=payload, headers=headers)

    [(function, arguments)] = database.calls
    assert function == "record_studio"
    assert (arguments["p_user"], arguments["p_status"], arguments["p_customer"]) == (USER, "active", "cus_1")
    assert datetime.fromisoformat(arguments["p_period_end"]) == datetime.fromtimestamp(PERIOD_END, timezone.utc) + PERIOD_GRACE


def test_a_subscription_made_elsewhere_is_left_alone():
    database = _Database()
    payload, headers = _signed("customer.subscription.updated", "sub_1")
    _server(_Stripe(subscription=_subscription(metadata={})), database).post(WEBHOOK_ROUTE, content=payload, headers=headers)
    assert database.calls == []


def test_a_full_refund_takes_the_purchase_back_and_a_partial_one_does_not():
    full, partial = _Database(), _Database()
    payload, headers = _signed("charge.refunded", "ch_1")
    _server(_Stripe(charge={"id": "ch_1", "refunded": True, "payment_intent": "pi_1"}), full).post(
        WEBHOOK_ROUTE, content=payload, headers=headers
    )
    _server(_Stripe(charge={"id": "ch_1", "refunded": False, "payment_intent": "pi_1"}), partial).post(
        WEBHOOK_ROUTE, content=payload, headers=headers
    )
    assert full.calls == [("record_refund", {"p_payment_intent": "pi_1"})]
    assert partial.calls == []


def test_a_webhook_signed_by_someone_else_writes_nothing():
    database = _Database()
    payload, headers = _signed("checkout.session.completed", "cs_1", secret="whsec_someone_else")
    answer = _server(_Stripe(session=_session()), database).post(WEBHOOK_ROUTE, content=payload, headers=headers)
    assert answer.status_code == 400
    assert database.calls == []


def test_without_its_secret_the_webhook_takes_nothing():
    database = _Database()
    payload, headers = _signed("checkout.session.completed", "cs_1", secret="")
    answer = _server(_Stripe(session=_session()), database, secret="").post(WEBHOOK_ROUTE, content=payload, headers=headers)
    assert answer.status_code == 503
    assert database.calls == []


# -- the app's side ---------------------------------------------------------------


class _Account:
    def __init__(self, token: str | None = "session"):
        self.token = token

    def access_token(self) -> str | None:
        return self.token


def _answering(status: int, body: dict, seen: list | None = None) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content) if request.content else None)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_buying_sends_the_line_and_opens_the_page_in_the_browser():
    opened, sent = [], []
    client = _answering(200, {"url": "https://checkout.stripe.test/c/1"}, sent)
    billing.buy(_Account(), "pack", open_url=opened.append, client=client)
    assert sent == [{"line": "pack"}]
    assert opened == ["https://checkout.stripe.test/c/1"]


@pytest.mark.parametrize(
    ("status", "code", "worded"),
    [
        (409, "already_subscribed", "already_subscribed"),
        (409, "already_bought", "already_bought"),
        (409, "needs_luikki", "needs_luikki"),
        (410, "sold_out", "sold_out"),
        (404, "no_customer", "no_customer"),
        (502, "billing_unavailable", "billing_refused"),
        (422, "anything", "billing_refused"),
    ],
)
def test_a_refusal_comes_back_as_a_code_the_app_words(status, code, worded):
    with pytest.raises(AccountError) as refused:
        billing.buy(_Account(), "luikki", open_url=lambda url: None, client=_answering(status, {"code": code}))
    assert refused.value.code == worded


def test_signed_out_opens_nothing():
    opened = []
    with pytest.raises(AccountError) as refused:
        billing.buy(_Account(token=None), "luikki", open_url=opened.append)
    assert refused.value.code == "signed_out"
    assert opened == []


def test_the_account_buttons_reach_billing(tmp_path, monkeypatch):
    from luikki.extract.passthrough import PassthroughExtractor
    from luikki.web.app import create_app

    pressed = []
    monkeypatch.setattr(billing, "buy", lambda account, line: pressed.append(line))
    monkeypatch.setattr(billing, "manage", lambda account: pressed.append("manage"))
    client = TestClient(create_app(tmp_path / "work", extractor=PassthroughExtractor()))

    assert client.post("/api/account/buy", json={"line": "founder"}).status_code == 200
    assert client.post("/api/account/manage").status_code == 200
    assert pressed == ["founder", "manage"]
