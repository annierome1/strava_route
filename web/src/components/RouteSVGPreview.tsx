import type { GeoJSONLine } from '../types'

interface Props {
  geojson: GeoJSONLine
  color: string
  width?: number
  height?: number
}

export function RouteSVGPreview({ geojson, color, width = 200, height = 120 }: Props) {
  const coords = geojson?.coordinates ?? []
  if (!coords.length) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#333', fontSize: 11 }}>—</div>
  }

  const lngs = coords.map(c => c[0])
  const lats = coords.map(c => c[1])
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs)
  const minLat = Math.min(...lats), maxLat = Math.max(...lats)
  const pad = 10
  const xRange = maxLng - minLng || 0.001
  const yRange = maxLat - minLat || 0.001
  const scale = Math.min((width - pad * 2) / xRange, (height - pad * 2) / yRange)
  const offX = (width - xRange * scale) / 2
  const offY = (height - yRange * scale) / 2

  const points = coords
    .map(c => {
      const x = offX + (c[0] - minLng) * scale
      const y = height - (offY + (c[1] - minLat) * scale)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height="100%"
      preserveAspectRatio="xMidYMid meet"
      style={{ display: 'block' }}
    >
      <rect width={width} height={height} fill="#0F1117" />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
