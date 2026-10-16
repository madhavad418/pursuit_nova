import test from 'node:test'
import assert from 'node:assert/strict'
import { convertBetween, convertFromCorporate, viewableCurrencies } from './currency.js'

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

// --- convertBetween: a single record's native amount, shown in the currency the page is viewed in

test('a record already in the view currency is untouched', () => {
  assert.equal(convertBetween(194, 'GBP', 'GBP', 'USD', RATES), 194)
  assert.equal(convertBetween(500, 'USD', 'USD', 'USD', RATES), 500)
})

test('a native amount reaches the view currency via the corporate one', () => {
  // The reported case: a 100,000 INR deal on a board being viewed in GBP.
  const gbp = convertBetween(100_000, 'INR', 'GBP', 'USD', RATES)
  const expected = 100_000 * RATES.INR / RATES.GBP
  assert.ok(Math.abs(gbp - expected) < 1e-9)
  assert.ok(gbp > 700 && gbp < 800, `expected ~781, got ${gbp}`)
})

test('corporate-held amounts still convert, without double-applying a rate', () => {
  assert.equal(convertBetween(1_000, 'USD', 'USD', 'USD', RATES), 1_000)
  const inr = convertBetween(1_000, 'USD', 'INR', 'USD', RATES)
  assert.ok(Math.abs(inr - 1_000 / RATES.INR) < 1e-6)
})

test('converting a record round-trips back to its own currency', () => {
  const gbp = convertBetween(100_000, 'INR', 'GBP', 'USD', RATES)
  const back = convertBetween(gbp, 'GBP', 'INR', 'USD', RATES)
  assert.ok(Math.abs(back - 100_000) < 1e-6, `expected 100000, got ${back}`)
})

test('a sloppily stored code still converts', () => {
  for (const code of [' inr ', 'INR ', 'inr', 'Inr']) {
    assert.ok(Math.abs(convertBetween(100_000, code, 'GBP', 'USD', RATES) - convertBetween(100_000, 'INR', 'GBP', 'USD', RATES)) < 1e-12, code)
  }
})

test('a blank code is treated as the corporate currency, matching the server', () => {
  assert.equal(convertBetween(1_000, '', 'USD', 'USD', RATES), 1_000)
  assert.equal(convertBetween(1_000, null, 'USD', 'USD', RATES), 1_000)
})

test('an unrated currency on either leg yields null, never a converted-looking zero', () => {
  assert.equal(convertBetween(75_000, 'KWD', 'GBP', 'USD', RATES), null, 'source has no rate')
  assert.equal(convertBetween(75_000, 'INR', 'KWD', 'USD', RATES), null, 'target has no rate')
  assert.equal(convertBetween(75_000, 'INR', 'GBP', 'USD', { INR: 0, GBP: 1.3 }), null)
})

test('nullish amounts convert as zero, not NaN', () => {
  assert.equal(convertBetween(null, 'INR', 'GBP', 'USD', RATES), 0)
  assert.equal(convertBetween(undefined, 'GBP', 'GBP', 'USD', RATES), 0)
})
