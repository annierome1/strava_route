import { useState } from 'react'
import { supabase } from '../lib/supabase'

const FEATURES = [
  'AI routes built from your actual ride history',
  'Personalised training sessions by effort type',
  'GPX export & direct Strava upload',
]

export function Auth() {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'signup') {
        const { error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        setSent(true)
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-root">
      {/* ── Hero panel ── */}
      <div className="auth-hero">
        <div className="auth-hero-logo">
          <div className="auth-hero-mark">
            <svg viewBox="0 0 20 20" width="18" height="18" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 15 L8 4 L12 10 L15 6 L18 8" stroke="white" fill="none"/>
            </svg>
          </div>
          <span className="auth-hero-brand">Route AI</span>
        </div>

        <div className="auth-hero-tagline">
          Every route, built for how you <span>actually</span> ride.
        </div>
        <div className="auth-hero-sub">
          Connect Strava, build your rider profile, and let AI design routes matched to your fitness and style.
        </div>

        <div className="auth-hero-features">
          {FEATURES.map(f => (
            <div key={f} className="auth-feature">
              <div className="auth-feature-dot" />
              <span className="auth-feature-text">{f}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Form panel ── */}
      <div className="auth-panel">
        {sent ? (
          <div className="auth-sent">
            <div className="auth-sent-icon">✉️</div>
            <div className="auth-sent-title">Check your inbox</div>
            <div className="auth-sent-sub">
              We sent a confirmation link to <strong>{email}</strong>.<br/>
              Click it, then come back and log in.
            </div>
            <button className="auth-submit" onClick={() => { setSent(false); setMode('login') }}>
              Back to log in
            </button>
          </div>
        ) : (
          <>
            <div className="auth-panel-title">
              {mode === 'login' ? 'Welcome back' : 'Create your account'}
            </div>
            <div className="auth-panel-sub">
              {mode === 'login' ? 'Log in to continue to Route AI.' : 'Free to start — no credit card needed.'}
            </div>

            <div className="auth-tabs">
              <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Log in</button>
              <button className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>Sign up</button>
            </div>

            <form onSubmit={submit} className="auth-form">
              <label>
                Email
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="you@example.com"
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                  placeholder="••••••••"
                  minLength={6}
                />
              </label>
              {error && <div className="auth-error">{error}</div>}
              <button type="submit" className="auth-submit" disabled={loading}>
                {loading ? '…' : mode === 'login' ? 'Log in' : 'Create account'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
