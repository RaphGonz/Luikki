// Stripe's webhook: the one piece of Luikki that runs on a server (ROADMAP G4).
//
// The licence is a yearly subscription sold through a Payment Link. Its first
// payment adds a year to the account named by the link's `client_reference_id`,
// which the app puts in it (`luikki/billing.py`), and ties the Stripe customer
// to that account; each renewal (`invoice.paid`, `subscription_cycle`) adds a
// year to the customer's account. A cancelled subscription simply stops
// renewing. A full refund takes a year back. All go through `supabase/schema.sql`,
// which records an invoice once however often Stripe sends it. A forged id only gives a year to someone
// else's account: the app is never believed about a payment, Stripe is.
//
//   supabase secrets set STRIPE_SECRET_KEY=… STRIPE_WEBHOOK_SECRET=… STRIPE_PAYMENT_LINK=plink_…
//   supabase functions deploy stripe-webhook --no-verify-jwt
//
// `--no-verify-jwt`: Stripe signs its calls, it holds no Supabase session.
// SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are given to every function.

import Stripe from "npm:stripe@17";
import { createClient } from "npm:@supabase/supabase-js@2";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY")!);
const subtle = Stripe.createSubtleCryptoProvider();
const database = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
const PAYMENT_LINK = Deno.env.get("STRIPE_PAYMENT_LINK");

// Postgres refusing the account id itself: not a uuid, or no such account.
// Stripe sending it again would not change the answer.
const NO_SUCH_ACCOUNT = new Set(["22P02", "23503"]);

Deno.serve(async (request) => {
  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      await request.text(),
      request.headers.get("stripe-signature") ?? "",
      Deno.env.get("STRIPE_WEBHOOK_SECRET")!,
      undefined,
      subtle,
    );
  } catch {
    return new Response("bad signature", { status: 400 });
  }

  if (event.type === "checkout.session.completed" || event.type === "checkout.session.async_payment_succeeded") {
    const session = event.data.object;
    // A card paid at once is "paid" on completion; a bank transfer arrives
    // later, as async_payment_succeeded. A 100 % code needs no payment.
    if (session.payment_link !== PAYMENT_LINK || !["paid", "no_payment_required"].includes(session.payment_status)) {
      return received();
    }
    if (!session.client_reference_id) {
      console.error(`session ${session.id} names no account: give the year by hand`);
      return received();
    }
    const { error } = await database.rpc("record_purchase", {
      p_user: session.client_reference_id,
      p_line: "base",
      // Keyed on the first invoice, which `invoice.paid` below leaves to this.
      p_session: (session.invoice as string | null) ?? session.id,
      p_payment_intent: session.payment_intent,
      p_customer: session.customer,
      p_cases: 0,
      p_years: 1,
    });
    if (error && NO_SUCH_ACCOUNT.has(error.code)) {
      console.error(`session ${session.id} names no account (${error.code}): give the year by hand`);
    } else if (error) {
      // Stripe tries again for three days.
      console.error(`record_purchase: ${error.code} ${error.message}`);
      return new Response("not recorded", { status: 500 });
    }
  } else if (event.type === "invoice.paid") {
    const invoice = event.data.object;
    // The first invoice is the Checkout session's, recorded above: it can
    // arrive before the session ties the customer to an account.
    if (invoice.billing_reason !== "subscription_cycle") return received();
    const { data, error } = await database.rpc("record_renewal", {
      p_customer: invoice.customer,
      p_invoice: invoice.id,
    });
    if (error) {
      console.error(`record_renewal: ${error.code} ${error.message}`);
      return new Response("not recorded", { status: 500 });
    }
    if (data === false) console.error(`invoice ${invoice.id}: customer ${invoice.customer} has no account`);
  } else if (event.type === "charge.refunded") {
    const charge = event.data.object;
    // A partial refund takes nothing back. A one-off payment of before the
    // subscription is found by its payment intent, a subscription's by customer.
    if (charge.refunded && charge.payment_intent) {
      const { data, error } = await database.rpc("record_refund", { p_payment_intent: charge.payment_intent });
      let failed = error;
      if (!error && data === false && charge.customer) {
        ({ error: failed } = await database.rpc("record_customer_refund", { p_customer: charge.customer }));
      }
      if (failed) {
        console.error(`refund: ${failed.code} ${failed.message}`);
        return new Response("not recorded", { status: 500 });
      }
    }
  }
  return received();
});

const received = () => Response.json({ received: true });
