import test from 'node:test'
import assert from 'node:assert/strict'
import { convertFromCorporate, viewableCurrencies } from './currency.js'

// Live rates on 2026-10-07: one unit of each in USD.
const RATES = { USD: 1, INR: 0.01036624, GBP: 1.32625995, EUR: 1.12523911, AED: 0.27229408 }

test('viewing in the corporate currency is a no-op', () => {
  assert.equal(convertFromCorporate(1_047_747, 'USD', 'USD', RATES), 1_047_747)
  assert.equal(convertFromCorporate(1_047_747, '', 'USD', RATES), 1_047_747)
})

test('USD -> INR divides by the per-unit rate', () => {
  // $51,830 is what ₹5,000,000 converts to; viewing it back in INR must round-trip.
  const usd = 5_000_000 * RATES.INR
  assert.ok(Math.abs(convertFromCorporate(usd, 'INR', 'USD', RATES) - 5_000_000) < 1e-6)
})

test('a currency worth more than the corporate one shrinks the figure', () => {
  const gbp = convertFromCorporate(1_000, 'GBP', 'USD', RATES)
  assert.ok(gbp < 1_000 && gbp > 700, `expected ~754, got ${gbp}`)
})

test('a missing or broken rate yields null rather than a silent zero', () => {
  assert.equal(convertFromCorporate(1_000, 'KWD', 'USD', RATES), null)
  assert.equal(convertFromCorporate(1_000, 'INR', 'USD', { INR: 0 }), null)
  assert.equal(convertFromCorporate(1_000, 'INR', 'USD', { INR: 'oops' }), null)
  assert.equal(convertFromCorporate(1_000, 'INR', 'USD', undefined), null)
})

test('nullish amounts convert as zero, not NaN', () => {
  assert.equal(convertFromCorporate(null, 'INR', 'USD', RATES), 0)
  assert.equal(convertFromCorporate(undefined, 'USD', 'USD', RATES), 0)
})

test('the picker lists the corporate currency first, then rated ones alphabetically', () => {
  assert.deepEqual(viewableCurrencies('USD', RATES), ['USD', 'AED', 'EUR', 'GBP', 'INR'])
  assert.deepEqual(viewableCurrencies('USD', { USD: 1, XXX: 0, INR: 0.01 }), ['USD', 'INR'], 'a zero rate is not offered')
  assert.deepEqual(viewableCurrencies('USD', {}), ['USD'])
})
