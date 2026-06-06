import { useState } from 'react'
import { useApp } from '../context'
import { api } from '../api'
import { RouteCard, exportGPX, exportToStrava } from '../components/RouteCard'
import type { Route } from '../types'

const ADAPTATIONS = [
  {
    id: 'recovery',
    name: 'Recovery',
    tagline: 'Spin it out',
    color: '#1EB85F',
    distMult: '×0.5',
    vertTarget: '4 m/km',
    rationale: 'Flat, familiar, zero stress. Let the legs breathe.',
  },
  {
    id: 'aerobic_base',
    name: 'Aerobic Base',
    tagline: 'Build the engine',
    color: '#52A8FF',
    distMult: '×1.25',
    vertTarget: '8 m/km',
    rationale: 'Long, steady, low-stress. Build aerobic capacity without spiking fatigue.',
  },
  {
    id: 'muscular_endurance',
    name: 'Muscular Endurance',
    tagline: 'Sustain the grind',
    color: '#F0970A',
    distMult: '×1.1',
    vertTarget: '12 m/km',
    rationale: 'Continuous moderate grade. Builds leg strength without blowing up.',
  },
  {
    id: 'threshold',
    name: 'Threshold',
    tagline: 'Find your ceiling',
    color: '#FC4C02',
    distMult: '×0.85',
    vertTarget: '15 m/km',
    rationale: 'One sustained climb in the middle third. Threshold effort on the ascent.',
  },
  {
    id: 'vo2max',
    name: 'VO₂ Max',
    tagline: 'Go to the limit',
    color: '#E53E3E',
    distMult: '×0.65',
    vertTarget: '22 m/km',
    rationale: 'Short, hard, punchy. Multiple sharp climbs. Nothing sustained.',
  },
]

export function Training() {
  const { profile, showToast } = useApp()
  const [loading, setLoading] = useState<string | null>(null)
  const [result, setResult] = useState<{ title: string; explanation: string; routes: Route[] } | null>(null)

  async function generate(id: string, name: string) {
    if (!profile) { showToast('Build your Route DNA in Settings first', 'error'); return }
    setLoading(id)
    setResult(null)
    try {
      const data = await api.trainingRoute(id)
      setResult({ title: name + ' Route', explanation: data.recipe_explanation, routes: data.routes })
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : 'Generation failed', 'error')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div id="training-view" className="view active">
      <div className="page-header">
        <div className="page-title">Training Routes</div>
        <div className="page-sub">Routes prescribed for specific physiological adaptations — calibrated to your actual fitness history.</div>
      </div>

      <div className="section-label">Choose a session type</div>

      <div className="adaptations-grid">
        {ADAPTATIONS.map(a => (
          <div
            key={a.id}
            className={`adapt-card ${loading === a.id ? 'loading' : ''}`}
            onClick={() => generate(a.id, a.name)}
          >
            <div className="adapt-header">
              <span className="effort-pip" style={{ background: a.color }}/>
              <span className="adapt-name">{a.name}</span>
            </div>
            <div className="adapt-tagline">{a.tagline}</div>
            <div className="adapt-params">
              <div className="adapt-param">
                <span className="adapt-param-val">{a.distMult}</span>
                <span className="adapt-param-lbl">Distance</span>
              </div>
              <div className="adapt-param">
                <span className="adapt-param-val">{a.vertTarget}</span>
                <span className="adapt-param-lbl">Vert target</span>
              </div>
            </div>
            <div className="adapt-rationale">{a.rationale}</div>
            <div className="btn-adapt">
              Generate route{' '}
              <svg viewBox="0 0 24 24" fill="none">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
              </svg>
            </div>
          </div>
        ))}
      </div>

      {result && (
        <div className="training-results">
          <div className="results-section-header">
            <div className="results-section-title">{result.title}</div>
          </div>
          <div className="recipe-banner" style={{ marginBottom: 16 }}>
            <div>{result.explanation}</div>
          </div>
          <div className="routes-grid">
            {result.routes.map((route, i) => (
              <RouteCard
                key={`${route.variant}-${i}`}
                route={route}
                onExportGPX={() => exportGPX(route)}
                onExportStrava={() => exportToStrava(route)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
