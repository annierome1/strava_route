import { useEffect, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import { useApp, useUnit } from '../context'
import type { Route } from '../types'

const VARIANT_META = {
  match:  { label: 'Best Match', cls: 'match',  lineColor: '#22c55e' },
  harder: { label: 'Harder',     cls: 'harder', lineColor: '#f59e0b' },
  scenic: { label: 'Scenic',     cls: 'scenic', lineColor: '#6366f1' },
} as const

interface Props {
  route: Route
  onExportGPX: () => void
  onExportStrava: () => void
}

export function RouteCard({ route, onExportGPX, onExportStrava }: Props) {
  const { mbToken } = useApp()
  const { fmtDist, distUnit, fmtElevNum, elevUnit } = useUnit()
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)

  const meta = VARIANT_META[route.variant] ?? VARIANT_META.match
  const score = route.score?.total ?? 0
  const scorePct = Math.round(score * 100)
  const scoreClass = score >= 0.8 ? 'high' : score >= 0.6 ? 'mid' : 'low'

  useEffect(() => {
    if (!mbToken || !containerRef.current || !route.geojson?.coordinates?.length) return
    mapboxgl.accessToken = mbToken

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      interactive: false,
      attributionControl: false,
    })
    mapRef.current = map

    map.on('load', () => {
      const coords = route.geojson.coordinates
      map.addSource('route', { type: 'geojson', data: { type: 'Feature', geometry: route.geojson as unknown as GeoJSON.Geometry, properties: {} } })
      map.addLayer({
        id: 'route-line', type: 'line', source: 'route',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': meta.lineColor, 'line-width': 3, 'line-opacity': 0.9 },
      })
      const lngs = coords.map(c => c[0])
      const lats = coords.map(c => c[1])
      map.fitBounds(
        [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
        { padding: 22, duration: 0 }
      )
    })

    return () => { map.remove(); mapRef.current = null }
  }, [mbToken, route.geojson, meta.lineColor])

  return (
    <div className="route-card">
      <div className="route-map-wrap">
        {mbToken
          ? <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
          : <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#444', fontSize: 12 }}>No Mapbox token</div>
        }
      </div>

      <div className="route-card-body">
        <div className="route-card-header">
          <span className={`variant-badge ${meta.cls}`}>{meta.label}</span>
          {route.rank === 1 && <span className="rank-star">★</span>}
          {route.is_similar_to_saved && (
            <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 'auto' }} title="Similar to a saved route">📚 saved before</span>
          )}
        </div>

        <div className="route-stats">
          <span>{fmtDist(route.distance_km)}</span>
          <span className="stat-unit"> {distUnit()}</span>
          <span className="route-stats-sep">·</span>
          <span>{fmtElevNum(route.elevation_m ?? 0)}</span>
          <span className="stat-unit"> {elevUnit()} ↑</span>
        </div>

        <div className="route-score-row">
          <div className="score-bar-track">
            <div
              className={`score-bar-fill ${scoreClass}`}
              style={{ width: `${scorePct}%` }}
            />
          </div>
          <span className="score-label">{scorePct}%</span>
        </div>

        {route.explanation && (
          <div className="route-explanation">{route.explanation}</div>
        )}

        <div className="route-card-footer">
          <button className="btn-export" onClick={e => { e.stopPropagation(); onExportGPX() }}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 1a.5.5 0 0 1 .5.5v7.793l2.146-2.147a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 0 1 .708-.708L7.5 9.293V1.5A.5.5 0 0 1 8 1zM1 13.5a.5.5 0 0 1 .5-.5h13a.5.5 0 0 1 0 1h-13a.5.5 0 0 1-.5-.5z"/>
            </svg>
            Download GPX
          </button>
          <button className="btn-export strava" onClick={e => { e.stopPropagation(); onExportStrava() }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
              <path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/>
            </svg>
            Export to Strava
          </button>
        </div>
      </div>
    </div>
  )
}

export function exportGPX(route: Route): void {
  if (!route?.geojson?.coordinates?.length) return
  const label = { match: 'Match', harder: 'Harder', scenic: 'Scenic' }[route.variant] ?? route.variant
  const name = `RouteAI — ${label} ${route.distance_km}km`
  const now = new Date().toISOString()
  const trkpts = route.geojson.coordinates.map(([lng, lat, ele]) => {
    const eleTag = ele != null && !isNaN(ele) ? `\n        <ele>${ele.toFixed(1)}</ele>` : ''
    return `      <trkpt lat="${lat.toFixed(7)}" lon="${lng.toFixed(7)}">${eleTag}\n      </trkpt>`
  }).join('\n')

  const gpx = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="RouteAI" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>${name}</name><time>${now}</time></metadata>
  <trk><name>${name}</name><type>cycling</type><trkseg>
${trkpts}
  </trkseg></trk>
</gpx>`

  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([gpx], { type: 'application/gpx+xml' }))
  a.download = `${label.toLowerCase()}_${route.distance_km}km.gpx`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

export function exportToStrava(route: Route): void {
  exportGPX(route)
  setTimeout(() => window.open('https://www.strava.com/routes/new', '_blank', 'noopener'), 400)
}
