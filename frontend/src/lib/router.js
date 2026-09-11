import { useEffect, useState } from 'react'

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '') || 'dashboard'
  const [path, query = ''] = raw.split('?')
  return { path: `/${path}`, query: new URLSearchParams(query) }
}
export function navigate(path) {
  const clean = path.startsWith('/') ? path.slice(1) : path
  window.location.hash = `#/${clean}`
}
export function useHashRoute() {
  const [route, setRoute] = useState(parseHash())
  useEffect(() => {
    const fn = () => setRoute(parseHash())
    window.addEventListener('hashchange', fn)
    return () => window.removeEventListener('hashchange', fn)
  }, [])
  return route
}
