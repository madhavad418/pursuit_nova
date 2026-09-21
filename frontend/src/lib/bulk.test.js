import test from 'node:test'
import assert from 'node:assert/strict'
import { deleteMany, bulkResultMessage } from './bulk.js'

test('deleteMany continues past failures and reports them', async () => {
  const seen = []
  const res = await deleteMany([1, 2, 3], async id => { seen.push(id); if (id === 2) throw new Error('nope') })
  assert.deepEqual(seen, [1, 2, 3])
  assert.equal(res.deleted, 2)
  assert.deepEqual(res.failed, [{ id: 2, message: 'nope' }])
})

test('bulkResultMessage', () => {
  assert.deepEqual(bulkResultMessage('action', { deleted: 1, failed: [] }), { message: '1 action deleted' })
  assert.deepEqual(bulkResultMessage('prospect', { deleted: 2, failed: [] }), { message: '2 prospects deleted' })
  assert.equal(bulkResultMessage('prospect', { deleted: 1, failed: [{ message: 'x' }] }).type, 'error')
})
