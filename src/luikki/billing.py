"""Buying the licence, and managing what was bought, from the app (G4).

Both pages are Stripe's own, opened in the system browser — never in the app's
window, where a bank's 3-D Secure step or a password manager may not work —
and no server of Luikki's stands in between.

Buy is a Stripe Payment Link. The account's id rides on it as
`client_reference_id`, and Stripe's webhook (`supabase/functions/stripe-webhook`)
adds the year to that account; the app reads it back through `my_status` when
the artist returns. Manage is the Customer Portal's login link: the artist
signs in there with their email, and finds the invoices.
"""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from .account import Account, AccountError

# Made once in Stripe's dashboard (Payment Links; Settings → Customer portal).
# `LUIKKI_PAYMENT_URL` and `LUIKKI_PORTAL_URL` point at test mode's.
PAYMENT_URL = ""
PORTAL_URL = ""


def buy(account: Account, open_url: Callable[[str], Any] = webbrowser.open) -> None:
    """Open the Payment Link for the signed-in account."""
    user = account.user_id()
    open_url(_link("LUIKKI_PAYMENT_URL", PAYMENT_URL, client_reference_id=user, prefilled_email=account.email))


def manage(account: Account, open_url: Callable[[str], Any] = webbrowser.open) -> None:
    """Open the Customer Portal: invoices and receipts."""
    open_url(_link("LUIKKI_PORTAL_URL", PORTAL_URL, prefilled_email=account.email))


def _link(variable: str, default: str, **params: str | None) -> str:
    url = os.environ.get(variable) or default
    if not url:
        raise AccountError("billing_refused", status=503)
    query = urlencode({name: value for name, value in params.items() if value})
    return f"{url}?{query}" if query else url
