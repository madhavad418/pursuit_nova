import test from 'node:test'
import assert from 'node:assert/strict'
import { dateText, initials, pct } from './format.js'

test('display helpers are deterministic', () => {
  assert.equal(initials('BD Executive'), 'BE')
  assert.equal(pct(61.9), '62%')
  assert.match(dateText('2026-09-11'), /11/)
})
