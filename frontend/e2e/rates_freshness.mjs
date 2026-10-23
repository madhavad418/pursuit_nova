// Rate freshness, end to end: the "view in" caption must name today's provider date, and an open tab
// must re-validate its rate table rather than converting at whatever it first loaded.
//
// Two reported bugs live here. "Provider rates · 16 Oct 2026 · not refreshed" still on screen a week
// later, because the backend refreshed only at boot. And GBP figures ~5 % out on the Pipeline page
// after EXCHANGERATE_API_KEY was first set, because the open tab kept dividing by the placeholder
// rate of 1.27 that the deploy had already replaced with 1.33923.
//
// Run it against a backend whose EXCHANGERATE_API_KEY is set, or the caption reads "Placeholder
// rates" and the first check fails for that reason instead.
import { chromium } from 'playwright-core'

const CHROME = process.env.CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = process.env.BASE || 'http://localhost:5173'
const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })

const problems = []
let authed = false
const rateCalls = []
page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))
page.on('response', r => { if (authed && r.status() >= 400) problems.push(`${r.status()} ${r.url().replace(BASE, '')}`) })
page.on('request', r => { if (r.url().includes('/api/currency/rates')) rateCalls.push(r.url()) })
let fails = 0
const check = (name, ok, detail = '') => { if (!ok) fails++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`) }
const txt = async sel => (await page.$(sel)) ? (await page.$eval(sel, e => e.textContent.trim().replace(/\s+/g, ' '))) : null

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
authed = true
await page.waitForLoadState('networkidle')

// ------------------------------------------------------------------------------- the symptom
const caption = await txt('.currency-picker small')
const today = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
check('caption shows provider rates dated today', caption === `Provider rates · ${today}`, caption)
check('caption no longer says "not refreshed"', !/not refreshed/.test(caption || ''), caption)
check('picker is not flagged stale', !(await page.$('.currency-picker.is-stale')))

// ------------------------------------------- one shared table, not one fetch per mounted hook
check('one rates request for the whole page', rateCalls.length === 1, `${rateCalls.length} call(s)`)

// --------------------------------------------------------------- conversion through the picker
// Picking a currency re-validates unconditionally: it is the moment someone is about to read
// converted figures, and the moment a superseded rate would be noticed.
const before = await txt('.currency-total')
await page.selectOption('.currency-picker select', 'GBP')
await page.waitForTimeout(900)
const after = await txt('.currency-total')
check('switching to GBP re-expresses the figures', !!before && !!after && before !== after, `${before} -> ${after}`)
check('choosing a currency re-validates the table', rateCalls.length === 2, `${rateCalls.length} call(s)`)

await page.goto(`${BASE}/#pipeline`, { waitUntil: 'networkidle' })
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
await page.waitForTimeout(400)
check('a second money page shows the same fresh caption', (await txt('.currency-picker small')) === `Provider rates · ${today}`)
check('a second money page reuses the table while it is fresh', rateCalls.length === 2, `${rateCalls.length} call(s)`)

// ------------------------------------- the open-tab case: a rate that changes under a live tab
// This is the one that bit in production. The rates on the server changed — an admin refresh, or
// the deploy that first swapped the seeded placeholders for live rates — and the open tab carried
// on dividing by the old one. Push the page's clock past the TTL, then raise the focus event the
// hook re-checks on, and the table must be re-fetched.
await page.evaluate(() => { const real = Date.now; Date.now = () => real() + 10 * 60 * 1000 })
await page.evaluate(() => window.dispatchEvent(new Event('focus')))
await page.waitForTimeout(900)
check('a table past its TTL is re-validated on focus', rateCalls.length === 3, `${rateCalls.length} call(s)`)

check('no page errors or failed requests', problems.length === 0, problems.join(' | '))
await browser.close()
console.log(fails ? `\n${fails} FAILED` : '\nall checks passed')
process.exit(fails ? 1 : 0)
