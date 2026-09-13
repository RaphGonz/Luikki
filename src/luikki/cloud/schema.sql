-- Luikki accounts, rights, panels and the job lock (ROADMAP §B: B2, B5, B5b).
--
-- Paste into the Supabase SQL editor. Safe to run twice, and safe on the
-- tables B2 made: it migrates them in place.
--
-- Only the Modal servers touch these tables, with the secret key, which
-- bypasses RLS. The app holds the publishable key and reads its own rights
-- through `my_status` (below), never from the tables: RLS is on with no
-- policy, so `anon` and `authenticated` get nothing, and the grants are
-- revoked as well in case RLS is ever switched off by hand.
--
-- What is sold is panels, not pages (business-plan.md §4.2): the GPU paints one
-- panel at a time, and a webtoon episode is 60 to 80 of them.

-- Studio subscriptions and testers, one row per account. Testers are set by
-- hand: plan 'tester', status 'active', a period_end. A Studio row is written
-- by Stripe's webhook (`record_studio`).
create table if not exists public.subscriptions (
    user_id            uuid primary key references auth.users (id) on delete cascade,
    status             text not null check (status in (
                           'active', 'trialing', 'past_due', 'canceled', 'unpaid',
                           'incomplete', 'incomplete_expired', 'paused')),
    plan               text not null,
    period_end         timestamptz not null,
    stripe_customer_id text unique
);
-- B5 sold a monthly plan called 'paid'; the one subscription left is Studio.
alter table public.subscriptions drop constraint if exists subscriptions_plan_check;
update public.subscriptions set plan = 'studio' where plan = 'paid';
alter table public.subscriptions add constraint subscriptions_plan_check check (plan in ('tester', 'studio'));

-- One-time purchases: Luikki, the colour pass, packs, founder licences. One
-- row per Checkout Session, so a webhook sent twice records once. `cases` are
-- bought panels and never expire; `years` extend the colours.
create table if not exists public.purchases (
    id                bigint generated always as identity primary key,
    user_id           uuid not null references auth.users (id) on delete cascade,
    line              text not null check (line in ('luikki', 'pass', 'pack', 'founder')),
    cases             int not null default 0,
    years             int not null default 0,
    stripe_session_id text not null unique,
    payment_intent    text,
    refunded          boolean not null default false,
    created_at        timestamptz not null default now()
);
create index if not exists purchases_user on public.purchases (user_id);
create index if not exists purchases_payment_intent on public.purchases (payment_intent);

-- Until when an account has Cobra's colours from one-time purchases. Held
-- rather than derived: each purchase extends it from the later of now and its
-- current end, and a refund takes the years back.
create table if not exists public.colours (
    user_id uuid primary key references auth.users (id) on delete cascade,
    until   timestamptz not null
);

-- An account's Stripe customer, whatever it bought: for the portal, and so a
-- second purchase does not make a second customer.
create table if not exists public.customers (
    user_id            uuid primary key references auth.users (id) on delete cascade,
    stripe_customer_id text not null unique
);
insert into public.customers (user_id, stripe_customer_id)
select user_id, stripe_customer_id from public.subscriptions where stripe_customer_id is not null
on conflict do nothing;

-- One row per `POST /v1/panel` painted, so count(*) is GPU work, and every row
-- is one panel sold: generating a panel again costs a panel again. `source`
-- says what paid for it: 'month' one of the month's panels, 'credits' one
-- bought panel.
create table if not exists public.usage (
    id            bigint generated always as identity primary key,
    user_id       uuid not null references auth.users (id) on delete cascade,
    page_id       uuid not null,
    generation_id uuid not null,
    created_at    timestamptz not null default now()
);
alter table public.usage add column if not exists source text not null default 'month';
alter table public.usage drop constraint if exists usage_source_check;
alter table public.usage add constraint usage_source_check check (source in ('month', 'credits'));
create index if not exists usage_user_month on public.usage (user_id, created_at);

-- The seats. A device unseen for the server's days gives its place up.
create table if not exists public.devices (
    user_id   uuid not null references auth.users (id) on delete cascade,
    device_id uuid not null,
    last_seen timestamptz not null default now(),
    primary key (user_id, device_id)
);

-- The job lock, one row per job: one per device, and at most the plan's
-- `parallel_jobs` for the account. B2's table held one per account; its rows
-- only ever live for the length of a panel, so it is replaced, not migrated.
do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'jobs' and column_name = 'device_id'
    ) then
        drop table if exists public.jobs;
    end if;
end $$;
create table if not exists public.jobs (
    user_id    uuid not null references auth.users (id) on delete cascade,
    device_id  uuid not null,
    started_at timestamptz not null default now(),
    ip         inet not null,
    primary key (user_id, device_id)
);

-- What each plan allows, in panels. Read by the gate and by the app's line in
-- step 5, so the number the artist is shown is the number they are held to.
-- Changing a limit is one update here, no deploy. Studio's 5 000 is worked out
-- in business-plan.md §4.5, at 20 s of GPU per panel: measure, then adjust.
create table if not exists public.plans (
    plan text primary key
);
alter table public.plans drop constraint if exists plans_plan_check;
alter table public.plans add column if not exists cases_per_month int;
alter table public.plans add column if not exists devices int;
alter table public.plans add column if not exists parallel_jobs int;
alter table public.plans drop column if exists pages_per_month;
alter table public.plans drop column if exists generations_per_page;
delete from public.plans where plan = 'paid';
insert into public.plans (plan, cases_per_month, devices, parallel_jobs)
values ('tester', 1000, 2, 1), ('luikki', 1000, 2, 1), ('studio', 5000, 3, 3)
on conflict (plan) do update set
    cases_per_month      = coalesce(public.plans.cases_per_month, excluded.cases_per_month),
    devices              = coalesce(public.plans.devices, excluded.devices),
    parallel_jobs        = coalesce(public.plans.parallel_jobs, excluded.parallel_jobs);
alter table public.plans alter column cases_per_month set not null;
alter table public.plans alter column devices set not null;
alter table public.plans alter column parallel_jobs set not null;

alter table public.subscriptions enable row level security;
alter table public.purchases     enable row level security;
alter table public.colours       enable row level security;
alter table public.customers     enable row level security;
alter table public.usage         enable row level security;
alter table public.devices       enable row level security;
alter table public.jobs          enable row level security;
alter table public.plans         enable row level security;

revoke all on table public.subscriptions, public.purchases, public.colours, public.customers,
    public.usage, public.devices, public.jobs, public.plans
    from anon, authenticated;

-- The plan an account works under now, or null: a Studio subscription first,
-- then a tester's, then colours bought once.
create or replace function public.current_plan(p_user uuid) returns text
language sql
stable
set search_path = ''
as $$
    select case
        when exists (
            select 1 from public.subscriptions
            where user_id = p_user and plan = 'studio' and status in ('active', 'trialing') and period_end > now()
        ) then 'studio'
        when exists (
            select 1 from public.subscriptions
            where user_id = p_user and plan = 'tester' and status in ('active', 'trialing') and period_end > now()
        ) then 'tester'
        when exists (select 1 from public.colours where user_id = p_user and until > now()) then 'luikki'
    end;
$$;

-- Bought panels not used yet. A ledger rather than a counter: what was bought
-- and not refunded, minus the panels painted from it.
create or replace function public.credits_left(p_user uuid) returns int
language sql
stable
set search_path = ''
as $$
    select (
        coalesce((select sum(cases) from public.purchases where user_id = p_user and not refunded), 0)
        - (select count(*) from public.usage where user_id = p_user and source = 'credits')
    )::int;
$$;

-- The whole gate, in one transaction: `POST /v1/panel` calls this before the
-- GPU and `finish_panel` after it. One call rather than a count in Python and
-- an insert after it, because two requests for one account could both pass a
-- count neither has written to yet. Returns 'ok:<source>' or the refusal's code.
drop function if exists public.start_panel(uuid, uuid, uuid, uuid, inet, int, int, int, int, int);
create or replace function public.start_panel(
    p_user uuid, p_page uuid, p_generation uuid, p_device uuid, p_ip inet,
    p_device_days int, p_job_seconds int
) returns text
language plpgsql
set search_path = ''
as $$
declare
    month_start constant timestamptz := date_trunc('month', now());
    plan_now text;
    credits int;
    limits public.plans%rowtype;
    paid_from text;
begin
    -- Calls for one account queue here, so the checks below see each other.
    perform pg_advisory_xact_lock(hashtextextended(p_user::text, 0));

    plan_now := public.current_plan(p_user);
    credits := public.credits_left(p_user);
    if plan_now is null and credits <= 0 then
        return 'no_subscription';
    end if;
    -- Bought panels alone work under Luikki's limits, without its month.
    select * into limits from public.plans where plan = coalesce(plan_now, 'luikki');
    if not found then
        return 'no_subscription';
    end if;

    -- A device unseen for p_device_days gives its place up: a new computer
    -- must not be locked out by one that went to the tip.
    if not exists (
        select 1 from public.devices where user_id = p_user and device_id = p_device
    ) and (
        select count(*) from public.devices
        where user_id = p_user and last_seen > now() - make_interval(days => p_device_days)
    ) >= limits.devices then
        return 'too_many_devices';
    end if;

    -- A job older than the server's timeout is a container that died holding it.
    delete from public.jobs
    where user_id = p_user and started_at < now() - make_interval(secs => p_job_seconds);
    if exists (select 1 from public.jobs where user_id = p_user and device_id = p_device) then
        return 'job_running';
    end if;
    if (select count(*) from public.jobs where user_id = p_user) >= limits.parallel_jobs then
        return 'job_elsewhere';
    end if;

    -- The month's panels first, then bought ones.
    if plan_now is not null and (
        select count(*) from public.usage
        where user_id = p_user and source = 'month' and created_at >= month_start
    ) < limits.cases_per_month then
        paid_from := 'month';
    elsif credits > 0 then
        paid_from := 'credits';
    else
        return 'quota_cases';
    end if;

    insert into public.devices (user_id, device_id, last_seen)
    values (p_user, p_device, now())
    on conflict (user_id, device_id) do update set last_seen = excluded.last_seen;
    insert into public.jobs (user_id, device_id, started_at, ip) values (p_user, p_device, now(), p_ip);
    return 'ok:' || paid_from;
end;
$$;

-- Usage is written here and only on success: a panel the GPU failed does not
-- cost the artist anything.
drop function if exists public.finish_panel(uuid, uuid, uuid, boolean);
create or replace function public.finish_panel(
    p_user uuid, p_page uuid, p_generation uuid, p_device uuid, p_source text, p_succeeded boolean
) returns void
language sql
set search_path = ''
as $$
    delete from public.jobs where user_id = p_user and device_id = p_device;
    insert into public.usage (user_id, page_id, generation_id, source)
    select p_user, p_page, p_generation, p_source where p_succeeded;
$$;

-- A one-time purchase, from Stripe's webhook. Recorded once per Checkout
-- Session however often the webhook comes. False when it was already there.
create or replace function public.record_purchase(
    p_user uuid, p_line text, p_session text, p_payment_intent text, p_customer text,
    p_cases int, p_years int
) returns boolean
language plpgsql
set search_path = ''
as $$
begin
    insert into public.purchases (user_id, line, cases, years, stripe_session_id, payment_intent)
    values (p_user, p_line, p_cases, p_years, p_session, p_payment_intent)
    on conflict (stripe_session_id) do nothing;
    if not found then
        return false;
    end if;
    if p_years > 0 then
        insert into public.colours (user_id, until)
        values (p_user, now() + make_interval(years => p_years))
        on conflict (user_id) do update
        set until = greatest(public.colours.until, now()) + make_interval(years => p_years);
    end if;
    if p_customer is not null then
        insert into public.customers (user_id, stripe_customer_id) values (p_user, p_customer)
        on conflict (user_id) do update set stripe_customer_id = excluded.stripe_customer_id;
    end if;
    return true;
end;
$$;

-- A refunded payment takes back what it bought: its years of colours, and its
-- panels (a balance can go below zero, and then nothing more is painted from it).
create or replace function public.record_refund(p_payment_intent text) returns boolean
language plpgsql
set search_path = ''
as $$
declare
    bought public.purchases%rowtype;
begin
    update public.purchases set refunded = true
    where payment_intent = p_payment_intent and not refunded
    returning * into bought;
    if not found then
        return false;
    end if;
    if bought.years > 0 then
        update public.colours set until = until - make_interval(years => bought.years)
        where user_id = bought.user_id;
    end if;
    return true;
end;
$$;

-- A Studio subscription as Stripe holds it now.
create or replace function public.record_studio(
    p_user uuid, p_status text, p_period_end timestamptz, p_customer text
) returns void
language sql
set search_path = ''
as $$
    insert into public.subscriptions (user_id, status, plan, period_end, stripe_customer_id)
    values (p_user, p_status, 'studio', p_period_end, p_customer)
    on conflict (user_id) do update
    set status = excluded.status, plan = 'studio', period_end = excluded.period_end,
        stripe_customer_id = excluded.stripe_customer_id;
    insert into public.customers (user_id, stripe_customer_id) values (p_user, p_customer)
    on conflict (user_id) do update set stripe_customer_id = excluded.stripe_customer_id;
$$;

-- What the billing server needs to know before opening a payment page.
create or replace function public.buyer_status(p_user uuid) returns jsonb
language sql
stable
set search_path = ''
as $$
    select jsonb_build_object(
        'customer', (select stripe_customer_id from public.customers where user_id = p_user),
        'studio', public.current_plan(p_user) = 'studio',
        'bought', exists (
            select 1 from public.purchases
            where user_id = p_user and line in ('luikki', 'founder') and not refunded
        ),
        'founder', exists (
            select 1 from public.purchases where user_id = p_user and line = 'founder' and not refunded
        ),
        'founders_sold', (select count(*) from public.purchases where line = 'founder' and not refunded)
    );
$$;

-- Supabase lets `anon` and `authenticated` call any new function in `public`
-- through the Data API. These are the servers' alone.
do $$
declare
    signature text;
begin
    foreach signature in array array[
        'public.current_plan(uuid)',
        'public.credits_left(uuid)',
        'public.start_panel(uuid, uuid, uuid, uuid, inet, int, int)',
        'public.finish_panel(uuid, uuid, uuid, uuid, text, boolean)',
        'public.record_purchase(uuid, text, text, text, text, int, int)',
        'public.record_refund(text)',
        'public.record_studio(uuid, text, timestamptz, text)',
        'public.buyer_status(uuid)'
    ] loop
        execute format('revoke execute on function %s from public, anon, authenticated', signature);
        execute format('grant execute on function %s to service_role', signature);
    end loop;
end $$;

-- The signed-in artist's own rights and what is left of them, for the app to
-- show before step 5 is pressed. Called by the app itself, with the artist's
-- session: it runs as the table owner to read past RLS, and answers only about
-- `auth.uid()`. The GPU server is not woken to answer it. `p_page` is no
-- longer read, and kept so an app that still sends it is answered.
create or replace function public.my_status(p_page uuid default null)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with me as (select auth.uid() as id),
         month as (select date_trunc('month', now()) as start),
         now_plan as (select public.current_plan(me.id) as plan from me)
    select jsonb_build_object(
        'plan', now_plan.plan,
        'active', now_plan.plan is not null or public.credits_left(me.id) > 0,
        'credits', public.credits_left(me.id),
        'colours_until', (select c.until from public.colours c where c.user_id = me.id),
        'bought', exists (
            select 1 from public.purchases b
            where b.user_id = me.id and b.line in ('luikki', 'founder') and not b.refunded
        ),
        'customer', exists (select 1 from public.customers c where c.user_id = me.id),
        'cases_per_month', case when now_plan.plan is null then 0 else p.cases_per_month end,
        'cases_used', (
            select count(*) from public.usage u, month
            where u.user_id = me.id and u.source = 'month' and u.created_at >= month.start
        )
    )
    from me
    cross join now_plan
    left join public.plans p on p.plan = coalesce(now_plan.plan, 'luikki');
$$;

revoke execute on function public.my_status(uuid) from public, anon;
grant execute on function public.my_status(uuid) to authenticated;
