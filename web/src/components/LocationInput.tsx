import { useState, useRef, useCallback, useEffect } from 'react'
import { useApp } from '../context'
import { api } from '../api'
import type { LocationCoords } from '../types'

interface Props {
  placeholder: string
  value: LocationCoords | null
  onChange: (loc: LocationCoords | null) => void
  icon: React.ReactNode
}

export function LocationInput({ placeholder, value, onChange, icon }: Props) {
  const { mbToken } = useApp()
  const [query, setQuery] = useState(value?.name ?? '')
  const [suggestions, setSuggestions] = useState<LocationCoords[]>([])
  const [open, setOpen] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const fieldRef = useRef<HTMLDivElement>(null)
  const suggestionsRef = useRef<HTMLDivElement>(null)

  // Keep input text in sync when value is cleared externally
  useEffect(() => {
    if (!value) setQuery('')
  }, [value])

  const positionDropdown = useCallback(() => {
    if (!fieldRef.current || !suggestionsRef.current) return
    const rect = fieldRef.current.getBoundingClientRect()
    const el = suggestionsRef.current
    el.style.top = `${rect.bottom + 4}px`
    el.style.left = `${rect.left}px`
    el.style.width = `${rect.width}px`
  }, [])

  const fetchSuggestions = useCallback(async (q: string) => {
    if (!mbToken || q.length < 3) { setSuggestions([]); setOpen(false); return }
    const results = await api.geocode(q, mbToken).catch(() => [])
    setSuggestions(results)
    setOpen(results.length > 0)
    positionDropdown()
  }, [mbToken, positionDropdown])

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value
    setQuery(q)
    if (!q) { onChange(null); setSuggestions([]); setOpen(false); return }
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => fetchSuggestions(q), 280)
  }

  const select = (loc: LocationCoords) => {
    onChange(loc)
    setQuery(loc.name)
    setOpen(false)
    setSuggestions([])
  }

  const clear = () => {
    onChange(null)
    setQuery('')
    setSuggestions([])
    setOpen(false)
  }

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!fieldRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Reposition on scroll/resize while open
  useEffect(() => {
    if (!open) return
    const handler = () => positionDropdown()
    window.addEventListener('scroll', handler, true)
    window.addEventListener('resize', handler)
    return () => { window.removeEventListener('scroll', handler, true); window.removeEventListener('resize', handler) }
  }, [open, positionDropdown])

  return (
    <div className="location-field" ref={fieldRef}>
      <span className="loc-icon">{icon}</span>
      <input
        type="text"
        className="location-input"
        placeholder={placeholder}
        value={query}
        onChange={handleInput}
        onFocus={() => query.length >= 3 && fetchSuggestions(query)}
        autoComplete="off"
      />
      <button
        className={`loc-clear ${query ? 'visible' : ''}`}
        onClick={clear}
        title="Clear"
      >✕</button>

      <div
        ref={suggestionsRef}
        className={`location-suggestions ${open ? 'open' : ''}`}
      >
        {suggestions.map((s, i) => (
          <div key={i} className="suggestion-item" onMouseDown={() => select(s)}>
            {s.name}
          </div>
        ))}
      </div>
    </div>
  )
}
