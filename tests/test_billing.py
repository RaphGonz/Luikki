"""Selling the licence: the app's buttons open Stripe's pages.

The webhook that records a purchase runs on Supabase
(`supabase/functions/stripe-webhook`) and is checked against Stripe in test
mode, not here.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from luikki import billing
from luikki.account import Account, AccountError

USER = "5f0c3a52-8a0e-4c2b-9d43-3f1e0e6b7a11"
PAY = "https://buy.stripe.test/link"
PORTAL = "https://billing.stripe.test/p/login/portal"


def _token(claims: dict) -> str:
    part = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{part}.signature"


class _Account:
    def __init__(self, token: str | None = _token({"sub": USER}), email: str | None = "artist@example.com"):
        self.token = token
        self.email = email

    def access_token(self) -> str | None:
        return self.token

    user_id = Account.user_id


@pytest.fixture(autouse=True)
def _links(monkeypatch):
    monkeypatch.setattr(billing, "PAYMENT_URL", PAY)
    monkeypatch.setattr(billing, "PORTAL_URL", PORTAL)
    monkeypatch.delenv("LUIKKI_PAYMENT_URL", raising=False)
    monkeypatch.delenv("LUIKKI_PORTAL_URL", raising=False)


def test_buying_opens_the_payment_link_for_this_account():
    opened = []
    billing.buy(_Account(), open_url=opened.append)
    assert opened == [f"{PAY}?client_reference_id={USER}&prefilled_email=artist%40example.com"]


def test_managing_opens_the_portal_with_the_email():
    opened = []
    billing.manage(_Account(), open_url=opened.append)
    assert opened == [f"{PORTAL}?prefilled_email=artist%40example.com"]


def test_test_mode_links_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("LUIKKI_PAYMENT_URL", "https://buy.stripe.test/test_link")
    opened = []
    billing.buy(_Account(email=None), open_url=opened.append)
    assert opened == [f"https://buy.stripe.test/test_link?client_reference_id={USER}"]


def test_signed_out_opens_nothing():
    opened = []
    with pytest.raises(AccountError) as refused:
        billing.buy(_Account(token=None), open_url=opened.append)
    assert refused.value.code == "signed_out"
    assert opened == []


def test_no_link_yet_is_a_refusal_the_app_words(monkeypatch):
    monkeypatch.setattr(billing, "PAYMENT_URL", "")
    with pytest.raises(AccountError) as refused:
        billing.buy(_Account(), open_url=lambda url: None)
    assert refused.value.code == "billing_refused"


def test_the_account_buttons_reach_billing(tmp_path, monkeypatch):
    from luikki.extract.passthrough import PassthroughExtractor
    from luikki.web.app import create_app

    pressed = []
    monkeypatch.setattr(billing, "buy", lambda account: pressed.append("buy"))
    monkeypatch.setattr(billing, "manage", lambda account: pressed.append("manage"))
    client = TestClient(create_app(tmp_path / "work", extractor=PassthroughExtractor()))

    assert client.post("/api/account/buy").status_code == 200
    assert client.post("/api/account/manage").status_code == 200
    assert pressed == ["buy", "manage"]
