const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
let csrfToken = null

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message)
    this.status = status
    this.payload = payload
  }
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { Accept: 'application/json', ...(options.headers || {}) }
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!csrfToken) await refreshCsrf()
    headers['X-CSRF-Token'] = csrfToken
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    headers,
    credentials: 'include'
  })
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    if (response.status === 403 && payload?.detail === 'CSRF validation failed') {
      csrfToken = null
    }
    throw new ApiError(payload?.detail || payload?.message || `Request failed (${response.status})`, response.status, payload)
  }
  return payload
}

export async function refreshCsrf() {
  const response = await fetch(`${API_BASE}/api/auth/csrf`, { credentials: 'include' })
  if (!response.ok) throw new ApiError('Unable to refresh security token', response.status)
  const payload = await response.json()
  csrfToken = payload.csrf_token
  return csrfToken
}

export async function login(email, password, otp = '') {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password, otp: otp || null })
  })
  const payload = await response.json()
  if (!response.ok) throw new ApiError(payload?.detail || `Login failed (${response.status})`, response.status, payload)
  csrfToken = payload.csrf_token
  return payload
}

export async function logout() {
  try { await request('/api/auth/logout', { method: 'POST' }) } finally { csrfToken = null }
}

export const api = {
  get: (path) => request(path),
  post: (path, data) => request(path, { method: 'POST', body: JSON.stringify({ data }) }),
  put: (path, data) => request(path, { method: 'PUT', body: JSON.stringify({ data }) }),
  delete: (path) => request(path, { method: 'DELETE' }),
  raw: request,
  base: API_BASE
}
