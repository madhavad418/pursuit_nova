import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { convertFromCorporate, viewableCurrencies } from './currency'

const STORAGE_KEY = 'pn.viewCurrency'
function readSaved() { try { return localStorage.getItem(STORAGE_KEY) || '' } catch { return '' } }
function writeSaved(v) { try { v ? localStorage.setItem(STORAGE_KEY, v) : localStorage.removeItem(STORAGE_KEY) } catch {} }

/**
 * Loads the rate table once and exposes a display currency plus a converter bound to it.
 *
 * `pageCurrency` is the corporate currency the page's own API response reports. It is the
 * fallback while the rates are loading or if they fail to load, so a page never labels its
 * figures with a currency the server did not report (a hard-coded 'USD' used to do exactly that
 * for an INR-based deployment). The choice is a per-viewer convenience kept in localStorage; a
 * saved currency that has since lost its rate silently falls back to the corporate currency.
 */
export function useViewCurrency(pageCurrency) {
  const [fx, setFx] = useState(null)
  const [choice, setChoice] = useState(readSaved)
  useEffect(() => { api.get('/api/currency/rates').then(setFx).catch(() => setFx({ failed: true, rates: {} })) }, [])

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
