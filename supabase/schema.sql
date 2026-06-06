-- Run this in the Supabase SQL editor (Dashboard → SQL Editor → New query)

-- Taste profiles: one per user (rebuilt from Strava anytime)
create table if not exists taste_profiles (
  id          uuid default gen_random_uuid() primary key,
  user_id     uuid references auth.users(id) on delete cascade not null,
  created_at  timestamptz default now(),
  profile_json jsonb not null
);

-- Ride bounding boxes: one row per activity, used for novelty scoring
create table if not exists ride_bboxes (
  activity_id bigint,
  user_id     uuid references auth.users(id) on delete cascade not null,
  bbox_json   jsonb not null,
  primary key (activity_id, user_id)
);

-- Saved routes library
create table if not exists saved_routes (
  id           uuid default gen_random_uuid() primary key,
  user_id      uuid references auth.users(id) on delete cascade not null,
  created_at   timestamptz default now(),
  user_prompt  text,
  variant      text,
  distance_km  real,
  elevation_m  real,
  start_lat    real,
  start_lng    real,
  geojson_json jsonb,
  score_total  real,
  explanation  text,
  bbox_json    jsonb
);

-- Row Level Security: each user can only see their own data
alter table taste_profiles  enable row level security;
alter table ride_bboxes     enable row level security;
alter table saved_routes    enable row level security;

create policy "own taste_profiles"  on taste_profiles  for all using (auth.uid() = user_id);
create policy "own ride_bboxes"     on ride_bboxes     for all using (auth.uid() = user_id);
create policy "own saved_routes"    on saved_routes    for all using (auth.uid() = user_id);

-- Indexes for common query patterns
create index if not exists taste_profiles_user_created on taste_profiles(user_id, created_at desc);
create index if not exists saved_routes_user_created   on saved_routes(user_id, created_at desc);
