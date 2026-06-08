# Strava AI Route Planner

An AI-powered cycling route generator that learns your riding preferences from your Strava history and builds personalized routes tailored to how you actually ride — not a generic cyclist's idea of what you might want.

---

## Overview

Most route planners ask you to fill in dropdowns: distance, difficulty, surface. This one reads your Strava history and figures out who you are as a cyclist. It extracts 20+ features across all your rides — grade distribution, effort shape, novelty index, preferred climb position, loop vs. point-to-point tendency — and distills them into a statistical fingerprint called a **taste profile**.

When you type *"something long with a big climb in the middle"*, the system doesn't guess what that means. It knows your median distance is 78km, your preferred elevation band is 1400–2200m, and that you consistently pick quieter roads even when the primary is faster. Three distinct, rideable routes come back — each calibrated to all of that, not just your words.

---

## Features

### Route DNA
- Ingests your full Strava cycling history via OAuth2
- Extracts 20+ features per ride: distance, elevation, grade distribution, climb count and character, effort shape, novelty index, loop detection, turn density
- Builds a taste profile: statistical fingerprint of your riding style, stored per-user in Supabase
- Auto-trains a Max-Entropy IRL model in the background after each DNA build (see [IRL Engine](#irl-engine))

### Dream Ride Generator
- Natural language prompt → agentic Claude recipe builder with tool use (see [Agentic Recipe Building](#agentic-recipe-building))
- Recipe encodes: distance range, elevation band, climb profile, climb position, traffic tolerance, surface, novelty intent, geographic target
- Geographic targets: say "by the beach" or "mountain climb" → Overpass API finds the nearest matching OSM feature and injects it as a mandatory waypoint
- Surface avoidance: "paved roads only" → OpenRouteService excludes unpaved surfaces
- Generates 3 topologically distinct route candidates in parallel

### Three Genuinely Different Routes
Routes are generated using **equilateral triangle waypoint routing** (Lewis & Corcoran, 2024): three triangles with apexes 120° apart, sized so routed distance ≈ target distance. A smart bearing selector analyzes your saved library and picks the least-explored compass sector triplet, so consecutive generations explore new territory rather than retracing familiar ground.

Variants:
- **Match** — closest fit to the recipe's target distance and elevation
- **Harder** — 8% longer distance, steeper ORS steepness level
- **Scenic** — same distance, lower steepness, different direction

### Training Planner
Five physiological adaptation modes, each prescribing distance and elevation targets calibrated to your taste profile:
- Recovery · Aerobic Base · Muscular Endurance · Threshold · VO₂ Max

### Route Library
Every generated route is auto-saved with geographic bounding box and score. Duplicate detection uses >65% bbox overlap + <15% distance difference to skip near-identical routes. The library supports text search, variant filtering, sort by date/distance/elevation, list and grid views, GPX export, and direct upload to Strava.

### Strava Write-back
Generated routes can be pushed back to Strava as private ride activities via the Strava Uploads API. The full generation-to-ride loop: generate here → uploaded to Strava → sync to Garmin/Wahoo automatically.

---

## Architecture

```
Strava API  ──────────────────────────────────────────────────────────┐
                                                                        ↓
                                               Route DNA Layer (extractor.py)
                                                       ↓
                                             Taste Profile  ←→  Supabase
                                             IRL Weights (per-user, background)
                                                       ↓
User prompt  →  Agentic Recipe Builder (recipe_builder.py)
                  Claude Sonnet + tools:
                  ├── check_area_novelty (ride bbox lookup)
                  ├── get_irl_profile    (learned weights)
                  └── finalize_recipe    (structured output)
                                ↓
                           RouteRecipe
                                ↓
                        Route Builder (routing_client.py)
                        ├── ORS cycling-road (primary, IRL-tuned steepness)
                        ├── GraphHopper bike (fallback)
                        ├── Overpass API (geographic waypoints)
                        └── Bearing fallback (6 × 60° rotations on failure)
                                ↓
                       Scorer + Ranker (scorer.py)
                                ↓
                       Claude Haiku (per-route 1-sentence explanation)
                                ↓
                       React frontend (Mapbox GL JS)
                       └── AI reasoning trace (collapsible tool call log)
```

**Backend:** Python 3.11, FastAPI, asyncio, structlog  
**Auth & DB:** Supabase (Postgres + Auth, JWT validation)  
**AI:** Claude Sonnet 4.5 (agentic recipe), Claude Haiku 4.5 (explanations)  
**Routing:** OpenRouteService (primary, 10K req/day free), GraphHopper (fallback, 500/day)  
**Map data:** OpenStreetMap via Overpass API (geographic waypoints), GraphHopper map matching (IRL)  
**Maps:** Mapbox GL JS  
**Frontend:** React 18, TypeScript, Vite  
**Deployment:** Railway (backend), Vercel (frontend)

---

## Agentic Recipe Building

The recipe builder is a multi-step Claude reasoning loop rather than a single prompt. Before finalizing a recipe, Claude has access to two tools:

- **`check_area_novelty`** — queries the rider's ride bbox history to see how familiar a geographic area is. If the user asks for "new roads north of the city," Claude can verify how explored that direction actually is.
- **`get_irl_profile`** — returns the IRL-learned road preference profile (traffic aversion, grade seeking, surface preference). Claude uses this to verify that `traffic_tolerance` and `surface` in the recipe match the rider's implicit GPS behavior, not just their stated preferences.

Claude calls 0–2 tools, reasons over the results, then calls `finalize_recipe` with the complete structured output. The full reasoning trace (tool calls + results) is shown as a collapsible panel in the UI after each generation.

---

## IRL Engine

The Max-Entropy Inverse Reinforcement Learning engine (Ziebart et al., 2008) learns what road features a rider implicitly prefers when alternatives exist — not what they say they want.

**Features learned:** cycleway presence, surface (paved vs. unpaved), average grade, traffic level, turn frequency, segment length.

**Training pipeline:**
1. After DNA build, GPS latlng streams are map-matched to real OSM road edges via the GraphHopper map-matching API (`/match` endpoint with `details=road_class,surface`)
2. Each matched edge becomes a `RoadSegment` with features extracted from actual OSM tags
3. MaxEnt IRL fits a reward weight vector over 150 epochs
4. Weights are saved to Supabase per user

**Usage:**
- IRL grade weight → ORS steepness level (riders who seek climbing get steeper variants; those who avoid it get flatter ones)
- IRL weights are passed to the recipe builder so Claude can read them during reasoning
- `POST /irl/route` runs a full IRL-custom-model-weighted route generation

---

## Getting Started

### Prerequisites
- Python 3.11+, Node 18+
- [Anthropic API key](https://console.anthropic.com)
- [OpenRouteService API key](https://account.heigit.org) — free, 10K req/day, strongly recommended
- [GraphHopper API key](https://www.graphhopper.com/pricing/) — free, 500 req/day, used for fallback and map matching
- [Mapbox token](https://account.mapbox.com) — free tier
- [Strava API app](https://www.strava.com/settings/api)
- [Supabase project](https://supabase.com) — free tier

### Install

```bash
# Python backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# React frontend
cd web && npm install && cd ..
```

### Configure

Create a `.env` file at the project root:

```env
# AI
ANTHROPIC_API_KEY=sk-ant-...

# Routing
GRAPHHOPPER_API_KEY=...
ORS_API_KEY=...

# Maps
MAPBOX_TOKEN=pk.eyJ1...

# Strava OAuth
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_REDIRECT_URI=http://localhost:8000/strava/callback

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...

# Frontend (Vite)
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=...
```

### Supabase Setup

Run these in your Supabase SQL editor:

```sql
-- Taste profiles
create table taste_profiles (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users on delete cascade,
  created_at timestamptz not null,
  profile_json jsonb not null
);

-- Ride bboxes (novelty tracking)
create table ride_bboxes (
  user_id uuid references auth.users on delete cascade,
  activity_id bigint not null,
  bbox_json jsonb not null,
  primary key (user_id, activity_id)
);

-- Saved routes (library)
create table saved_routes (
  id uuid primary key,
  user_id uuid references auth.users on delete cascade,
  created_at timestamptz not null,
  user_prompt text,
  variant text,
  distance_km float,
  elevation_m int,
  start_lat float,
  start_lng float,
  geojson_json jsonb,
  score_total float,
  explanation text,
  bbox_json jsonb
);

-- Strava OAuth tokens
create table strava_connections (
  user_id uuid references auth.users on delete cascade primary key,
  access_token text,
  refresh_token text,
  expires_at bigint,
  athlete_id bigint,
  athlete_name text
);

-- IRL model weights
create table irl_models (
  user_id uuid references auth.users on delete cascade primary key,
  weights_json jsonb not null,
  trained_at timestamptz not null
);

-- RLS: users own their own data
alter table taste_profiles enable row level security;
alter table ride_bboxes enable row level security;
alter table saved_routes enable row level security;
alter table strava_connections enable row level security;
alter table irl_models enable row level security;

create policy "own" on taste_profiles for all using (auth.uid() = user_id);
create policy "own" on ride_bboxes for all using (auth.uid() = user_id);
create policy "own" on saved_routes for all using (auth.uid() = user_id);
create policy "own" on strava_connections for all using (auth.uid() = user_id);
create policy "own" on irl_models for all using (auth.uid() = user_id);
```

### Run (development)

```bash
# Backend
source .venv/bin/activate
uvicorn src.api.main:app --reload --port 8000

# Frontend (separate terminal)
cd web && npm run dev
```

Open `http://localhost:5173`.

In Strava API settings, set **Authorization Callback Domain** to `localhost`.

### Build (production)

```bash
cd web && npm run build
```

The backend serves the built frontend from `web/dist/` at `/`.

---

## Strava OAuth Setup

1. Go to [strava.com/settings/api](https://www.strava.com/settings/api)
2. Set **Authorization Callback Domain** to your backend domain (e.g. `yourdomain.railway.app`)
3. Set `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and `STRAVA_REDIRECT_URI` in your environment
4. In the app, go to **Settings → Connect Strava** — this handles the full OAuth2 flow

The app requests `read_all,activity:read_all,activity:write` scope. The `activity:write` scope is required for the **push to Strava** feature (uploading generated routes as activities).

---

## Deployment

The project is designed for **Railway** (backend) + **Vercel** (frontend) with Supabase for auth and data.

**Railway:**
- Set all backend env vars (`ANTHROPIC_API_KEY`, `GRAPHHOPPER_API_KEY`, `ORS_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `STRAVA_*`, `FRONTEND_URL`)
- Dockerfile is included

**Vercel:**
- Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
- `vercel.json` proxies `/route/*`, `/dna/*`, `/strava/*`, `/routes/*`, `/config`, `/health` to the Railway backend

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/dna/build` | Ingest Strava history, build taste profile + schedule IRL training |
| `GET` | `/dna/status` | Profile build status and signature tags |
| `GET` | `/dna/profile` | Full taste profile JSON |
| `POST` | `/route/dream` | Generate 3 AI route candidates from natural language |
| `POST` | `/route/training` | Generate physiology-prescribed route |
| `POST` | `/irl/train` | Manually trigger IRL training (normally automatic) |
| `POST` | `/irl/route` | Generate route using full IRL custom model |
| `GET` | `/routes/library` | List all saved routes |
| `DELETE` | `/routes/library/{id}` | Delete a saved route |
| `POST` | `/routes/library/cleanup` | Remove geographic duplicates |
| `POST` | `/routes/library/{id}/push-to-strava` | Upload route to Strava as private activity |
| `GET` | `/strava/upload/{upload_id}` | Poll Strava upload status |
| `POST` | `/strava/connect` | Get Strava OAuth authorization URL |
| `GET` | `/strava/callback` | Strava OAuth callback handler |
| `GET` | `/strava/status` | Strava connection status |
| `DELETE` | `/strava/disconnect` | Revoke Strava connection |
| `GET` | `/rate-limits` | Remaining daily quota for the current user |
| `GET` | `/config` | Mapbox token + API key presence flags |
| `GET` | `/health` | Health check |

### Rate Limits

To protect free-tier API quotas, hard daily limits are enforced:

| Action | Per user | Global |
|--------|----------|--------|
| Route generation (`/route/*`) | 10/day | 40/day |
| DNA build (`/dna/build`) | 3/day | 15/day |

Limits reset at midnight UTC. `GET /rate-limits` returns remaining quota.

---

## Project Structure

```
src/
├── api/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── auth.py              # Supabase JWT validation
│   ├── db.py                # All Supabase read/write operations
│   └── rate_limit.py        # In-memory daily rate limiter
├── layers/
│   ├── route_dna/
│   │   ├── extractor.py     # Per-ride feature extraction (20+ features)
│   │   └── taste_profile.py # Taste profile builder and data model
│   ├── dream_generator/
│   │   ├── recipe.py        # RouteRecipe dataclass
│   │   └── recipe_builder.py # Agentic Claude recipe builder (tool use)
│   └── route_builder/
│       ├── routing_client.py # ORS / GraphHopper / Overpass, triangle routing
│       ├── custom_model.py   # Recipe → GraphHopper custom model translation
│       └── scorer.py         # Multi-factor route scoring
├── builds/
│   ├── dream_ride/
│   │   └── generator.py     # Full pipeline orchestration
│   ├── training_planner/
│   │   └── adaptations.py   # Physiological adaptation prescriptions
│   └── irl_engine/
│       └── engine.py        # MaxEntropy IRL, RoadSegment, map-match integration
└── platform/
    ├── strava_client.py     # Strava REST client, map-matching, Strava uploads
    ├── logger.py            # Generation event logger
    └── prompt_registry.py   # Prompt versioning

web/
└── src/
    ├── views/               # DreamRide, Training, Settings, Library, Dashboard
    ├── components/          # RouteCard, LocationInput, RouteSVGPreview, Toast
    ├── api.ts               # Typed API client
    ├── context.tsx          # App-wide state (auth, taste profile, home, units)
    └── types.ts             # Shared TypeScript types

tests/                       # Pytest test suite
prompts/                     # Versioned prompt files
```

---

## Development

```bash
# Run tests
source .venv/bin/activate && pytest

# Type-check frontend
cd web && npx tsc --noEmit

# Rebuild frontend
cd web && npm run build

# Lint backend
source .venv/bin/activate && ruff check src/
```

---

## References

- Ziebart, B. D. et al. (2008). *Maximum Entropy Inverse Reinforcement Learning.* AAAI.
- Lewis, M. & Corcoran, J. (2024). *Fast Algorithms for Fixed-Length Round Trips.* Transportation Research.
- Oyama, Y. & Hato, E. (2022). *Deep Inverse Reinforcement Learning for Route Choice Modelling.* Transportation Research Part C.
