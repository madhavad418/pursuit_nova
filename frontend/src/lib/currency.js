// The API reports every total in the corporate currency. The "view in" picker on the money pages
// re-expresses those figures in another currency on the client, using the live rate table — the
// same one the server converts with, so the two can never disagree. Pure functions only here, so
// they run under `node --test`; the React hook that uses them lives in useViewCurrency.js.

/**
 * Convert an amount that is already in the corporate currency into `view`.
 * `rates` maps CODE -> what one unit of that code is worth in the corporate currency
 * (the server's `rate_to_corporate`), so USD -> INR is a division.
 * Returns null when the target has no usable rate, so callers can fall back rather than show 0.
 */
export function convertFromCorporate(amount, view, corporate, rates) {
  const n = Number(amount || 0)
  if (!view || view === corporate) return n
  const rate = Number(rates?.[view])
  if (!Number.isFinite(rate) || rate <= 0) return null
  return n / rate
}

/** Currencies the picker can offer: the corporate one first, then everything with a usable rate. */
export function viewableCurrencies(corporate, rates) {
  const others = Object.keys(rates || {}).filter(c => c !== corporate && Number(rates[c]) > 0).sort()
  return corporate ? [corporate, ...others] : others
}
