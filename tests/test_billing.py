"""Subscriptions: the billing server's doors, and the app's two buttons.

Stripe does not run here. `_Stripe` answers the SDK calls the server makes
with real `StripeObject`s, and webhooks are signed the way Stripe signs them,
with a secret made for the test. Supabase's `subscriptions` table is an httpx
transport keeping rows in a dict. `stripe_setup.py` is checked against Stripe
itself, in test mode.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
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
from luikki.cloud.billing import PERIOD_GRACE, WEBHOOK_ROUTE, Subscriptions, create_billing  # noqa: E402

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


def _row(status: str = "active", days: int = 10, customer: str | None = "cus_1") -> dict:
    ends = datetime.now(timezone.utc) + timedelta(days=days)
    return {"status": status, "plan": "paid", "period_end": ends.isoformat(), "stripe_customer_id": customer}


class _Table:
    """`subscriptions`, as the Data API answers it."""

    def __init__(self, rows: dict | None = None):
        self.rows = rows or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            user = request.url.params["user_id"].removeprefix("eq.")
            return httpx.Response(200, json=[self.rows[user]] if user in self.rows else [])
        row = json.loads(request.content)
        self.rows[row["user_id"]] = row
        return httpx.Response(201)


class _Stripe:
    """The part of the SDK the server calls. Webhook signatures are checked for real."""

    StripeError = stripe.StripeError
    SignatureVerificationError = stripe.SignatureVerificationError
    Webhook = stripe.Webhook

    def __init__(self, subscription: dict | None = None):
        self.sessions: list[dict] = []
        self.portals: list[dict] = []
        configurations = [{"id": "bpc_other", "metadata": {}}, {"id": "bpc_luikki", "metadata": {"luikki": "portal"}}]
        self.Price = SimpleNamespace(list=lambda **_: _object({"data": [{"id": "price_monthly"}]}))
        self.Subscription = SimpleNamespace(retrieve=lambda _id: _object(subscription))
        self.checkout = SimpleNamespace(Session=SimpleNamespace(create=self._checkout))
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


def _server(fake: _Stripe, table: _Table, secret: str = WEBHOOK_SECRET) -> TestClient:
    subscriptions = Subscriptions(PROJECT, "sb_secret_test", client=httpx.Client(transport=httpx.MockTransport(table)))
    return TestClient(
        create_billing(
            fake,
            verifier=TokenVerifier(PROJECT, signing_key=lambda token: KEY.public_key()),
            subscriptions=subscriptions,
            webhook_secret=secret,
            base_url=BASE,
        )
    )


def _subscription(**changes) -> dict:
    return {
        "id": "sub_1",
        "status": "active",
        "customer": "cus_1",
        "metadata": {"user_id": USER},
        "items": {"data": [{"current_period_end": PERIOD_END}]},
    } | changes


def _signed(kind: str = "customer.subscription.updated", secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict]:
    # Stale on purpose: the server reads the subscription again rather than trusting the event.
    event = {"id": "evt_1", "type": kind, "data": {"object": {"id": "sub_1", "status": "incomplete"}}}
    payload = json.dumps(event).encode()
    stamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return payload, {"stripe-signature": f"t={stamp},v1={signature}", "content-type": "application/json"}


def test_checkout_is_for_this_account_takes_codes_and_asks_for_no_card_it_does_not_need():
    fake = _Stripe()
    answer = _server(fake, _Table()).post("/v1/checkout", headers=_bearer())

    assert answer.json() == {"url": "https://checkout.stripe.test/c/1"}
    [session] = fake.sessions
    assert session["client_reference_id"] == USER
    assert session["subscription_data"] == {"metadata": {"user_id": USER}}
    assert session["allow_promotion_codes"] is True
    assert session["payment_method_collection"] == "if_required"
    assert session["line_items"] == [{"price": "price_monthly", "quantity": 1}]
    assert "customer" not in session


def test_checkout_needs_a_session():
    fake = _Stripe()
    assert _server(fake, _Table()).post("/v1/checkout").status_code == 401
    assert fake.sessions == []


def test_an_active_subscriber_is_not_sent_to_pay_twice():
    fake = _Stripe()
    answer = _server(fake, _Table({USER: _row()})).post("/v1/checkout", headers=_bearer())
    assert (answer.status_code, answer.json()["code"]) == (409, "already_subscribed")
    assert fake.sessions == []


def test_a_lapsed_subscriber_checks_out_as_the_same_customer():
    fake = _Stripe()
    _server(fake, _Table({USER: _row(status="canceled", days=-1)})).post("/v1/checkout", headers=_bearer())
    assert fake.sessions[0]["customer"] == "cus_1"


def test_the_portal_needs_a_stripe_customer():
    answer = _server(_Stripe(), _Table()).post("/v1/portal", headers=_bearer())
    assert (answer.status_code, answer.json()["code"]) == (404, "no_customer")


def test_the_portal_opens_with_luikkis_configuration():
    fake = _Stripe()
    answer = _server(fake, _Table({USER: _row()})).post("/v1/portal", headers=_bearer())
    assert answer.json() == {"url": "https://billing.stripe.test/p/1"}
    assert fake.portals == [{"customer": "cus_1", "return_url": BASE + "/v1/done", "configuration": "bpc_luikki"}]


def test_a_webhook_writes_what_stripe_holds_now():
    table = _Table()
    payload, headers = _signed()
    answer = _server(_Stripe(_subscription()), table).post(WEBHOOK_ROUTE, content=payload, headers=headers)

    assert answer.status_code == 200
    row = table.rows[USER]
    assert (row["status"], row["plan"], row["stripe_customer_id"]) == ("active", "paid", "cus_1")
    assert datetime.fromisoformat(row["period_end"]) == datetime.fromtimestamp(PERIOD_END, timezone.utc) + PERIOD_GRACE


def test_a_cancelled_subscription_is_written_cancelled():
    table = _Table()
    payload, headers = _signed("customer.subscription.deleted")
    _server(_Stripe(_subscription(status="canceled")), table).post(WEBHOOK_ROUTE, content=payload, headers=headers)
    assert table.rows[USER]["status"] == "canceled"


def test_a_webhook_signed_by_someone_else_writes_nothing():
    table = _Table()
    payload, headers = _signed(secret="whsec_someone_else")
    answer = _server(_Stripe(_subscription()), table).post(WEBHOOK_ROUTE, content=payload, headers=headers)
    assert answer.status_code == 400
    assert table.rows == {}


def test_without_its_secret_the_webhook_takes_nothing():
    table = _Table()
    payload, headers = _signed(secret="")
    answer = _server(_Stripe(_subscription()), table, secret="").post(WEBHOOK_ROUTE, content=payload, headers=headers)
    assert answer.status_code == 503
    assert table.rows == {}


def test_a_subscription_made_elsewhere_is_left_alone():
    table = _Table()
    payload, headers = _signed()
    answer = _server(_Stripe(_subscription(metadata={})), table).post(WEBHOOK_ROUTE, content=payload, headers=headers)
    assert answer.status_code == 200
    assert table.rows == {}


# -- the app's side -------------------------------------------------------------


class _Account:
    def __init__(self, token: str | None = "session"):
        self.token = token

    def access_token(self) -> str | None:
        return self.token


def _answering(status: int, body: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))


def test_subscribe_opens_the_checkout_page_in_the_browser():
    opened = []
    billing.subscribe(_Account(), open_url=opened.append, client=_answering(200, {"url": "https://checkout.stripe.test/c/1"}))
    assert opened == ["https://checkout.stripe.test/c/1"]


@pytest.mark.parametrize(
    ("status", "code"),
    [(409, "already_subscribed"), (404, "no_customer"), (502, "billing_unreachable")],
)
def test_a_refusal_comes_back_as_a_code_the_app_words(status, code):
    with pytest.raises(AccountError) as refused:
        billing.manage(_Account(), open_url=lambda url: None, client=_answering(status, {"code": "x"}))
    assert refused.value.code == code


def test_signed_out_opens_nothing():
    opened = []
    with pytest.raises(AccountError) as refused:
        billing.subscribe(_Account(token=None), open_url=opened.append)
    assert refused.value.code == "signed_out"
    assert opened == []


def test_the_account_buttons_reach_billing(tmp_path, monkeypatch):
    from luikki.extract.passthrough import PassthroughExtractor
    from luikki.web.app import create_app

    pressed = []
    monkeypatch.setattr(billing, "subscribe", lambda account: pressed.append("subscribe"))
    monkeypatch.setattr(billing, "manage", lambda account: pressed.append("manage"))
    client = TestClient(create_app(tmp_path / "work", extractor=PassthroughExtractor()))

    assert client.post("/api/account/subscribe").status_code == 200
    assert client.post("/api/account/manage").status_code == 200
    assert pressed == ["subscribe", "manage"]
