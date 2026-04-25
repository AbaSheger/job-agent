create table if not exists public.job_agent_state (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists set_job_agent_state_updated_at on public.job_agent_state;

create trigger set_job_agent_state_updated_at
before update on public.job_agent_state
for each row
execute function public.set_updated_at();
