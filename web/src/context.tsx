import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import type { TasteProfile, Unit, LocationCoords } from './types'
import { supabase } from './lib/supabase'

interface Toast { msg: string; type: 'error' | '' }

interface AppCtx {
  unit: Unit
  setUnit: (u: Unit) => void
  profile: TasteProfile | null
  setProfile: (p: TasteProfile) => void
  mbToken: string
  setMbToken: (t: string) => void
  homeLocation: LocationCoords | null
  setHomeLocation: (l: LocationCoords | null) => void
  toast: Toast | null
  showToast: (msg: string, type?: 'error' | '') => void
  session: Session | null
  user: User | null
}

const Ctx = createContext<AppCtx>(null!)
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }: { children: ReactNode }) {
  const [unit, setUnit] = useState<Unit>('metric')
  const [profile, setProfile] = useState<TasteProfile | null>(null)
  const [mbToken, setMbToken] = useState('')
  const [session, setSession] = useState<Session | null>(null)
  const [homeLocation, setHomeLocationState] = useState<LocationCoords | null>(() => {
    try {
      const s = localStorage.getItem('routeai_home')
      return s ? JSON.parse(s) : null
    } catch { return null }
  })
  const [toast, setToast] = useState<Toast | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_ev, s) => setSession(s))
    return () => subscription.unsubscribe()
  }, [])

  const showToast = useCallback((msg: string, type: 'error' | '' = '') => {
    setToast({ msg, type })
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setToast(null), 3200)
  }, [])

  const setHomeLocation = useCallback((l: LocationCoords | null) => {
    setHomeLocationState(l)
    if (l) localStorage.setItem('routeai_home', JSON.stringify(l))
    else localStorage.removeItem('routeai_home')
  }, [])

  return (
    <Ctx.Provider value={{
      unit, setUnit,
      profile, setProfile,
      mbToken, setMbToken,
      homeLocation, setHomeLocation,
      toast, showToast,
      session, user: session?.user ?? null,
    }}>
      {children}
    </Ctx.Provider>
  )
}

export function useUnit() {
  const { unit } = useApp()
  const fmtDist = (km: number) => unit === 'imperial' ? (km * 0.621371).toFixed(1) : km.toFixed(1)
  const distUnit = () => unit === 'imperial' ? 'mi' : 'km'
  const fmtElevNum = (m: number) =>
    unit === 'imperial' ? Math.round(m * 3.28084).toLocaleString() : Math.round(m).toLocaleString()
  const elevUnit = () => unit === 'imperial' ? 'ft' : 'm'
  const fmtElev = (m: number) => `${fmtElevNum(m)} ${elevUnit()}`
  const fmtVertPace = (mPerKm: number) =>
    unit === 'imperial' ? `${Math.round(mPerKm * 5.28)} ft/mi` : `${mPerKm} m/km`
  return { fmtDist, distUnit, fmtElevNum, elevUnit, fmtElev, fmtVertPace }
}
