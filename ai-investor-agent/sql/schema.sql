create extension if not exists vector;

create table if not exists stocks (
  symbol text primary key,
  name text not null,
  sector text not null,
  market_cap numeric,
  is_fno boolean default false
);

create table if not exists bulk_deals (
  id bigint generated always as identity primary key,
  symbol text not null references stocks(symbol),
  deal_date date not null,
  buyer text not null,
  quantity bigint not null,
  price numeric not null
);

create table if not exists pattern_success_rates (
  id bigint generated always as identity primary key,
  symbol text not null references stocks(symbol),
  pattern_name text not null,
  total_occurrences integer not null,
  successful_occurrences integer not null,
  success_rate numeric not null,
  avg_return_pct numeric not null
);

create table if not exists user_portfolios (
  user_id text primary key,
  holdings jsonb not null,
  risk_profile text not null,
  total_capital numeric not null
);

create table if not exists alerts (
  id bigint generated always as identity primary key,
  symbol text not null references stocks(symbol),
  action text not null,
  confidence numeric not null,
  embedding vector(1536)
);

create table if not exists recommendation_outcomes (
  id bigint generated always as identity primary key,
  user_id text not null,
  symbol text not null references stocks(symbol),
  pattern_name text not null,
  action text not null,
  market_condition text not null,
  signal_stack jsonb not null default '[]'::jsonb,
  entry_price numeric not null,
  target_price numeric not null,
  stop_loss numeric not null,
  outcome_return_pct numeric not null,
  outcome_horizon_days integer not null,
  outcome_label text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_pattern_success_symbol_pattern
  on pattern_success_rates(symbol, pattern_name);

create index if not exists idx_recommendation_outcomes_lookup
  on recommendation_outcomes(symbol, pattern_name, market_condition);
