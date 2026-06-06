import { useState, useEffect } from 'react'
import { useApp } from './context'
import { api } from './api'
import { Sidebar } from './components/Sidebar'
import { Toast } from './components/Toast'
import { DreamRide } from './views/DreamRide'
import { Training } from './views/Training'
import { Settings } from './views/Settings'
import { Library } from './views/Library'
import { Auth } from './views/Auth'
import { supabase } from './lib/supabase'
import type { View } from './types'

export default function App() {
  const { setProfile, setMbToken, session } = useApp()
  const [view, setView] = useState<View>('dream')
  const [authReady, setAuthReady] = useState(false)
  const [apiStatus, setApiStatus] = useState<{ state: 'ok' | 'err' | 'busy' | 'idle'; label: string }>({
    state: 'idle',
    label: 'Connecting…',
  })

  // Wait for Supabase to restore session before deciding what to show
  useEffect(() => {
    supabase.auth.getSession().then(() => setAuthReady(true))
  }, [])

  useEffect(() => {
    if (!session) return
    async function boot() {
      try {
        const cfg = await api.config()
        setMbToken(cfg.mapbox_token ?? '')
        if (!cfg.has_anthropic) {
          setApiStatus({ state: 'err', label: 'Missing ANTHROPIC_API_KEY' })
        } else if (!cfg.has_graphhopper) {
          setApiStatus({ state: 'err', label: 'Missing GRAPHHOPPER_API_KEY' })
        } else {
          setApiStatus({ state: 'ok', label: 'Connected' })
        }
        const p = await api.dnaProfile().catch(() => null)
        if (p) setProfile(p)
      } catch {
        setApiStatus({ state: 'err', label: 'API offline — start the server' })
      }
    }
    boot()
  }, [session, setProfile, setMbToken])

  if (!authReady) return null

  if (!session) return <Auth />

  return (
    <div className="app">
      <Sidebar view={view} setView={setView} apiStatus={apiStatus} />
      <main>
        {view === 'dream'    && <DreamRide />}
        {view === 'training' && <Training />}
        {view === 'settings' && <Settings />}
        {view === 'library'  && <Library />}
      </main>
      <Toast />
    </div>
  )
}
