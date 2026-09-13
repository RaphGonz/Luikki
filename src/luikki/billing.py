"""Subscribing, and managing the subscription, from the app (B5).

The app asks the billing server (`cloud/billing.py`) for a Stripe page, with
the artist's session, and opens it in the system browser — never in the app's
window, where a bank's 3-D Secure step or a password manager may not work.
What the subscription becomes is written on the server by Stripe's webhook;
the app reads it back through `my_status` when the artist returns.
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


def subscribe(account: Account, open_url: Callable[[str], Any] = webbrowser.open, client: Any = None) -> None:
    """Open Stripe Checkout for this account. A tester's code is typed there."""
    open_url(_page(account, CHECKOUT_ROUTE, client))


def manage(account: Account, open_url: Callable[[str], Any] = webbrowser.open, client: Any = None) -> None:
    """Open the Customer Portal: cancel, change the card, read the invoices."""
    open_url(_page(account, PORTAL_ROUTE, client))


def _page(account: Account, route: str, client: Any) -> str:
    import httpx

    token = account.access_token()
    if not token:
        raise AccountError("signed_out")
    url = (os.environ.get("LUIKKI_BILLING_URL") or BILLING_URL).rstrip("/") + route
    http = client or httpx.Client(timeout=30.0)
    try:
        response = http.post(url, headers={"authorization": f"Bearer {token}"})
    except httpx.TransportError as exc:
        logger.warning("billing %s: %s", route, type(exc).__name__)
        raise AccountError("billing_unreachable", status=503) from exc
    finally:
        if client is None:
            http.close()
    if response.status_code == 409:
        raise AccountError("already_subscribed")
    if response.status_code == 404:
        raise AccountError("no_customer")
    if response.status_code >= 300:
        logger.warning("billing %s answered %s: %s", route, response.status_code, response.text[:200])
        raise AccountError("billing_unreachable", status=503)
    return response.json()["url"]
