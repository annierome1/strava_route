import { useApp } from '../context'

export function Toast() {
  const { toast } = useApp()
  return (
    <div className={`toast ${toast ? 'show' : ''} ${toast?.type === 'error' ? 'error' : ''}`}>
      {toast?.msg}
    </div>
  )
}
