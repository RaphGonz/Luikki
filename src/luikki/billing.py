"""Buying colours and panels, and managing a Studio subscription, from the app (B5, B5b).

The app asks the billing server (`cloud/billing.py`) for a Stripe page, with
the artist's session, and opens it in the system browser — never in the app's
window, where a bank's 3-D Secure step or a password manager may not work.
What the purchase gives is written on the server by Stripe's webhook; the app
reads it back through `my_status` when the artist returns.
"""

from __future__ import annotations

import logging
import os
import webbrowser
from collections.abc import Callable
from typing import Any

from .account import Account, AccountError

logger = logging.getLogger("luikki.billing")

BILLING_URL = "https://raphgonz--luikki-cobra-billing.modal.run"
CHECKOUT_ROUTE = "/v1/checkout"
PORTAL_ROUTE = "/v1/portal"


def buy(account: Account, line: str, open_url: Callable[[str], Any] = webbrowser.open, client: Any = None) -> None:
    """Open Stripe Checkout for one line of `cloud/billing.py`'s `LINES`."""
    open_url(_page(account, CHECKOUT_ROUTE, client, {"line": line}))


def manage(account: Account, open_url: Callable[[str], Any] = webbrowser.open, client: Any = None) -> None:
    """Open the Customer Portal: invoices, the card, the Studio subscription."""
    open_url(_page(account, PORTAL_ROUTE, client))


def _page(account: Account, route: str, client: Any, body: dict | None = None) -> str:
    import httpx

    token = account.access_token()
    if not token:
        raise AccountError("signed_out")
    url = (os.environ.get("LUIKKI_BILLING_URL") or BILLING_URL).rstrip("/") + route
    http = client or httpx.Client(timeout=30.0)
    try:
        response = http.post(url, json=body, headers={"authorization": f"Bearer {token}"})
    except httpx.TransportError as exc:
        logger.warning("billing %s: %s", route, type(exc).__name__)
        raise AccountError("billing_unreachable", status=503) from exc
    finally:
        if client is None:
            http.close()
    if response.status_code < 300:
        return response.json()["url"]
    try:
        code = response.json().get("code")
    except (ValueError, AttributeError):
        code = None
    # The refusals the artist can act on, each in their own words.
    if code == "already_subscribed":
        raise AccountError("already_subscribed")
    if code == "already_bought":
        raise AccountError("already_bought")
    if code == "needs_luikki":
        raise AccountError("needs_luikki")
    if code == "sold_out":
        raise AccountError("sold_out", status=410)
    if code == "no_customer":
        raise AccountError("no_customer", status=404)
    # The server answered, and still no page: not the network's fault.
    logger.warning("billing %s answered %s: %s", route, response.status_code, response.text[:200])
    raise AccountError("billing_refused", status=502)
