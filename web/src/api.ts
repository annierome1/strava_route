import type { AppConfig, DreamRideResult, LibraryRoute, TasteProfile } from './types'
import { supabase } from './lib/supabase'

// In dev: Vite proxy forwards /route /dna etc. to localhost:8000
// In production: VITE_API_URL points to the deployed backend (e.g. Railway)
const BASE = ''

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const headers = {
    ...(opts?.body ? { 'Content-Type': 'application/json' } : {}),
    ...(await authHeaders()),
    ...((opts?.headers as Record<string, string>) ?? {}),
  }
  const r = await fetch(BASE + path, { ...opts, headers })
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail || `Request failed: ${r.status}`)
  }
  return r.json()
}

export const api = {
  config: () => req<AppConfig>('/config'),

  dnaStatus: () => req<{ profile_built: boolean; has_strava_token: boolean }>('/dna/status'),
  dnaProfile: () => req<TasteProfile>('/dna/profile'),
  dnaBuild: () => req<{ taste_profile: TasteProfile; rides_analyzed: number }>('/dna/build', { method: 'POST' }),

  dreamRide: (body: {
    prompt: string
    is_loop: boolean
    start_lat?: number
    start_lng?: number
    end_lat?: number
    end_lng?: number
  }) => req<DreamRideResult>('/route/dream', {
    method: 'POST',
    body: JSON.stringify(body),
  }),

  trainingRoute: (adaptation: string) => req<DreamRideResult>('/route/training', {
    method: 'POST',
    body: JSON.stringify({ adaptation }),
  }),

  library: () => req<LibraryRoute[]>('/routes/library'),

  deleteRoute: (id: string) => req(`/routes/library/${id}`, { method: 'DELETE' }),

  cleanupLibrary: () => req<{ deleted: number; remaining: number }>('/routes/library/cleanup', { method: 'POST' }),

  strava: {
    status: () => req<{ connected: boolean; athlete_name?: string; athlete_id?: number }>('/strava/status'),
    connect: () => req<{ url: string }>('/strava/connect', { method: 'POST' }),
    disconnect: () => req('/strava/disconnect', { method: 'DELETE' }),
  },

  geocode: async (query: string, token: string): Promise<{ lat: number; lng: number; name: string }[]> => {
    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(query)}.json` +
      `?access_token=${token}&types=address,place,poi&limit=5&language=en`
    const data = await fetch(url).then(r => r.json())
    return (data.features ?? []).map((f: { center: [number, number]; place_name: string }) => ({
      lat: f.center[1],
      lng: f.center[0],
      name: f.place_name,
    }))
  },
}
