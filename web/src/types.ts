export type Unit = 'metric' | 'imperial'
export type View = 'dashboard' | 'dream' | 'training' | 'library' | 'settings'
export type Variant = 'match' | 'harder' | 'scenic'

export interface GeoJSONLine {
  type: 'LineString'
  coordinates: [number, number, number?][]
}

export interface RouteScore {
  total: number
  notes: string[]
}

export interface Route {
  variant: Variant
  rank?: number
  distance_km: number
  elevation_m: number
  score?: RouteScore
  explanation?: string
  geojson: GeoJSONLine
  is_similar_to_saved?: boolean
}

export interface LibraryRoute {
  id: string
  created_at: string
  user_prompt: string
  variant: Variant
  distance_km: number
  elevation_m: number
  start_lat?: number
  start_lng?: number
  geojson: GeoJSONLine
  score_total?: number
  explanation?: string
}

export interface TasteProfile {
  preferred_distance_km: [number, number]
  median_distance_km: number
  preferred_elevation_m: [number, number]
  vert_per_km: number
  grade_distribution: { flat: number; rolling: number; steep: number }
  avg_climbs_per_ride: number
  favors_sustained: boolean
  favors_punchy: boolean
  effort_shape: string
  avg_novelty_score: number
  prefers_loops: boolean
  signature_tags: string[]
  home_coords?: [number, number] | null
  avg_threshold_time_pct?: number
}

export interface LocationCoords {
  lat: number
  lng: number
  name: string
}

export interface ThinkingStep {
  type: 'thinking' | 'tool_call' | 'finalized' | 'fallback'
  content?: string
  name?: string
  input?: Record<string, unknown>
  result?: Record<string, unknown>
  recipe_mood?: string
}

export interface DreamRideResult {
  user_prompt: string
  recipe_explanation: string
  recipe: Record<string, unknown>
  routes: Route[]
  generation_id: string
  thinking_trace?: ThinkingStep[]
}

export interface AppConfig {
  mapbox_token: string
  has_graphhopper: boolean
  has_anthropic: boolean
  has_strava_token: boolean
}
