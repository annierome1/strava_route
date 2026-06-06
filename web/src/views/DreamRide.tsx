import { useState } from 'react'
import { useApp, useUnit } from '../context'
import { api } from '../api'
import { LocationInput } from '../components/LocationInput'
import { RouteCard, exportGPX, exportToStrava } from '../components/RouteCard'
import type { LocationCoords, Route } from '../types'

const HINTS = [
  { label: 'big climb',     text: 'something long with a big climb in the middle' },
  { label: 'fast flat',     text: 'fast flat loop, 2 hours max' },
  { label: 'explore',       text: 'quiet roads, explore somewhere new' },
  { label: 'epic day',      text: "epic all-day adventure, don't hold back" },
  { label: 'by the beach',  text: 'scenic coastal ride, paved roads only' },
  { label: 'mountain run',  text: 'mountain climb with big views' },
]

export function DreamRide() {
  const { profile, homeLocation, showToast } = useApp()
  const { fmtDist, distUnit, fmtElevNum, elevUnit } = useUnit()
  const [prompt, setPrompt] = useState('')
  const [startCoords, setStartCoords] = useState<LocationCoords | null>(null)
  const [endCoords, setEndCoords] = useState<LocationCoords | null>(null)
  const [isLoop, setIsLoop] = useState(true)
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState(0)
  const [routes, setRoutes] = useState<Route[]>([])
  const [recipeExplanation, setRecipeExplanation] = useState('')
  const [userPromptUsed, setUserPromptUsed] = useState('')

  const steps = ['Building your recipe…', 'Generating route candidates…', 'Scoring and ranking…']

  async function generate() {
    if (!prompt.trim()) { showToast('Enter a ride description first', 'error'); return }
    if (!profile) { showToast('Build your Route DNA in Settings first', 'error'); return }

    setLoading(true)
    setRoutes([])
    setStep(0)
    const timer = setInterval(() => setStep(s => Math.min(s + 1, steps.length - 1)), 2200)

    try {
      const start = startCoords ?? homeLocation
      const body: Parameters<typeof api.dreamRide>[0] = { prompt, is_loop: isLoop }
      if (start) { body.start_lat = start.lat; body.start_lng = start.lng }
      if (!isLoop && endCoords) { body.end_lat = endCoords.lat; body.end_lng = endCoords.lng }

      const result = await api.dreamRide(body)
      setRoutes(result.routes)
      setRecipeExplanation(result.recipe_explanation)
      setUserPromptUsed(result.user_prompt)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Generation failed', 'error')
    } finally {
      clearInterval(timer)
      setLoading(false)
    }
  }

  const sub = profile
    ? `${(profile.signature_tags ?? []).join(' · ')} — ${fmtDist(profile.median_distance_km)} ${distUnit()} typical, ${fmtElevNum(profile.preferred_elevation_m[0])}–${fmtElevNum(profile.preferred_elevation_m[1])} ${elevUnit()} vert`
    : 'Describe any ride. Your history shapes the route.'

  return (
    <div id="dream-view" className="view active">
      <div className="page-header">
        <div className="page-title">Route Generator</div>
        <div className="page-sub">{sub}</div>
      </div>

      <div className="prompt-box">
        {/* Start location row */}
        <div className="location-row">
          <LocationInput
            placeholder={`Start location${homeLocation ? ` (${homeLocation.name})` : ' (default: your home)'}`}
            value={startCoords}
            onChange={setStartCoords}
            icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 1 8 8c0 5.25-8 14-8 14S4 15.25 4 10a8 8 0 0 1 8-8z"/></svg>}
          />
          <div className="loop-toggle-wrap">
            <label className="loop-toggle-label">
              <input type="checkbox" checked={isLoop} onChange={e => setIsLoop(e.target.checked)} />
              <span className="loop-toggle-track"><span className="loop-toggle-thumb"></span></span>
            </label>
            <span className="loop-toggle-text">{isLoop ? 'Loop' : 'A → B'}</span>
          </div>
        </div>

        {/* End location row (A→B mode) */}
        {!isLoop && (
          <div className="location-row">
            <LocationInput
              placeholder="End location"
              value={endCoords}
              onChange={setEndCoords}
              icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14"><path d="M5 12h14M12 5l7 7-7 7"/></svg>}
            />
          </div>
        )}

        <textarea
          className="prompt-textarea"
          rows={3}
          placeholder="quiet roads, 60 miles with some climbing…"
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) generate() }}
        />

        <div className="prompt-footer">
          <div className="prompt-hints">
            {HINTS.map(h => (
              <div key={h.label} className="hint-pill" onClick={() => setPrompt(h.text)}>{h.label}</div>
            ))}
          </div>
          <button className="btn-generate" disabled={loading} onClick={generate}>
            <svg viewBox="0 0 24 24" fill="none"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            Generate
          </button>
        </div>
      </div>

      {/* Loading state */}
      <div className={`generating-bar ${loading ? 'visible' : ''}`}>
        <div className="dot-row"><span/><span/><span/></div>
        <span>{steps[step]}</span>
      </div>

      {/* Skeleton cards */}
      {loading && (
        <div className="skeleton routes-grid visible">
          {[0,1,2].map(i => (
            <div key={i} className="skel-card">
              <div className="skel-map"/>
              <div className="skel-body">
                <div className="skel-line w60"/><div className="skel-line w80"/><div className="skel-line w45"/>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Recipe banner */}
      {recipeExplanation && !loading && (
        <div className="recipe-banner">
          <div className="recipe-prompt">"{userPromptUsed}"</div>
          <div>{recipeExplanation}</div>
        </div>
      )}

      {/* Route cards */}
      {!loading && routes.length > 0 && (
        <div className="routes-grid">
          {routes.map((route, i) => (
            <RouteCard
              key={`${route.variant}-${i}`}
              route={route}
              onExportGPX={() => { exportGPX(route); showToast('GPX downloaded — import at strava.com/routes/new') }}
              onExportStrava={() => exportToStrava(route)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
