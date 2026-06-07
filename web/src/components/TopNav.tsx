import { useApp, useUnit } from '../context'
import { supabase } from '../lib/supabase'
import type { View } from '../types'

interface Props {
  view: View
  setView: (v: View) => void
  apiStatus: { state: 'ok' | 'err' | 'busy' | 'idle'; label: string }
}

export function TopNav({ view, setView, apiStatus }: Props) {
  const { unit, setUnit, user } = useApp()
  const { fmtDist, distUnit } = useUnit()

  const initials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : '?'

  return (
    <nav className="topnav">
      <div className="topnav-brand">
        <div className="topnav-logo-mark">
          <svg viewBox="0 0 20 20" width="16" height="16" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 15 L8 4 L12 10 L15 6 L18 8" stroke="white" fill="none"/>
          </svg>
        </div>
        <span className="topnav-wordmark">Route AI</span>
      </div>

      <div className="topnav-links">
        <NavLink id="dashboard" label="Home" active={view === 'dashboard'} onClick={() => setView('dashboard')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        </NavLink>
        <NavLink id="dream" label="Dream Ride" active={view === 'dream'} onClick={() => setView('dream')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        </NavLink>
        <NavLink id="training" label="Training" active={view === 'training'} onClick={() => setView('training')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        </NavLink>
        <NavLink id="library" label="Library" active={view === 'library'} onClick={() => setView('library')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
        </NavLink>
        <NavLink id="settings" label="Settings" active={view === 'settings'} onClick={() => setView('settings')}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </NavLink>
      </div>

      <div className="topnav-right">
        <div className="unit-toggle">
          <button className={`unit-btn ${unit === 'metric' ? 'active' : ''}`} onClick={() => setUnit('metric')}>km</button>
          <button className={`unit-btn ${unit === 'imperial' ? 'active' : ''}`} onClick={() => setUnit('imperial')}>mi</button>
        </div>

        <div className="status-dot-wrap" title={apiStatus.label}>
          <span className={`status-dot ${apiStatus.state === 'idle' ? '' : apiStatus.state}`} />
        </div>

        <button
          className="user-avatar"
          title={`${user?.email ?? ''} — Log out`}
          onClick={() => supabase.auth.signOut()}
        >
          {initials}
        </button>
      </div>
    </nav>
  )
}

function NavLink({ id, label, active, onClick, children }: {
  id: string; label: string; active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      id={`nav-${id}`}
      className={`topnav-link ${active ? 'active' : ''}`}
      onClick={onClick}
    >
      {children}
      {label}
    </button>
  )
}
