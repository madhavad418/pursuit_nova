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
// Compact money ("$98.2K", "₹142.6M") back to a number.
const num = s => { const m = String(s).replace(/,/g, '').match(/([0-9.]+)\s*([KMB])?/); if (!m) return 0; const n = Number(m[1]); return n * ({ K: 1e3, M: 1e6, B: 1e9 }[m[2]] || 1) }

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

// ------------------------------------------------------------- Pipeline page
await page.goto(`${BASE}/#/pipeline`, { waitUntil: 'networkidle' })
await page.waitForSelector('.pipeline-column header b', { timeout: 20000 })
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
check('pipeline: picker present', true)

const api = await page.evaluate(() => fetch('/api/query/opportunities?page_size=100', { credentials: 'include' }).then(r => r.json()))
const rates = await page.evaluate(() => fetch('/api/currency/rates', { credentials: 'include' }).then(r => r.json()))
check('pipeline: banner matches API state', !!(await page.$('.warning-callout.stacked')) === (api.missing_fx_rates.length > 0), `missing=${JSON.stringify(api.missing_fx_rates)}`)

// Column headers must equal the server's converted per-stage totals, not a sum of raw card amounts.
const headers = await page.$$eval('.pipeline-column', cols => cols.map(c => ({ stage: c.querySelector('header strong').textContent.trim(), total: c.querySelector('header b').textContent.trim(), cards: [...c.querySelectorAll('.deal-card > b')].map(b => b.textContent.trim()) })))
let ok = true, detail = []
for (const h of headers) {
  const g = api.summary.by_status[h.stage]
  const expected = g ? g.value : 0
  const shown = num(h.total)
  const match = Math.abs(shown - expected) <= Math.max(1, expected * 0.011)
  if (!match) ok = false
  if (h.cards.length) detail.push(`${h.stage}: header ${h.total} | api $${Math.round(expected)} | cards ${h.cards.join(' + ')}`)
}
check('pipeline: stage totals are the converted whole-set totals', ok)
console.log('        ' + detail.join('\n        '))
const prefix = c => c.match(/^[^0-9]+/)?.[0].trim()
const mixed = headers.find(h => new Set(h.cards.map(prefix)).size > 1)
check('pipeline: a mixed-currency column is converted, not summed raw', !!mixed && num(mixed.total) < mixed.cards.reduce((s, c) => s + num(c), 0), mixed ? `${mixed.stage}: ${mixed.total} vs raw sum ${mixed.cards.join(' + ')}` : 'no mixed column in data')

// Switch view to INR: mini-KPIs and headers follow, cards (native) do not.
const cardsBefore = headers.flatMap(h => h.cards)
await page.selectOption('.currency-picker select', 'INR')
await page.waitForTimeout(500)
const kpi = await page.$eval('.mini-kpis strong', e => e.textContent.trim())
const headersAfter = await page.$$eval('.pipeline-column header b', e => e.map(x => x.textContent.trim()))
const cardsAfter = await page.$$eval('.deal-card > b', e => e.map(x => x.textContent.trim()))
check('pipeline: mini-KPI converts to ₹', kpi.startsWith('₹'), kpi)
check('pipeline: stage headers convert to ₹', headersAfter.filter(Boolean).every(h => h.startsWith('₹')), headersAfter.join(' | '))
check('pipeline: native card amounts untouched', JSON.stringify(cardsBefore) === JSON.stringify(cardsAfter))
await page.selectOption('.currency-picker select', 'USD')

// Deal editor exposes the currency.
await page.click('.deal-card')
await page.waitForSelector('.opp-drawer', { timeout: 20000 })
await page.click('.opp-drawer .inline-head button')
await page.waitForSelector('.edit-opportunity', { timeout: 10000 })
const labels = await page.$$eval('.edit-opportunity label', e => e.map(x => x.textContent.trim()))
check('pipeline: amount field is labelled with its currency', labels.some(l => /^Amount \([A-Z]{3}\)/.test(l)), labels.find(l => l.startsWith('Amount')))
check('pipeline: currency is editable in the drawer', labels.some(l => l.startsWith('Currency')))
const opts = await page.$$eval('.edit-opportunity select', sels => sels.map(s => [...s.options].map(o => o.value)))
check('pipeline: currency options are the rated currencies', opts.some(o => o.includes('INR') && o.includes('AED') && o.includes('USD')))
await page.keyboard.press('Escape')

// ------------------------------------------------------------- Lead360 create form default
const leadId = await page.evaluate(() => fetch('/api/leads', { credentials: 'include' }).then(r => r.json()).then(l => l[0].id))
await page.goto(`${BASE}/#/lead/${leadId}`, { waitUntil: 'networkidle' })
await page.waitForTimeout(800)
// The create form lives in a modal behind the "Create opportunity" / "New opportunity" button.
const opener = await page.$('text=Create opportunity') || await page.$('text=New opportunity')
if (opener) { await opener.click(); await page.waitForTimeout(400) }
const sel = await page.$$eval('select', sels => sels.map(s => ({ value: s.value, options: [...s.options].map(o => o.value) })).find(s => s.options.includes('INR') && s.options.includes('USD')))
check('lead360: currency select defaults to corporate and lists rated currencies', !!sel && sel.value === rates.corporate_currency && sel.options.includes('AED'), JSON.stringify(sel))

console.log('\nproblems after login:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
