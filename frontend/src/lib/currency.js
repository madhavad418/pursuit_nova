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

/**
 * Convert an amount held in the currency it was booked in (`code`) into `view`.
 *
 * Totals arrive from the API already in the corporate currency, so `convertFromCorporate` is all
 * they need. A single record does not: it carries its own native amount and its own code. Rendering
 * that raw under a converted total is what put a ₹100,000 card beneath a £ column header — the
 * figures were each right on their own terms and wrong next to each other.
 *
 * `rates` is expressed against the corporate currency, so this goes native -> corporate -> view.
 * Returns null when either leg has no usable rate, so the caller shows the real native amount and
 * says so, rather than a number that looks converted but is not.
 */
export function convertBetween(amount, code, view, corporate, rates) {
  const n = Number(amount || 0)
  // Legacy rows can carry "inr" or "INR " — the server normalises the same way before converting.
  const from = String(code || '').trim().toUpperCase() || corporate
  if (!view || from === view) return n
  let inCorporate = n
  if (from !== corporate) {
    const rate = Number(rates?.[from])
    if (!Number.isFinite(rate) || rate <= 0) return null
    inCorporate = n * rate
  }
  return convertFromCorporate(inCorporate, view, corporate, rates)
}

/** Currencies the picker can offer: the corporate one first, then everything with a usable rate. */
export function viewableCurrencies(corporate, rates) {
  const others = Object.keys(rates || {}).filter(c => c !== corporate && Number(rates[c]) > 0).sort()
  return corporate ? [corporate, ...others] : others
}
