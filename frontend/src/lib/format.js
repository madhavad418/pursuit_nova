// A value of exactly `null` is a field the viewer is not allowed to see (the API masks hidden
// fields to null), so it renders as a dash rather than as a convincing-looking zero. `undefined`
// and 0 are genuine zeros.
export function money(value, currency = 'USD', compact = true) {
  if (value === null) return '—'
  const number = Number(value || 0)
  // Legacy rows can carry "inr" or "INR " — the server normalises the same way before converting.
  const code = String(currency || 'USD').trim().toUpperCase() || 'USD'
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: code,
      maximumFractionDigits: compact ? 1 : 0,
      notation: compact ? 'compact' : 'standard'
    }).format(number)
  } catch {
    // Not an ISO code (e.g. "RS"): label it plainly, honouring compact so it sits next to the others.
    const body = compact ? new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(number) : number.toLocaleString('en-US')
    return `${code} ${body}`
  }
}
// The symbol for a currency code ("₹" for INR, "$" for USD, "AED" when the code has no symbol), for
// labels that show a code next to its sign. Unknown codes come back as themselves.
export function currencySymbol(currency) {
  const code = String(currency || '').trim().toUpperCase()
  if (!code) return ''
  try {
    const part = new Intl.NumberFormat('en-US', { style: 'currency', currency: code, currencyDisplay: 'narrowSymbol' }).formatToParts(1).find(p => p.type === 'currency')
    return part ? part.value : code
  } catch { return code }
}
// Date and time in the viewer's own time zone, e.g. "16 Sept 2026, 4:45 pm". Expects an ISO timestamp with a zone (…Z).
export function dateTimeText(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true })
}

export function dateText(value) {
  if (!value) return '—'
  const d = new Date(`${String(value).slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}
export function pct(value) { return `${Number(value || 0).toFixed(0)}%` }
export function initials(name = '') { return name.split(/\s+/).filter(Boolean).slice(0, 2).map(x => x[0]).join('').toUpperCase() || 'PN' }
export function classNames(...parts) { return parts.filter(Boolean).join(' ') }
