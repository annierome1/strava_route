import { useState, useEffect } from 'react'
import { useApp, useUnit } from '../context'
import { api } from '../api'
import { supabase } from '../lib/supabase'
import { LocationInput } from '../components/LocationInput'
import type { LocationCoords } from '../types'

export function Settings() {
  const { profile, setProfile, homeLocation, setHomeLocation, showToast, user } = useApp()
  const { fmtDist, distUnit, fmtElevNum, elevUnit, fmtVertPace } = useUnit()

  const [pendingHome, setPendingHome] = useState<LocationCoords | null>(homeLocation)
  const [buildingDNA, setBuildingDNA] = useState(false)
  const [stravaStatus, setStravaStatus] = useState<{ connected: boolean; athlete_name?: string } | null>(null)
  const [stravaLoading, setStravaLoading] = useState(false)

  // Fetch Strava connection status on mount
  useEffect(() => {
    api.strava.status().then(setStravaStatus).catch(() => setStravaStatus({ connected: false }))
  }, [])

  // Handle redirect back from Strava OAuth (?strava=connected / denied / error)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const result = params.get('strava')
    if (!result) return
    window.history.replaceState({}, '', window.location.pathname)
    if (result === 'connected') {
      showToast('Strava connected!')
      api.strava.status().then(setStravaStatus).catch(() => {})
    } else if (result === 'denied') {
      showToast('Strava authorization was cancelled', 'error')
    } else {
      showToast('Strava connection failed — try again', 'error')
    }
  }, [showToast])

  function saveHome() {
    if (!pendingHome) { showToast('Select a location from the dropdown first', 'error'); return }
    setHomeLocation(pendingHome)
    showToast('Home location saved')
  }

  async function connectStrava() {
    setStravaLoading(true)
    try {
      const { url } = await api.strava.connect()
      window.location.href = url
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Could not start Strava connection', 'error')
      setStravaLoading(false)
    }
  }

  async function disconnectStrava() {
    setStravaLoading(true)
    try {
      await api.strava.disconnect()
      setStravaStatus({ connected: false })
      showToast('Strava disconnected')
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Disconnect failed', 'error')
    } finally {
      setStravaLoading(false)
    }
  }

  async function buildDNA() {
    setBuildingDNA(true)
    try {
      const data = await api.dnaBuild()
      setProfile(data.taste_profile)
      showToast(`DNA built from ${data.rides_analyzed} rides`)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Build failed', 'error')
    } finally {
      setBuildingDNA(false)
    }
  }

  const p = profile

  return (
    <div id="settings-view" className="view active">
      <div className="page-header">
        <div className="page-title">Settings</div>
        <div className="page-sub" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span>Home location, Strava connection, and your rider profile.</span>
          {user && (
            <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-3)' }}>
              {user.email}
              <button
                onClick={() => supabase.auth.signOut()}
                style={{ fontSize: 11, padding: '3px 10px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 6, cursor: 'pointer', color: 'var(--text-2)' }}
              >
                Log out
              </button>
            </span>
          )}
        </div>
      </div>

      {/* ── Home Location ── */}
      <div className="settings-section">
        <div className="settings-section-title">Home Location</div>
        <p style={{ color: 'var(--text-2)', fontSize: 13.5, lineHeight: 1.6, marginBottom: 14 }}>
          Used as the default starting point when no start is specified on Dream Ride.
        </p>
        <div className="home-input-row">
          <div className="home-input-field">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14" style={{ flexShrink: 0, color: 'var(--text-3)' }}>
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
              <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            <LocationInput
              placeholder="Enter your home address or city…"
              value={pendingHome}
              onChange={setPendingHome}
              icon={null}
            />
          </div>
          <button className="btn-secondary" onClick={saveHome}>Save</button>
        </div>
        {homeLocation && (
          <div className="home-saved-info">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="13" height="13"><polyline points="20 6 9 17 4 12"/></svg>
            <span>Saved: {homeLocation.name}</span>
            <button className="home-clear-btn" onClick={() => { setHomeLocation(null); setPendingHome(null) }}>clear</button>
          </div>
        )}
        {p?.home_coords && (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>
            DNA home: {p.home_coords[0].toFixed(4)}, {p.home_coords[1].toFixed(4)}
          </div>
        )}
      </div>

      {/* ── Strava Connection ── */}
      <div className="settings-section">
        <div className="settings-section-title">Strava Connection</div>
        <p style={{ color: 'var(--text-2)', fontSize: 13.5, lineHeight: 1.6, marginBottom: 16 }}>
          Connect your Strava account so Route AI can read your ride history and build your personal preference model.
          Read-only access — your data never leaves this app.
        </p>

        {stravaStatus?.connected ? (
          <div className="strava-connected-card">
            <div className="strava-connected-left">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="#FC4C02"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{stravaStatus.athlete_name || 'Strava account'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Connected · read-only</div>
              </div>
            </div>
            <button className="btn-secondary" onClick={disconnectStrava} disabled={stravaLoading}>
              {stravaLoading ? '…' : 'Disconnect'}
            </button>
          </div>
        ) : (
          <button className="btn-strava" onClick={connectStrava} disabled={stravaLoading}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>
            {stravaLoading ? 'Redirecting to Strava…' : 'Connect Strava'}
          </button>
        )}
      </div>

      {/* ── Route DNA ── */}
      <div className="settings-section">
        <div className="settings-section-title">Rider Profile · Route DNA</div>

        {!p ? (
          <>
            <p style={{ color: 'var(--text-2)', fontSize: 13.5, lineHeight: 1.6, marginBottom: 16 }}>
              Analyse your Strava history to build a personal preference model from your actual rides.
              This shapes all generated routes to match how you truly ride.
            </p>
            <button className="btn-primary" disabled={buildingDNA || !stravaStatus?.connected} onClick={buildDNA} title={!stravaStatus?.connected ? 'Connect Strava first' : undefined}>
              {buildingDNA ? 'Analysing rides…' : 'Build my Route DNA'}
            </button>
            {!stravaStatus?.connected && (
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>Connect Strava above first</div>
            )}
          </>
        ) : (
          <>
            <div className="dna-stats-row">
              <div className="dna-stat">
                <div className="dna-stat-val">{fmtDist(p.median_distance_km)} <span style={{ fontSize: 14, fontWeight: 400 }}>{distUnit()}</span></div>
                <div className="dna-stat-lbl">Typical distance</div>
              </div>
              <div className="dna-stat">
                <div className="dna-stat-val">{fmtDist(p.preferred_distance_km[0])}–{fmtDist(p.preferred_distance_km[1])} <span style={{ fontSize: 14, fontWeight: 400 }}>{distUnit()}</span></div>
                <div className="dna-stat-lbl">Preferred range</div>
              </div>
              <div className="dna-stat">
                <div className="dna-stat-val">{fmtElevNum(p.preferred_elevation_m[0])}–{fmtElevNum(p.preferred_elevation_m[1])} <span style={{ fontSize: 14, fontWeight: 400 }}>{elevUnit()}</span></div>
                <div className="dna-stat-lbl">Elevation range</div>
              </div>
              <div className="dna-stat">
                <div className="dna-stat-val">{fmtVertPace(p.vert_per_km)}</div>
                <div className="dna-stat-lbl">Vert per dist</div>
              </div>
            </div>

            <div className="dna-bottom-row">
              <div className="dna-card">
                <div className="dna-card-title">Grade Distribution</div>
                <div className="grade-bar-row">
                  <div className="grade-segment flat"    style={{ width: `${Math.round((p.grade_distribution.flat    ?? 0) * 100)}%` }}>{Math.round((p.grade_distribution.flat    ?? 0) * 100) > 8 ? Math.round((p.grade_distribution.flat    ?? 0) * 100) + '%' : ''}</div>
                  <div className="grade-segment rolling" style={{ width: `${Math.round((p.grade_distribution.rolling ?? 0) * 100)}%` }}>{Math.round((p.grade_distribution.rolling ?? 0) * 100) > 8 ? Math.round((p.grade_distribution.rolling ?? 0) * 100) + '%' : ''}</div>
                  <div className="grade-segment steep"   style={{ width: `${Math.round((p.grade_distribution.steep   ?? 0) * 100)}%` }}>{Math.round((p.grade_distribution.steep   ?? 0) * 100) > 8 ? Math.round((p.grade_distribution.steep   ?? 0) * 100) + '%' : ''}</div>
                </div>
                <div className="grade-legend">
                  <span><span className="legend-dot" style={{ background: '#52A8FF' }}/>Flat</span>
                  <span><span className="legend-dot" style={{ background: '#F0970A' }}/>Rolling</span>
                  <span><span className="legend-dot" style={{ background: '#E53E3E' }}/>Steep</span>
                </div>
              </div>

              <div className="dna-card">
                <div className="dna-card-title">Rider Signature</div>
                <div className="effort-shape-badge">
                  {{ negative_split: '↗', positive_split: '↘', even: '→' }[p.effort_shape] ?? '→'}{' '}
                  {{ negative_split: 'Strong Finisher', positive_split: 'Front-Loaded', even: 'Even Paced' }[p.effort_shape] ?? p.effort_shape}
                </div>
                <div className="tags-list">
                  {(p.signature_tags ?? []).map(t => <span key={t} className="dna-tag">{t}</span>)}
                </div>
              </div>
            </div>

            <div className="dna-actions">
              <button className="btn-secondary" disabled={buildingDNA} onClick={buildDNA}>
                {buildingDNA ? 'Rebuilding…' : 'Rebuild from Strava'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
