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

-- The whole gate, in one transaction: `POST /v1/panel` calls this before the
-- GPU and `finish_panel` after it. One call rather than a count in Python and
-- an insert after it, because two requests for one account could both pass a
-- count neither has written to yet. Returns 'ok' or the refusal's code.
--
-- The limits come from the server (`cloud/accounts.py`), so changing one is a
-- deploy, not a migration.
create or replace function public.start_panel(
    p_user uuid, p_page uuid, p_generation uuid, p_device uuid, p_ip inet,
    p_pages_per_month int, p_generations_per_page int,
    p_devices int, p_device_days int, p_job_seconds int
) returns text
language plpgsql
set search_path = ''
as $$
declare
    month_start constant timestamptz := date_trunc('month', now());
    running_ip inet;
begin
    -- Calls for one account queue here, so the checks below see each other.
    perform pg_advisory_xact_lock(hashtextextended(p_user::text, 0));

    if not exists (
        select 1 from public.subscriptions
        where user_id = p_user and status in ('active', 'trialing') and period_end > now()
    ) then
        return 'no_subscription';
    end if;

    -- A device unseen for p_device_days gives its place up: a new computer
    -- must not be locked out by one that went to the tip.
    if not exists (
        select 1 from public.devices where user_id = p_user and device_id = p_device
    ) and (
        select count(*) from public.devices
        where user_id = p_user and last_seen > now() - make_interval(days => p_device_days)
    ) >= p_devices then
        return 'too_many_devices';
    end if;

    -- A job older than the server's timeout is a container that died holding it.
    delete from public.jobs
    where user_id = p_user and started_at < now() - make_interval(secs => p_job_seconds);
    select ip into running_ip from public.jobs where user_id = p_user;
    if found then
        return case when running_ip = p_ip then 'job_running' else 'job_elsewhere' end;
    end if;

    -- A page already counted this month costs nothing more, up to its cap of
    -- generations; a new page needs room in the month.
    if not exists (
        select 1 from public.usage
        where user_id = p_user and page_id = p_page and created_at >= month_start
    ) then
        if (
            select count(distinct page_id) from public.usage
            where user_id = p_user and created_at >= month_start
        ) >= p_pages_per_month then
            return 'quota_pages';
        end if;
    elsif not exists (
        select 1 from public.usage
        where user_id = p_user and page_id = p_page and generation_id = p_generation
    ) and (
        select count(distinct generation_id) from public.usage
        where user_id = p_user and page_id = p_page and created_at >= month_start
    ) >= p_generations_per_page then
        return 'quota_generations';
    end if;

    insert into public.devices (user_id, device_id, last_seen)
    values (p_user, p_device, now())
    on conflict (user_id, device_id) do update set last_seen = excluded.last_seen;
    insert into public.jobs (user_id, started_at, ip) values (p_user, now(), p_ip);
    return 'ok';
end;
$$;

-- Usage is written here and only on success: a panel the GPU failed does not
-- cost the artist a page.
create or replace function public.finish_panel(
    p_user uuid, p_page uuid, p_generation uuid, p_succeeded boolean
) returns void
language sql
set search_path = ''
as $$
    delete from public.jobs where user_id = p_user;
    insert into public.usage (user_id, page_id, generation_id)
    select p_user, p_page, p_generation where p_succeeded;
$$;

-- Supabase lets `anon` and `authenticated` call any new function in `public`
-- through the Data API. These two are the server's alone.
revoke execute on function public.start_panel(uuid, uuid, uuid, uuid, inet, int, int, int, int, int)
    from public, anon, authenticated;
revoke execute on function public.finish_panel(uuid, uuid, uuid, boolean)
    from public, anon, authenticated;
grant execute on function public.start_panel(uuid, uuid, uuid, uuid, inet, int, int, int, int, int)
    to service_role;
grant execute on function public.finish_panel(uuid, uuid, uuid, boolean) to service_role;
