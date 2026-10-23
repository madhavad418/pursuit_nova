// Rate freshness, end to end: the "view in" caption must name today's provider date, and a tab left
// open must pick up a new day's rates rather than converting at the day it was opened on.
//
// This is the sweep for the reported bug — "Provider rates · 16 Oct 2026 · not refreshed" still on
// screen a week later, because the backend refreshed only at boot and the hook fetched only on
// mount. Run it against a backend whose EXCHANGERATE_API_KEY is set, or the caption reads
// "Placeholder rates" and the first check fails for that reason instead.
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
const before = await txt('.currency-total')
await page.selectOption('.currency-picker select', 'GBP')
await page.waitForTimeout(600)
const after = await txt('.currency-total')
check('switching to GBP re-expresses the figures', !!before && !!after && before !== after, `${before} -> ${after}`)
check('GBP view issues no extra rates fetch', rateCalls.length === 1, `${rateCalls.length} call(s)`)

await page.goto(`${BASE}/#pipeline`, { waitUntil: 'networkidle' })
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
check('a second money page shows the same fresh caption', (await txt('.currency-picker small')) === `Provider rates · ${today}`)
check('a second money page reuses the table', rateCalls.length === 1, `${rateCalls.length} call(s)`)

// ----------------------------------------------------- the open-tab case: the day turns over
// Move the page's own idea of the date, then raise the focus event the hook re-checks on.
await page.evaluate(() => { Date.prototype.getDate = function () { return 1 } })
await page.evaluate(() => window.dispatchEvent(new Event('focus')))
await page.waitForTimeout(800)
check('a turned-over day triggers exactly one refetch', rateCalls.length === 2, `${rateCalls.length} call(s)`)

check('no page errors or failed requests', problems.length === 0, problems.join(' | '))
await browser.close()
console.log(fails ? `\n${fails} FAILED` : '\nall checks passed')
process.exit(fails ? 1 : 0)
