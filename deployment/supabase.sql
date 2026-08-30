create table if not exists public.stockpulse_state (
    id text primary key,
    payload jsonb not null,
    updated_at timestamptz not null default now()
);

alter table public.stockpulse_state enable row level security;

revoke all on table public.stockpulse_state from anon, authenticated;
