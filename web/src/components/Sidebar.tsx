import { useApp, useUnit } from '../context'
import type { View } from '../types'

interface Props {
  view: View
  setView: (v: View) => void
  apiStatus: { state: 'ok' | 'err' | 'busy' | 'idle'; label: string }
}

export function Sidebar({ view, setView, apiStatus }: Props) {
  const { unit, setUnit, profile } = useApp()
  const { fmtDist, distUnit } = useUnit()

  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">
          <svg viewBox="0 0 20 20" width="18" height="18">
            <path d="M6 16 L10 4 L14 10 L17 6" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
          </svg>
        </div>
        <div>
          <div className="logo-text">Routes</div>
          <span className="logo-sub">AI Route Planner</span>
        </div>
      </div>

      <div className="sidebar-nav">
        <NavItem id="dream" label="Dream Ride" active={view === 'dream'} onClick={() => setView('dream')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        </NavItem>
        <NavItem id="training" label="Training" active={view === 'training'} onClick={() => setView('training')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        </NavItem>
        <NavItem id="settings" label="Settings" active={view === 'settings'} onClick={() => setView('settings')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </NavItem>
        <NavItem id="library" label="Library" active={view === 'library'} onClick={() => setView('library')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
        </NavItem>
      </div>

      <div className="sidebar-footer">
        <div className="unit-toggle">
          <button className={`unit-btn ${unit === 'metric' ? 'active' : ''}`} onClick={() => setUnit('metric')}>metric</button>
          <button className={`unit-btn ${unit === 'imperial' ? 'active' : ''}`} onClick={() => setUnit('imperial')}>imperial</button>
        </div>

        <div className="api-status">
          <span className={`status-dot ${apiStatus.state === 'idle' ? '' : apiStatus.state}`}></span>
          <span>{apiStatus.label}</span>
        </div>

        {profile && (
          <div className="profile-chip">
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 4 }}>Your DNA</div>
            <div className="profile-chip-tags">
              {(profile.signature_tags ?? []).slice(0, 3).map(t => (
                <span key={t} className="chip orange">{t}</span>
              ))}
              <span className="chip">
                {fmtDist(profile.median_distance_km)} {distUnit()} avg
              </span>
            </div>
          </div>
        )}
      </div>
    </nav>
  )
}

function NavItem({ id, label, active, onClick, children }: {
  id: string; label: string; active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <div id={`nav-${id}`} className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}>
      {children}
      {label}
    </div>
  )
}
