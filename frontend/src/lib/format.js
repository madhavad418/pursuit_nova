export function money(value, currency = 'USD', compact = true) {
  const number = Number(value || 0)
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency,
      maximumFractionDigits: compact ? 1 : 0,
      notation: compact ? 'compact' : 'standard'
    }).format(number)
  } catch { return `${currency} ${number.toLocaleString()}` }
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
