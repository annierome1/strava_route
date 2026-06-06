import { useState } from 'react'
import { useApp, useUnit } from '../context'
import { api } from '../api'
import { supabase } from '../lib/supabase'
import { LocationInput } from '../components/LocationInput'
import type { LocationCoords } from '../types'

export function Settings() {
  const { profile, setProfile, homeLocation, setHomeLocation, showToast, user } = useApp()
  const { fmtDist, distUnit, fmtElevNum, elevUnit, fmtVertPace } = useUnit()

  // Home location input state
  const [pendingHome, setPendingHome] = useState<LocationCoords | null>(homeLocation)
  const [buildingDNA, setBuildingDNA] = useState(false)

  function saveHome() {
    if (!pendingHome) { showToast('Select a location from the dropdown first', 'error'); return }
    setHomeLocation(pendingHome)
    showToast('Home location saved')
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

      {/* ── Route DNA ── */}
      <div className="settings-section">
        <div className="settings-section-title">Rider Profile · Route DNA</div>

        {!p ? (
          <>
            <p style={{ color: 'var(--text-2)', fontSize: 13.5, lineHeight: 1.6, marginBottom: 16 }}>
              Analyse your Strava history to build a personal preference model from your actual rides.
              This shapes all generated routes to match how you truly ride.
            </p>

            <div style={{ background: 'var(--bg)', borderRadius: 8, padding: 16, marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.07em', color: 'var(--text-3)', marginBottom: 10 }}>Strava OAuth setup</div>
              <ol style={{ paddingLeft: 18, color: 'var(--text-2)', fontSize: 13, lineHeight: 2.2, marginBottom: 12 }}>
                <li>Create a Strava API app at <a href="https://www.strava.com/settings/api" target="_blank" rel="noreferrer" style={{ color: 'var(--orange)' }}>strava.com/settings/api</a> — note your Client ID &amp; Secret</li>
                <li>Authorize via URL: <code style={{ background: '#fff', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>
                  https://www.strava.com/oauth/authorize?client_id=YOUR_ID&amp;redirect_uri=http://localhost&amp;response_type=code&amp;scope=read_all,activity:read_all
                </code></li>
                <li>Exchange the <code style={{ background: '#fff', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>code=</code> for tokens via <code style={{ background: '#fff', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>curl -X POST https://www.strava.com/oauth/token</code></li>
                <li>Add <code style={{ background: '#fff', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>STRAVA_CLIENT_ID</code>, <code style={{ background: '#fff', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>STRAVA_CLIENT_SECRET</code>, <code style={{ background: '#fff', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>STRAVA_REFRESH_TOKEN</code> to <code style={{ background: '#fff', padding: '1px 4px', borderRadius: 3, fontSize: 11 }}>.env</code></li>
                <li>Restart the server — tokens auto-refresh every 6 hours</li>
              </ol>
              <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Read-only access. Used locally only.</div>
            </div>

            <button className="btn-primary" disabled={buildingDNA} onClick={buildDNA}>
              {buildingDNA ? 'Connecting to Strava…' : 'Build my Route DNA'}
            </button>
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
