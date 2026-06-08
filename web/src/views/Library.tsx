import { useState, useEffect, useMemo } from 'react'
import { useApp, useUnit } from '../context'
import { api } from '../api'
import { RouteSVGPreview } from '../components/RouteSVGPreview'
import { exportGPX } from '../components/RouteCard'
import type { LibraryRoute, Variant } from '../types'

type SortKey = 'newest' | 'oldest' | 'dist-hi' | 'dist-lo' | 'elev-hi' | 'elev-lo'
type LibView = 'list' | 'grid'

const VARIANT_COLORS: Record<Variant, string> = {
  match:  '#22c55e',
  harder: '#f59e0b',
  scenic: '#6366f1',
}

export function Library() {
  const { showToast } = useApp()
  const { fmtDist, distUnit, fmtElev } = useUnit()

  const [routes, setRoutes] = useState<LibraryRoute[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Variant | 'all'>('all')
  const [sort, setSort] = useState<SortKey>('newest')
  const [view, setView] = useState<LibView>('list')

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      setRoutes(await api.library())
    } catch {
      showToast('Failed to load library', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function deleteRoute(id: string) {
    await api.deleteRoute(id).catch(() => null)
    setRoutes(prev => prev.filter(r => r.id !== id))
  }

  async function cleanup() {
    const data = await api.cleanupLibrary().catch(() => null)
    if (data) {
      showToast(`Removed ${data.deleted} duplicate${data.deleted !== 1 ? 's' : ''}`)
      await load()
    }
  }

  function pushToStrava(route: LibraryRoute) {
    exportGPX(route as unknown as import('../types').Route)
    setTimeout(() => window.open('https://www.strava.com/routes/new', '_blank', 'noopener'), 400)
    showToast('GPX saved to Downloads — drag it into the Strava page that just opened')
  }

  const filtered = useMemo(() => {
    let r = routes
    if (filter !== 'all') r = r.filter(x => x.variant === filter)
    if (search) r = r.filter(x => x.user_prompt.toLowerCase().includes(search.toLowerCase()))
    const sortFns: Record<SortKey, (a: LibraryRoute, b: LibraryRoute) => number> = {
      'newest':  (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      'oldest':  (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      'dist-hi': (a, b) => b.distance_km - a.distance_km,
      'dist-lo': (a, b) => a.distance_km - b.distance_km,
      'elev-hi': (a, b) => b.elevation_m - a.elevation_m,
      'elev-lo': (a, b) => a.elevation_m - b.elevation_m,
    }
    return [...r].sort(sortFns[sort])
  }, [routes, filter, search, sort])

  const totalDist = routes.reduce((s, r) => s + r.distance_km, 0)
  const totalElev = routes.reduce((s, r) => s + r.elevation_m, 0)

  return (
    <div id="library-view" className="view active">
      <div className="page-header" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div className="page-title">Route Library</div>
          <div className="page-sub">Every route you've generated — search, filter, and revisit anytime.</div>
        </div>
        {routes.length > 0 && (
          <button className="btn-secondary" style={{ marginTop: 4, fontSize: 12 }} onClick={cleanup}>
            Remove duplicates
          </button>
        )}
      </div>

      

      {/* Toolbar */}
      <div className="lib-toolbar">
        <div className="lib-search">
          <svg className="lib-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" width="14" height="14">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            className="lib-search-input"
            placeholder="Search by route description…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <select className="lib-sort-select" value={sort} onChange={e => setSort(e.target.value as SortKey)}>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="dist-hi">Longest first</option>
          <option value="dist-lo">Shortest first</option>
          <option value="elev-hi">Most elevation</option>
          <option value="elev-lo">Least elevation</option>
        </select>

        <div className="view-toggle">
          <button className={`view-toggle-btn ${view === 'list' ? 'active' : ''}`} onClick={() => setView('list')} title="List view">
            <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
              <rect x="1" y="2" width="14" height="2.5" rx="1"/>
              <rect x="1" y="6.75" width="14" height="2.5" rx="1"/>
              <rect x="1" y="11.5" width="14" height="2.5" rx="1"/>
            </svg>
          </button>
          <button className={`view-toggle-btn ${view === 'grid' ? 'active' : ''}`} onClick={() => setView('grid')} title="Grid view">
            <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
              <rect x="1" y="1" width="6.5" height="6.5" rx="1"/>
              <rect x="8.5" y="1" width="6.5" height="6.5" rx="1"/>
              <rect x="1" y="8.5" width="6.5" height="6.5" rx="1"/>
              <rect x="8.5" y="8.5" width="6.5" height="6.5" rx="1"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Filter pills */}
      <div className="lib-filter-row">
        {(['all', 'match', 'harder', 'scenic'] as const).map(f => (
          <button
            key={f}
            className={`lib-filter-pill ${f !== 'all' ? f : ''} ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading && (
        <div style={{ color: 'var(--text-3)', fontSize: 13, padding: '20px 0' }}>Loading…</div>
      )}

      {!loading && filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-3)', fontSize: 14 }}>
          {routes.length === 0
            ? 'No saved routes yet — generate a Dream Ride to start your library.'
            : 'No routes match your search or filter.'}
        </div>
      )}

      {!loading && filtered.length > 0 && (
        view === 'list'
          ? <LibList routes={filtered} onDelete={deleteRoute} onPushStrava={r => pushToStrava(r)} />
          : <LibGrid routes={filtered} onDelete={deleteRoute} onPushStrava={r => pushToStrava(r)} />
      )}
    </div>
  )
}

function LibList({
  routes,
  onDelete,
  onPushStrava,
}: {
  routes: LibraryRoute[]
  onDelete: (id: string) => void
  onPushStrava: (route: LibraryRoute) => void
}) {
  const { fmtDist, distUnit, fmtElev } = useUnit()

  return (
    <div className="library-list">
      {routes.map(r => {
        const color = VARIANT_COLORS[r.variant] ?? '#22c55e'
        const date = new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        return (
          <div key={r.id} className="library-item">
            <div className="lib-preview-mini">
              <RouteSVGPreview geojson={r.geojson} color={color} />
            </div>
            <div className="lib-variant">
              <span className={`variant-badge ${r.variant}`}>
                {r.variant === 'match' ? 'Match' : r.variant.charAt(0).toUpperCase() + r.variant.slice(1)}
              </span>
            </div>
            <div className="lib-info">
              <div className="lib-prompt">"{r.user_prompt}"</div>
              <div className="lib-stats">
                <span>{fmtDist(r.distance_km)} {distUnit()}</span>
                <span>{fmtElev(r.elevation_m)}</span>
                <span className="lib-date">{date}</span>
              </div>
            </div>
            <div className="lib-actions">
              <button className="lib-btn" onClick={() => exportGPX(r as unknown as import('../types').Route)}>GPX</button>
              <button className="lib-btn" onClick={() => onPushStrava(r)}>Strava ↑</button>
              <button className="lib-btn delete" onClick={() => onDelete(r.id)}>✕</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function LibGrid({
  routes,
  onDelete,
  onPushStrava,
}: {
  routes: LibraryRoute[]
  onDelete: (id: string) => void
  onPushStrava: (route: LibraryRoute) => void
}) {
  const { fmtDist, distUnit, fmtElev } = useUnit()

  return (
    <div className="library-grid">
      {routes.map(r => {
        const color = VARIANT_COLORS[r.variant] ?? '#22c55e'
        const date = new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        return (
          <div key={r.id} className="lib-grid-card">
            <div className="lib-grid-preview">
              <RouteSVGPreview geojson={r.geojson} color={color} />
            </div>
            <div className="lib-grid-body">
              <div className="lib-grid-meta">
                <span className={`variant-badge ${r.variant}`}>
                  {r.variant === 'match' ? 'Match' : r.variant.charAt(0).toUpperCase() + r.variant.slice(1)}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{date}</span>
              </div>
              <div className="lib-grid-prompt">"{r.user_prompt}"</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="lib-grid-nums">
                  {fmtDist(r.distance_km)} <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-3)' }}>{distUnit()}</span>
                </span>
                <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{fmtElev(r.elevation_m)} ↑</span>
              </div>
              <div className="lib-grid-actions">
                <button className="lib-btn" style={{ flex: 1 }} onClick={() => exportGPX(r as unknown as import('../types').Route)}>GPX</button>
                <button className="lib-btn" onClick={() => onPushStrava(r)}>Strava ↑</button>
                <button className="lib-btn delete" onClick={() => onDelete(r.id)}>✕</button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
