import test from 'node:test'
import assert from 'node:assert/strict'
import { isRequestedHiddenAdmin, visiblePickerUsers } from './users.js'

test('requested admin picker accounts are hidden without hiding unrelated users', () => {
  const users = [
    { id: 1, name: 'Santosh Admin', role: 'Admin' },
    { id: 2, name: 'Satish', role: 'Super Admin' },
    { id: 3, name: 'Satish Kumar', role: 'BD Lead' },
    { id: 4, name: 'Asha Admin', role: 'Admin' },
  ]

  assert.equal(isRequestedHiddenAdmin(users[0]), true)
  assert.equal(isRequestedHiddenAdmin(users[1]), true)
  assert.equal(isRequestedHiddenAdmin(users[2]), false)
  assert.deepEqual(visiblePickerUsers(users).map(u => u.id), [3, 4])
})

test('non-admin role with Santosh/Satish name is kept; missing fields do not throw', () => {
  assert.equal(isRequestedHiddenAdmin({ name: 'Santosh', role: 'BD Lead' }), false)
  assert.equal(isRequestedHiddenAdmin({ name: 'Santosh Admin', role: 'BD Lead' }), true)
  assert.equal(isRequestedHiddenAdmin({ name: 'Satish Admin' }), true)
  assert.equal(isRequestedHiddenAdmin(null), false)
  assert.equal(visiblePickerUsers(undefined).length, 0)
})
