-- THYSMY V4 additive migration. Run once after SUPABASE_SETUP.sql.
-- Existing profiles, subscriptions and payments are preserved.
begin;
create table if not exists public.analysis_snapshots (
 id text primary key, label text not null, event_time timestamptz not null,
 phase text not null check(phase in ('before','after')), bias text not null,
 created_at timestamptz not null default now(), payload jsonb not null
);
create index if not exists idx_analysis_snapshots_created on public.analysis_snapshots(created_at desc);
create table if not exists public.analysis_outcomes (
 snapshot_id text primary key references public.analysis_snapshots(id) on delete cascade,
 payload jsonb not null, updated_at timestamptz not null default now()
);
create table if not exists public.journal_entries (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
 created_at timestamptz not null default now(), payload jsonb not null, deleted boolean not null default false
);
create index if not exists idx_journal_entries_user_created on public.journal_entries(user_id,created_at desc);
create table if not exists public.alert_preferences (
 user_id uuid primary key references public.profiles(id) on delete cascade,
 payload jsonb not null, updated_at timestamptz not null default now()
);
alter table public.analysis_snapshots enable row level security;
alter table public.analysis_outcomes enable row level security;
alter table public.journal_entries enable row level security;
alter table public.alert_preferences enable row level security;
revoke all on public.analysis_snapshots,public.analysis_outcomes,public.journal_entries,public.alert_preferences from anon,authenticated;
grant all on public.analysis_snapshots,public.analysis_outcomes,public.journal_entries,public.alert_preferences to service_role;
-- Snapshots are append-only even when written through the backend service role.
create or replace function public.thysmy_snapshot_immutable() returns trigger language plpgsql as $$
begin raise exception 'Published analysis snapshots cannot be edited or deleted'; end;
$$;
drop trigger if exists thysmy_snapshot_immutable on public.analysis_snapshots;
create trigger thysmy_snapshot_immutable before update or delete on public.analysis_snapshots for each row execute function public.thysmy_snapshot_immutable();

-- One database transaction makes payment settlement retry-safe across servers.
create or replace function public.thysmy_settle_payment(
 p_order_id text,p_bill_code text,p_refno text,p_amount_sen integer,p_days integer,p_raw jsonb
) returns jsonb language plpgsql security definer set search_path=public,pg_temp as $$
declare p public.payments%rowtype; current_exp timestamptz; new_exp timestamptz;
begin
 if p_days<1 or p_days>366 then raise exception 'Invalid subscription duration'; end if;
 select * into p from public.payments where order_id=p_order_id for update;
 if not found then raise exception 'Unknown order'; end if;
 if p.bill_code is distinct from p_bill_code or p.amount_sen<>p_amount_sen then raise exception 'Payment mismatch'; end if;
 -- Lock the subscriber too: two different paid orders must both extend the term.
 perform pg_advisory_xact_lock(hashtextextended(p.user_id::text,0));
 if p.status='success' then return jsonb_build_object('ok',true,'already_settled',true); end if;
 select expires_at into current_exp from public.subscriptions where user_id=p.user_id for update;
 new_exp=greatest(coalesce(current_exp,now()),now())+make_interval(days=>p_days);
 insert into public.subscriptions(user_id,plan,status,expires_at,updated_at)
 values(p.user_id,'pro','active',new_exp,now()) on conflict(user_id) do update
 set plan='pro',status='active',expires_at=excluded.expires_at,updated_at=now();
 update public.payments set status='success',refno=p_refno,paid_at=now(),raw=p_raw where id=p.id;
 return jsonb_build_object('ok',true,'expires_at',new_exp,'already_settled',false);
end;
$$;
revoke all on function public.thysmy_settle_payment(text,text,text,integer,integer,jsonb) from public,anon,authenticated;
grant execute on function public.thysmy_settle_payment(text,text,text,integer,integer,jsonb) to service_role;
commit;
