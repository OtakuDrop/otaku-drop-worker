-- The deployed table uses a stable bigint id derived from retailer and source item id.
create table if not exists public.merchandise_drops (
  id bigint primary key,
  title text not null,
  retailer text not null,
  price numeric,
  url text,
  image_url text,
  release_date text,
  created_at timestamptz not null default now()
);

create index if not exists merchandise_drops_created_at_idx
  on public.merchandise_drops (created_at desc);

create index if not exists merchandise_drops_retailer_idx
  on public.merchandise_drops (retailer);

alter table public.merchandise_drops enable row level security;

-- Add a narrowly scoped SELECT policy only after deciding whether public
-- inventory visibility is intended. The service-role worker bypasses RLS.
