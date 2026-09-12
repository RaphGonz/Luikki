-- Luikki accounts, quota and the one-job lock (ROADMAP §B, "Données").
--
-- Paste into the Supabase SQL editor. Safe to run twice.
--
-- Only the Modal server touches these tables, with the `service_role` key,
-- which bypasses RLS. The client holds the public key and reads its plan and
-- quota through `GET /v1/me`, never here: RLS is on with no policy, so `anon`
-- and `authenticated` get nothing, and the grants are revoked as well in case
-- RLS is ever switched off by hand.

-- One row per account. Testers are set by hand: plan 'tester', status
-- 'active', a period_end, no Stripe customer. Access = status in
-- ('active', 'trialing') and period_end > now(), checked by the server.
create table if not exists public.subscriptions (
    user_id            uuid primary key references auth.users (id) on delete cascade,
    status             text not null check (status in (
                           'active', 'trialing', 'past_due', 'canceled', 'unpaid',
                           'incomplete', 'incomplete_expired', 'paused')),
    plan               text not null check (plan in ('tester', 'paid')),
    period_end         timestamptz not null,
    stripe_customer_id text unique
);

-- One row per `POST /v1/panel`, so count(*) is GPU work. The monthly quota is
-- count(distinct page_id); the per-page cap is count(distinct generation_id)
-- for that page, one generation being one press of step 5. Both ids are
-- client-made uuids: local page numbers are reused after a deletion and
-- collide across projects.
create table if not exists public.usage (
    id            bigint generated always as identity primary key,
    user_id       uuid not null references auth.users (id) on delete cascade,
    page_id       uuid not null,
    generation_id uuid not null,
    created_at    timestamptz not null default now()
);
create index if not exists usage_user_month on public.usage (user_id, created_at);

-- At most two per account, counted by the server before the GPU.
create table if not exists public.devices (
    user_id   uuid not null references auth.users (id) on delete cascade,
    device_id uuid not null,
    last_seen timestamptz not null default now(),
    primary key (user_id, device_id)
);

-- The lock: the primary key is "one job at a time". A second insert for the
-- same account fails; the server deletes the row when the job ends, and
-- treats a row older than its timeout as a dead container's leftover.
create table if not exists public.jobs (
    user_id    uuid primary key references auth.users (id) on delete cascade,
    started_at timestamptz not null default now(),
    ip         inet not null
);

alter table public.subscriptions enable row level security;
alter table public.usage         enable row level security;
alter table public.devices       enable row level security;
alter table public.jobs          enable row level security;

revoke all on table public.subscriptions, public.usage, public.devices, public.jobs
    from anon, authenticated;
