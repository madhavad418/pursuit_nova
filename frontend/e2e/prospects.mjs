// Every prospect shows a default currency (symbol + code) on the Prospects table, the create form
// offers the rated currencies with "Default for region", the edit form shows and saves the currency,
// and a new opportunity on a prospect inherits it.
import { chromium } from 'playwright-core'

const CHROME = process.env.CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = process.env.BASE || 'http://localhost:5173'
const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })
const problems = []
let authed = false
page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))
page.on('response', r => { if (authed && r.status() >= 400) problems.push(`${r.status()} ${r.url().replace(BASE, '')}`) })
const check = (name, ok, detail = '') => console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`)
const SIGN = { USD: '$', INR: '₹', GBP: '£', EUR: '€', AED: 'AED' }

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

// Same odd path the user is on
await page.goto(`${BASE}/admin/users#/prospects`, { waitUntil: 'networkidle' })
await page.waitForSelector('table tbody tr', { timeout: 20000 })
const headers = await page.$$eval('table thead th', th => th.map(x => x.textContent.trim()))
const idx = headers.findIndex(h => h.startsWith('Currency'))
check('prospects: Currency column is on by default', idx >= 0, headers.join(' | '))
const cells = await page.$$eval('table tbody tr', (trs, i) => trs.map(tr => tr.querySelectorAll('td')[i]?.textContent.trim().replace(/\s+/g, ' ')), idx)
check('prospects: every cell is "<symbol> <code>"', cells.length > 0 && cells.every(c => /^.+ [A-Z]{3}$/.test(c)), [...new Set(cells)].join(', '))
check('prospects: symbols match their codes', cells.every(c => { const [sign, code] = c.split(' '); return SIGN[code] ? sign === SIGN[code] : true }))
const api = await page.evaluate(() => fetch('/api/leads', { credentials: 'include' }).then(r => r.json()))
check('prospects: table matches the API', api.every(l => /^[A-Z]{3}$/.test(l.currency || '')), `${api.length} leads`)
const regionMismatch = api.filter(l => (l.region || '').toUpperCase() === 'INDIA' && l.currency !== 'INR')
check('prospects: Indian prospects default to INR', regionMismatch.length === 0, regionMismatch.map(l => l.company_name).join(','))

// Create form: field present, defaults to "region default", lists rated currencies
const opener = await page.$('text=New prospect') || await page.$('text=Add prospect')
if (opener) {
  await opener.click(); await page.waitForTimeout(500)
  const sel = await page.$$eval('select', sels => sels.map(s => ({ value: s.value, options: [...s.options].map(o => o.textContent.trim()) })).find(s => s.options.some(o => o.startsWith('Default for region'))))
  check('prospects: create form has a Currency field defaulting to the region', !!sel && sel.value === '' && sel.options.some(o => o.includes('(corporate)')), JSON.stringify(sel))
  await page.keyboard.press('Escape'); await page.waitForTimeout(300)
} else check('prospects: create form reachable', false, 'no opener button found')

// Edit form: shows the row's currency, saves a change, and blank restores the region default.
// Fresh load first so nothing from the create modal is still mounted.
await page.goto(`${BASE}/#/prospects`, { waitUntil: 'networkidle' })
await page.waitForSelector('table tbody tr', { timeout: 20000 })
const first = await page.$eval('table tbody tr', (tr, i) => ({ name: tr.querySelector('td strong')?.textContent.trim(), cell: tr.querySelectorAll('td')[i]?.textContent.trim().replace(/\s+/g, ' ') }), idx)
const lead = api.find(l => l.company_name === first.name)
await page.click(`table tbody tr:first-child button[aria-label="Edit ${first.name}"]`)
await page.waitForSelector('text=Edit prospect', { timeout: 20000 })
await page.waitForFunction(() => [...document.querySelectorAll('select')].some(s => [...s.options].some(o => o.textContent.includes('Default for region'))), null, { timeout: 20000 })
const editSel = await page.$$eval('select', sels => { const s = sels.find(s => [...s.options].some(o => o.textContent.includes('Default for region'))); return s ? { value: s.value, options: [...s.options].map(o => o.textContent.trim()) } : null })
check('prospects: edit form shows a Currency field prefilled with the prospect\'s currency', !!editSel && editSel.value === lead.currency, `${JSON.stringify(editSel?.value)} vs API ${lead.currency}`)
check('prospects: edit options carry symbols', !!editSel && editSel.options.some(o => /^[₹$£€] [A-Z]{3}/.test(o)), (editSel?.options || []).slice(0, 4).join(' | '))

const target = lead.currency === 'GBP' ? 'EUR' : 'GBP'
await page.evaluate(() => { const s = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.textContent.includes('Default for region'))); s.scrollIntoView() })
const handle = await page.evaluateHandle(() => [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.textContent.includes('Default for region'))))
await handle.asElement().selectOption(target)
const [put] = await Promise.all([
  page.waitForResponse(r => r.url().includes(`/api/leads/${lead.id}`) && r.request().method() === 'PUT', { timeout: 20000 }),
  page.click('button:has-text("Save changes")'),
])
check('prospects: saving the edit PUTs the currency', put.status() === 200, `HTTP ${put.status()}`)
await page.waitForTimeout(900)
const after = await page.$eval('table tbody tr', (tr, i) => tr.querySelectorAll('td')[i]?.textContent.trim().replace(/\s+/g, ' '), idx)
const apiAfter = await page.evaluate(id => fetch('/api/leads', { credentials: 'include' }).then(r => r.json()).then(l => l.find(x => x.id === id).currency), lead.id)
check('prospects: table and API reflect the new currency', after === `${SIGN[target]} ${target}` && apiAfter === target, `${first.cell} -> ${after} (API ${apiAfter})`)

// Blank restores the region default
await page.click(`table tbody tr:first-child button[aria-label="Edit ${first.name}"]`)
await page.waitForFunction(() => [...document.querySelectorAll('select')].some(s => [...s.options].some(o => o.textContent.includes('Default for region'))), null, { timeout: 20000 })
const h2 = await page.evaluateHandle(() => [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.textContent.includes('Default for region'))))
await h2.asElement().selectOption('')
await Promise.all([page.waitForResponse(r => r.url().includes(`/api/leads/${lead.id}`) && r.request().method() === 'PUT', { timeout: 20000 }), page.click('button:has-text("Save changes")')])
await page.waitForTimeout(900)
const restored = await page.evaluate(id => fetch('/api/leads', { credentials: 'include' }).then(r => r.json()).then(l => l.find(x => x.id === id).currency), lead.id)
check('prospects: "Default for region" restores the original', restored === lead.currency, `${restored} (was ${lead.currency})`)

console.log('\nproblems after login:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
