import { useState, useEffect } from 'react'
import { useApp, useUnit } from '../context'
import { api } from '../api'
import { RouteSVGPreview } from '../components/RouteSVGPreview'
import { exportGPX, pushToStrava } from '../components/RouteCard'
import type { LibraryRoute, View } from '../types'

interface Props {
  setView: (v: View) => void
}

const VARIANT_COLORS = { match: '#22c55e', harder: '#f59e0b', scenic: '#818cf8' }

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

function todayLabel() {
  return new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
}

export function Dashboard({ setView }: Props) {
  const { user, profile, showToast } = useApp()
  const { fmtDist, distUnit, fmtElev } = useUnit()

  const [stravaConnected, setStravaConnected] = useState<boolean | null>(null)
  const [recentRoutes, setRecentRoutes] = useState<LibraryRoute[]>([])
  const [loadingRoutes, setLoadingRoutes] = useState(true)

  const firstName = user?.email?.split('@')[0] ?? 'there'

  useEffect(() => {
    api.strava.status()
      .then(s => setStravaConnected(s.connected))
      .catch(() => setStravaConnected(false))

    api.library()
      .then(routes => setRecentRoutes(routes.slice(0, 4)))
      .catch(() => {})
      .finally(() => setLoadingRoutes(false))
  }, [])

  const setupDone = stravaConnected && !!profile
  const setupStep = !stravaConnected ? 0 : !profile ? 1 : 2

  return (
    <div className="dashboard">
      {/* ── Header ── */}
      <div className="dash-header">
        <div>
          <div className="dash-greeting">{greeting()}, {firstName}</div>
          <div className="dash-date">{todayLabel()}</div>
        </div>
        {setupDone && (
          <div className="dash-ready-badge">
            <svg viewBox="0 0 16 16" fill="none" width="13" height="13">
              <polyline points="2 8 6 12 14 4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Ready to ride
          </div>
        )}
      </div>

      {/* ── Setup strip ── */}
      {!setupDone && (
        <div className="dash-setup-card">
          <div className="dash-setup-title">Get started</div>
          <div className="dash-setup-steps">
            <SetupStep
              num={1}
              done={stravaConnected === true}
              active={setupStep === 0}
              label="Connect Strava"
              description="Link your account so we can read your rides."
              action="Connect"
              onAction={() => setView('settings')}
            />
            <div className="setup-step-connector" />
            <SetupStep
              num={2}
              done={!!profile}
              active={setupStep === 1}
              label="Build Route DNA"
              description="Analyse your history to personalise every route."
              action="Build DNA"
              onAction={() => setView('settings')}
            />
            <div className="setup-step-connector" />
            <SetupStep
              num={3}
              done={false}
              active={setupStep === 2}
              label="Generate a route"
              description="Describe a ride and get AI-matched options."
              action="Try it"
              onAction={() => setView('dream')}
            />
          </div>
        </div>
      )}

      {/* ── Quick generate ── */}
      <QuickGenerate setView={setView} profileReady={!!profile} />

      {/* ── Main row: DNA + recent routes ── */}
      <div className="dash-lower">
        {/* DNA snapshot */}
        {profile && (
          <div className="dash-dna-card">
            <div className="dash-card-label">Your Rider Profile</div>
            <div className="dash-dna-tags">
              {(profile.signature_tags ?? []).map(t => (
                <span key={t} className="dna-tag">{t}</span>
              ))}
            </div>
            <div className="dash-dna-stats">
              <div className="dash-dna-stat">
                <span className="dash-dna-val">{fmtDist(profile.median_distance_km)}</span>
                <span className="dash-dna-unit">{distUnit()}</span>
                <div className="dash-dna-lbl">Typical ride</div>
              </div>
              <div className="dash-dna-stat">
                <span className="dash-dna-val">{fmtDist(profile.preferred_distance_km[0])}–{fmtDist(profile.preferred_distance_km[1])}</span>
                <span className="dash-dna-unit">{distUnit()}</span>
                <div className="dash-dna-lbl">Sweet spot</div>
              </div>
              <div className="dash-dna-stat">
                <span className="dash-dna-val">{profile.vert_per_km}</span>
                <span className="dash-dna-unit">m/km</span>
                <div className="dash-dna-lbl">Vert rate</div>
              </div>
            </div>
            <div className="dash-effort-badge">
              {{ negative_split: '↗ Strong Finisher', positive_split: '↘ Front-Loaded', even: '→ Even Paced' }[profile.effort_shape] ?? profile.effort_shape}
            </div>
            <button className="dash-link-btn" onClick={() => setView('settings')}>
              View full profile →
            </button>
          </div>
        )}

        {/* Recent routes */}
        <div className="dash-recent">
          <div className="dash-section-header">
            <div className="dash-card-label">Recent Routes</div>
            {recentRoutes.length > 0 && (
              <button className="dash-link-btn" onClick={() => setView('library')}>View library →</button>
            )}
          </div>

          {loadingRoutes && (
            <div className="dash-empty">Loading…</div>
          )}

          {!loadingRoutes && recentRoutes.length === 0 && (
            <div className="dash-empty-card">
              <div className="dash-empty-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" width="22" height="22" strokeWidth="1.5">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                </svg>
              </div>
              <div className="dash-empty-text">No routes yet</div>
              <div className="dash-empty-sub">Generate your first Dream Ride to see it here.</div>
              <button className="btn-primary" style={{ marginTop: 14, fontSize: 13 }} onClick={() => setView('dream')}>
                Generate a route
              </button>
            </div>
          )}

          {!loadingRoutes && recentRoutes.length > 0 && (
            <div className="dash-route-list">
              {recentRoutes.map(r => {
                const color = VARIANT_COLORS[r.variant] ?? '#22c55e'
                const date = new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                return (
                  <div key={r.id} className="dash-route-item">
                    <div className="dash-route-preview">
                      <RouteSVGPreview geojson={r.geojson} color={color} />
                    </div>
                    <div className="dash-route-info">
                      <div className="dash-route-prompt">"{r.user_prompt}"</div>
                      <div className="dash-route-meta">
                        <span className={`variant-badge ${r.variant}`}>{r.variant}</span>
                        <span>{fmtDist(r.distance_km)} {distUnit()}</span>
                        <span>{fmtElev(r.elevation_m)} ↑</span>
                        <span className="dash-route-date">{date}</span>
                      </div>
                    </div>
                    <div className="dash-route-actions">
                      <button className="lib-btn" onClick={() => exportGPX(r as unknown as import('../types').Route)}>GPX</button>
                      <button className="lib-btn" onClick={() => pushToStrava(
                        r as unknown as import('../types').Route,
                        r.user_prompt,
                        msg => showToast(msg),
                        msg => showToast(msg, 'error'),
                      )}>
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="#FC4C02"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Training shortcuts ── */}
      {profile && (
        <div className="dash-training-strip">
          <div className="dash-card-label" style={{ marginBottom: 14 }}>Training Sessions</div>
          <div className="dash-training-pills">
            {TRAINING_CARDS.map(t => (
              <button key={t.id} className="dash-training-pill" onClick={() => setView('training')}>
                <span className="dash-training-dot" style={{ background: t.color }} />
                <span className="dash-training-name">{t.name}</span>
                <span className="dash-training-arrow">→</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SetupStep({ num, done, active, label, description, action, onAction }: {
  num: number; done: boolean; active: boolean; label: string
  description: string; action: string; onAction: () => void
}) {
  return (
    <div className={`setup-step ${done ? 'done' : active ? 'active' : 'pending'}`}>
      <div className="setup-step-num">
        {done
          ? <svg viewBox="0 0 16 16" fill="none" width="14" height="14"><polyline points="2 8 6 12 14 4" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
          : num
        }
      </div>
      <div className="setup-step-body">
        <div className="setup-step-label">{label}</div>
        <div className="setup-step-desc">{description}</div>
        {active && (
          <button className="setup-step-btn" onClick={onAction}>{action} →</button>
        )}
      </div>
    </div>
  )
}

function QuickGenerate({ setView, profileReady }: { setView: (v: View) => void; profileReady: boolean }) {
  const { homeLocation, showToast, profile } = useApp()
  const { fmtDist, distUnit, fmtElevNum, elevUnit } = useUnit()
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<import('../types').Route[] | null>(null)

  async function generate() {
    if (!prompt.trim()) { showToast('Enter a ride description first', 'error'); return }
    if (!profileReady) { showToast('Build your Route DNA in Settings first', 'error'); return }
    setLoading(true)
    setResult(null)
    try {
      const start = homeLocation
      const body: Parameters<typeof api.dreamRide>[0] = { prompt, is_loop: true }
      if (start) { body.start_lat = start.lat; body.start_lng = start.lng }
      const data = await api.dreamRide(body)
      setResult(data.routes)
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Generation failed', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="dash-generate-card">
      <div className="dash-card-label">Quick Generate</div>
      <div className="dash-generate-row">
        <input
          className="dash-generate-input"
          placeholder={profileReady ? 'Describe a ride… e.g. "60km with a big climb"' : 'Build your Route DNA in Settings to unlock generation'}
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') generate() }}
          disabled={!profileReady}
        />
        <button className="btn-generate" disabled={loading || !profileReady} onClick={generate}>
          <svg viewBox="0 0 24 24" fill="none"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          {loading ? 'Generating…' : 'Generate'}
        </button>
      </div>

      {!profileReady && (
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-3)' }}>
          <button className="dash-link-btn" onClick={() => setView('settings')}>Complete setup →</button>
        </div>
      )}

      {loading && (
        <div className="dash-gen-loading">
          <div className="dot-row"><span/><span/><span/></div>
          <span>Building routes matched to your profile…</span>
        </div>
      )}

      {result && !loading && (
        <div className="dash-gen-results">
          <div className="dash-gen-results-header">
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)' }}>3 routes generated</span>
            <button className="dash-link-btn" onClick={() => setView('dream')}>Open in Dream Ride →</button>
          </div>
          <div className="dash-gen-cards">
            {result.map((r, i) => {
              const score = Math.round((r.score?.total ?? 0) * 100)
              const dist = profile
                ? (r.distance_km * (profile ? 1 : 0.621371)).toFixed(1)
                : r.distance_km.toFixed(1)
              return (
                <div key={i} className="dash-gen-card">
                  <span className={`variant-badge ${r.variant}`}>{r.variant}</span>
                  <div className="dash-gen-card-stats">
                    <strong>{fmtDist(r.distance_km)}</strong> <span className="stat-unit">{distUnit()}</span>
                    <span className="route-stats-sep">·</span>
                    <strong>{fmtElevNum(r.elevation_m ?? 0)}</strong> <span className="stat-unit">{elevUnit()} ↑</span>
                  </div>
                  <div className="dash-gen-score">
                    <div className="score-bar-track" style={{ flex: 1 }}>
                      <div className={`score-bar-fill ${score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low'}`} style={{ width: `${score}%` }} />
                    </div>
                    <span className="score-label">{score}%</span>
                  </div>
                  <div className="dash-gen-card-actions">
                    <button className="lib-btn" onClick={() => exportGPX(r)}>GPX</button>
                    <button className="lib-btn" onClick={() => pushToStrava(
                      r,
                      prompt,
                      msg => showToast(msg),
                      msg => showToast(msg, 'error'),
                    )}>Strava</button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

const TRAINING_CARDS = [
  { id: 'recovery',           name: 'Recovery',           color: '#1EB85F' },
  { id: 'aerobic_base',       name: 'Aerobic Base',       color: '#52A8FF' },
  { id: 'muscular_endurance', name: 'Muscular Endurance', color: '#F0970A' },
  { id: 'threshold',          name: 'Threshold',          color: '#FC4C02' },
  { id: 'vo2max',             name: 'VO₂ Max',            color: '#E53E3E' },
]
