# Strava AI Route Planner

An AI-powered cycling route generator that learns your preferences from your Strava history and creates personalized routes tailored to how you actually ride — not just what you say you like.

---

## What It Does

You type a description of the ride you want. The system reads your entire Strava history, builds a model of your riding preferences, and generates three real, rideable routes that match both your request and your actual riding style.

**"something long with a big climb in the middle"** → three distinct routes, each calibrated to your median distance, preferred grade distribution, novelty preference, and effort shape — not some generic cyclist's.

---

## Why It's Impressive

### Your rides teach it
Before generating anything, the app ingests every cycling activity from your Strava account. It extracts 20+ features per ride: distance, elevation, grade distribution, climb count, effort shape (negative split vs. front-loaded), novelty index (new roads vs. familiar loops), and preferred climb position. These are distilled into a **taste profile** — a statistical fingerprint of who you are as a cyclist.

### The recipe layer
When you type a prompt, Claude (Anthropic's frontier model) doesn't just read your words — it also reads your taste profile. It produces a structured **route recipe**: target distance range, elevation band, climb character, traffic tolerance, surface preference, novelty preference, geographic target (coastal? mountain? forest?), and surface avoidance. This recipe bridges natural language to precise routing parameters.

### Geographic and surface intelligence
Say "by the beach" → the recipe sets `geographic_target: coastal`. The routing engine queries the **OpenStreetMap Overpass API** in real time to find the nearest beach/coastline and injects it as a required waypoint. Say "paved roads only" → OpenRouteService is instructed to avoid unpaved surfaces.

### Three genuinely different routes
Most routing APIs produce nearly identical results when called repeatedly. This system uses **Lewis & Corcoran (2024) waypoint triangle routing**: three equilateral triangles with apexes 120° apart on the compass, each sized so `routed_distance ≈ target_km`. The routes explore genuinely different geographic sectors. A smart bearing selector analyzes your saved library to pick the least-explored compass sectors, so you never get the same route twice.

### Deduplicated library
Every generated route is saved with its geographic bounding box. Before saving a new route, the system checks for >65% bounding-box overlap combined with <15% distance difference — exact duplicates are skipped entirely. A cleanup endpoint removes any that slip through.

### IRL-trained preferences (advanced)
A Max-Entropy Inverse Reinforcement Learning engine can be trained on your full GPS trajectory history. It learns implicit preferences — road features you consistently choose when alternatives exist — and encodes them as a GraphHopper custom model for future routes.

---

## Architecture

```
Strava API  →  Route DNA Layer  →  Taste Profile (SQLite)
                                        ↓
User prompt  →  Dream Generator  →  RouteRecipe (Claude Sonnet)
                                        ↓
                                   Route Builder
                                   ├── ORS (primary, 10K req/day free)
                                   ├── GraphHopper (fallback, 500/day)
                                   ├── Overpass API (geographic waypoints)
                                   └── Bearing fallback (up to 6 × 60° rotations)
                                        ↓
                                   Scorer + Ranker
                                        ↓
                                   Claude Haiku (per-route explanation)
                                        ↓
                                   React frontend (Mapbox GL)
```

**Backend**: Python 3.14, FastAPI, asyncio, structlog, SQLite  
**AI**: Anthropic Claude Sonnet (recipe), Claude Haiku (explanations)  
**Routing**: OpenRouteService (primary), GraphHopper (fallback)  
**Maps**: Mapbox GL JS (dark-v11 style)  
**Frontend**: React 18, TypeScript, Vite  
**Data source**: Strava REST API v3 with OAuth2 auto-refresh

---

## Getting Started

### 1. Prerequisites
- Python 3.12+, Node 18+
- [Anthropic API key](https://console.anthropic.com)
- [GraphHopper API key](https://www.graphhopper.com/pricing/) (free tier: 500 req/day)
- [OpenRouteService API key](https://account.heigit.org) (free tier: 10,000 req/day — strongly recommended)
- [Mapbox token](https://account.mapbox.com) (free tier)
- [Strava API credentials](https://www.strava.com/settings/api)

### 2. Install

```bash
# Python backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# React frontend
cd web && npm install && npm run build && cd ..
```

### 3. Configure

Copy `.env.example` to `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-...
GRAPHHOPPER_API_KEY=...
ORS_API_KEY=...                  # strongly recommended
MAPBOX_TOKEN=pk.eyJ1...
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_REFRESH_TOKEN=...
```

**Getting Strava tokens:**
1. Create an app at strava.com/settings/api
2. Authorize: `https://www.strava.com/oauth/authorize?client_id=YOUR_ID&redirect_uri=http://localhost&response_type=code&scope=read_all,activity:read_all`
3. Exchange the code: `curl -X POST https://www.strava.com/oauth/token -d client_id=ID -d client_secret=SECRET -d code=CODE -d grant_type=authorization_code`
4. Copy `refresh_token` from the response into `.env`

### 4. Run

```bash
# Start backend
source .venv/bin/activate
uvicorn src.api.main:app --reload --port 8000

# (dev only) start React dev server with hot reload
cd web && npm run dev
```

Open `http://localhost:5173` (dev) or `http://localhost:8000` (production build).

### 5. Build your Route DNA

Go to **Settings** → click **Build my Route DNA**. The system fetches all your Strava activities (148 rides analyzed in under 30 seconds), extracts features, and builds your taste profile. This happens once; subsequent route generations use the cached profile.

---

## Using the App

### Dream Ride
Type any description of a ride you want. Use natural language:
- "something long with a big climb in the middle"
- "scenic coastal ride, paved roads only"  
- "quiet mountain roads, 4 hours"
- "fast flat loop, 2 hours max"

Optionally set a custom start location (geocoded via Mapbox). Toggle **Loop / A→B** for point-to-point routes. Press ⌘↵ or click Generate.

Three route candidates appear, each with a Mapbox preview, fit score, and a one-sentence explanation from Claude. Download as GPX or export directly to Strava Routes.

### Training Routes
Five physiological adaptation types: Recovery, Aerobic Base, Muscular Endurance, Threshold, VO₂ Max. Each prescribes distance and elevation targets calibrated to your taste profile, then generates routes that match those parameters.

### Settings
- **Home Location**: set your default starting point (saved to localStorage). Used when no start is specified.
- **Route DNA**: view your inferred riding preferences — grade distribution, effort shape, signature tags, preferred ranges. Rebuild from Strava anytime.

### Library
Every generated route is auto-saved. The library lets you:
- **Search** by prompt text
- **Filter** by variant (Match / Harder / Scenic)
- **Sort** by date, distance, or elevation
- **Switch views** between list (with SVG route previews) and grid
- **Export** any saved route as GPX or send to Strava
- **Remove duplicates** in one click

---

## Development

```bash
# Run Python tests
source .venv/bin/activate && pytest

# Type-check React
cd web && npx tsc --noEmit

# Rebuild frontend for production
cd web && npm run build
```

### Project structure
```
src/
  api/main.py                    # FastAPI app, all endpoints
  layers/
    route_dna/                   # Strava ingest + taste profile
    dream_generator/             # Claude recipe builder
    route_builder/               # ORS / GraphHopper / Overpass
  builds/
    dream_ride/generator.py      # Full pipeline orchestration
    training_planner/            # Physiological route prescriptions
    irl_engine/                  # Max-entropy IRL (advanced)
web/
  src/
    views/                       # DreamRide, Training, Settings, Library
    components/                  # RouteCard, LocationInput, RouteSVGPreview
    api.ts                       # Typed API client
    context.tsx                  # App-wide state (unit, profile, home)
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/dna/build` | Ingest Strava history, build taste profile |
| `GET`  | `/dna/profile` | Retrieve current taste profile |
| `POST` | `/route/dream` | Generate 3 AI route candidates |
| `POST` | `/route/training` | Generate physiology-prescribed route |
| `GET`  | `/routes/library` | List all saved routes |
| `DELETE` | `/routes/library/{id}` | Delete a saved route |
| `POST` | `/routes/library/cleanup` | Remove duplicate routes |
| `GET`  | `/config` | API key status + Mapbox token |
| `GET`  | `/health` | Health check |
