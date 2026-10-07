import test from 'node:test'
import assert from 'node:assert/strict'
import { currencySymbol, dateText, initials, money, pct } from './format.js'

test('display helpers are deterministic', () => {
  assert.equal(initials('BD Executive'), 'BE')
  assert.equal(pct(61.9), '62%')
  assert.match(dateText('2026-09-11'), /11/)
})


test('money normalises legacy currency spellings before formatting', () => {
  assert.equal(money(1500, 'INR ', false), money(1500, 'INR', false))
  assert.equal(money(1500, 'inr', false), '₹1,500')
  assert.ok(money(1500, 'INR').startsWith('₹'))
})

test('money falls back to a plain label for a non-ISO code, honouring compact', () => {
  assert.equal(money(5_000_000, 'RS', false), 'RS 5,000,000')
  assert.equal(money(5_000_000, 'RS'), 'RS 5M')
})

test('money treats null as a masked field, not a zero', () => {
  assert.equal(money(null, 'USD'), '—')
  assert.equal(money(undefined, 'USD', false), '$0')
  assert.equal(money(0, 'USD', false), '$0')
})

test('money never prints "null" or "undefined" as a currency', () => {
  assert.equal(money(1500, null, false), '$1,500')
  assert.equal(money(1500, '', false), '$1,500')
})


test('currencySymbol gives the sign for a code, or the code when there is none', () => {
  assert.equal(currencySymbol('INR'), '₹')
  assert.equal(currencySymbol('USD'), '$')
  assert.equal(currencySymbol('GBP'), '£')
  assert.equal(currencySymbol('EUR'), '€')
  assert.equal(currencySymbol('inr '), '₹', 'normalised like everything else')
  assert.equal(currencySymbol('AED'), 'AED', 'no narrow symbol -> the code itself')
  assert.equal(currencySymbol('ZZZ'), 'ZZZ')
  assert.equal(currencySymbol(''), '')
})
