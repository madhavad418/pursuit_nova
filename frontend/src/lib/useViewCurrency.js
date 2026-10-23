import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { convertFromCorporate, dayKey, ratesNeedRefetch, viewableCurrencies } from './currency'

const STORAGE_KEY = 'pn.viewCurrency'
function readSaved() { try { return localStorage.getItem(STORAGE_KEY) || '' } catch { return '' } }
function writeSaved(v) { try { v ? localStorage.setItem(STORAGE_KEY, v) : localStorage.removeItem(STORAGE_KEY) } catch {} }

// How often an open tab re-checks. The check is cheap and almost always a no-op: it only fetches
// once `ratesNeedRefetch` says the viewer's day has turned, which matches the server's daily pull.
const RECHECK_MS = 30 * 60 * 1000

// ---------------------------------------------------------------- one rate table for the whole app
// Up to three of these hooks mount at once (a page, its editor modal, a drawer), and they all want
// the same table. Holding it here means one request instead of three, a second page renders with
// rates already in hand rather than flashing the corporate currency, and — the point of the day
// stamp — a tab left open overnight re-fetches instead of converting at yesterday's rate forever.
let table = null        // the last payload, success or failure
let fetchedOn = ''      // the viewer's day it was fetched on; '' until the first success
let inflight = null     // a request already in the air, awaited by every caller rather than repeated
const listeners = new Set()

function publish(payload) { table = payload; listeners.forEach(fn => fn(payload)) }

function loadRates(force = false) {
  if (!force && table && !ratesNeedRefetch(fetchedOn)) return Promise.resolve(table)
  if (!inflight) {
    inflight = api.get('/api/currency/rates')
      .then(payload => { fetchedOn = dayKey(); publish(payload); return payload })
      // A failed fetch is published so the picker can say so, but deliberately not day-stamped, so
      // the next mount or re-check retries instead of leaving the page unconvertible all day.
      .catch(() => { const payload = { failed: true, rates: {} }; publish(payload); return payload })
      .finally(() => { inflight = null })
  }
  return inflight
}

/** Drop the shared table — used on sign-out so the next session fetches its own. */
export function resetViewCurrency() { table = null; fetchedOn = ''; inflight = null }

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
    // actually looks at the figures. Both go through the day-stamp guard, so returning to a tab
    // within the same day costs nothing and the first look on a new day gets that day's rates.
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
  const setView = v => { const next = v === corporate ? '' : v; setChoice(next); writeSaved(next) }
  const convert = useMemo(() => amount => {
    const out = convertFromCorporate(amount, view, corporate, rates)
    return out == null ? Number(amount || 0) : out
  }, [view, corporate, rates])

  return {
    view, setView, corporate, rates, options, convert,
    asOf: fx?.as_of || null,
    live: !!fx?.live, stale: !!fx?.stale, sources: fx?.sources || [],
    loaded: fx != null, failed: !!fx?.failed,
  }
}
