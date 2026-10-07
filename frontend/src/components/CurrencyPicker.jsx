import React from 'react'
import { Select } from './UI'
import { dateText } from '../lib/format'

/**
 * "View in" selector for the money pages. Takes the object returned by `useViewCurrency()`.
 * The caption names where the rates came from and how old they are — provenance and freshness
 * are separate facts: provider rates can be a month old, hand-entered ones can be today's.
 */
export function CurrencyPicker({ fx }) {
  const { view, setView, options, corporate, asOf, live, stale, sources, loaded, failed } = fx
  if (!loaded) return null
  if (failed) return <span className="currency-picker is-stale"><small>Exchange rates unavailable — figures shown in {corporate}</small></span>
  if (options.length < 2) return null
  const origin = live ? 'Provider rates' : sources.some(s => s === 'MANUAL' || s === 'TREASURY') ? 'Hand-entered rates' : 'Placeholder rates'
  const caption = `${origin} · ${dateText(asOf)}${stale ? ' · not refreshed' : ''}`
  const title = view === corporate ? 'Figures are in the corporate reporting currency' : `Converted from ${corporate} at the rate of ${dateText(asOf)}`
  return <label className={stale ? 'currency-picker is-stale' : 'currency-picker'} title={title}>
    <span>View in</span>
    <Select value={view} onChange={e => setView(e.target.value)} aria-label="Display currency">
      {options.map(c => <option key={c} value={c}>{c}{c === corporate ? ' (corporate)' : ''}</option>)}
    </Select>
    <small>{caption}</small>
  </label>
}
