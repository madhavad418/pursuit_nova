// Runs `remove(id)` for each id one at a time; a failure on one item never stops the rest.
export async function deleteMany(ids, remove) {
  const failed = []
  for (const id of ids) {
    try { await remove(id) } catch (e) { failed.push({ id, message: e?.message || String(e) }) }
  }
  return { deleted: ids.length - failed.length, failed }
}

export function bulkResultMessage(noun, { deleted, failed }) {
  const plural = n => `${n} ${noun}${n === 1 ? '' : 's'}`
  if (!failed.length) return { message: `${plural(deleted)} deleted` }
  return { type: 'error', message: `${deleted ? `${plural(deleted)} deleted, ` : ''}${failed.length} failed: ${failed[0].message}` }
}
