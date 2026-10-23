import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { RATES_TTL_MS, convertFromCorporate, ratesAreStale, viewableCurrencies } from './currency'

const STORAGE_KEY = 'pn.viewCurrency'
function readSaved() { try { return localStorage.getItem(STORAGE_KEY) || '' } catch { return '' } }
function writeSaved(v) { try { v ? localStorage.setItem(STORAGE_KEY, v) : localStorage.removeItem(STORAGE_KEY) } catch {} }

// How often an open tab re-checks. The check is a no-op while the table is inside its TTL, so this
// only has to be often enough that a re-validation lands soon after the TTL expires.
const RECHECK_MS = 60 * 1000

// ---------------------------------------------------------------- one rate table for the whole app
// Up to three of these hooks mount at once (a page, its editor modal, a drawer) and they all want
// the same table. Holding it here means one request instead of three, and a second money page
// renders with rates already in hand rather than flashing the corporate currency.
//
// The table is re-validated rather than held for the session, because every figure on a money page
// is derived from it: a tab that keeps a superseded rate shows numbers that are wrong with no
// outward sign, which is how a placeholder GBP of 1.27 kept being divided into totals for a week
// after the live 1.33923 had landed on the server.
let table = null        // the last payload, success or failure
let fetchedAt = 0       // when it landed (epoch ms); 0 until the first success
let inflight = null     // a request already in the air, awaited by every caller rather than repeated
const listeners = new Set()

function publish(payload) { table = payload; listeners.forEach(fn => fn(payload)) }

function loadRates({ force = false } = {}) {
  if (!force && table && !ratesAreStale(fetchedAt)) return Promise.resolve(table)
  if (!inflight) {
    inflight = api.get('/api/currency/rates')
      .then(payload => { fetchedAt = Date.now(); publish(payload); return payload })
      // A failed fetch is published so the picker can say so, but deliberately not stamped, so the
      // next look retries instead of leaving the page unconvertible until the TTL lapses.
      .catch(() => { const payload = { failed: true, rates: {} }; publish(payload); return payload })
      .finally(() => { inflight = null })
  }
  return inflight
}

/**
 * Drop the shared table so the next read re-fetches.
 *
 * Called on sign-out, and by the admin screens straight after they change the rates — the person who
 * just pressed "Refresh rates now" is the one most likely to switch to a money page and check,
 * and waiting out the TTL would show them the rates they had just replaced.
 */
export function resetViewCurrency() { table = null; fetchedAt = 0; inflight = null }

/**
 * Loads the rate table and exposes a display currency plus a converter bound to it.
 *
 * `pageCurrency` is the corporate currency the page's own API response reports. It is the
 * fallback while the rates are loading or if they fail to load, so a page never labels its
 * figures with a currency the server did not report (a hard-coded 'USD' used to do exactly that
 * for an INR-based deployment). The choice is a per-viewer convenience kept in localStorage; a
 * saved currency that has since lost its rate silently falls back to the corporate currency.
 */
export function useViewCurrency(pageCurrency) {
  const [fx, setFx] = useState(table)
  const [choice, setChoice] = useState(readSaved)

  useEffect(() => {
    listeners.add(setFx)
    loadRates()
    // Re-check on a timer and whenever the tab comes back to the foreground, which is when someone
    // actually looks at the figures. Both go through the TTL, so returning to a tab within a few
    // minutes costs nothing while a longer absence gets whatever the server now holds.
    const recheck = () => { if (document.visibilityState !== 'hidden') loadRates() }
    const timer = setInterval(recheck, RECHECK_MS)
    document.addEventListener('visibilitychange', recheck)
    window.addEventListener('focus', recheck)
    return () => {
      listeners.delete(setFx)
      clearInterval(timer)
      document.removeEventListener('visibilitychange', recheck)
      window.removeEventListener('focus', recheck)
    }
  }, [])

  const corporate = fx?.corporate_currency || pageCurrency || 'USD'
  const rates = fx?.rates || {}
  const options = useMemo(() => viewableCurrencies(corporate, rates), [corporate, rates])
  const view = options.includes(choice) ? choice : corporate
  // Picking a currency is the moment someone is about to read converted figures and the moment they
  // would notice a wrong one, so it re-validates unconditionally rather than trusting the TTL.
  const setView = v => {
    const next = v === corporate ? '' : v
    setChoice(next); writeSaved(next)
    loadRates({ force: true })
  }
  const convert = useMemo(() => amount => {
    const out = convertFromCorporate(amount, view, corporate, rates)
    return out == null ? Number(amount || 0) : out
  }, [view, corporate, rates])

  return {
    view, setView, corporate, rates, options, convert,
    asOf: fx?.as_of || null,
    live: !!fx?.live, stale: !!fx?.stale, sources: fx?.sources || [],
    loaded: fx != null, failed: !!fx?.failed,
    ttlMs: RATES_TTL_MS,
  }
}
