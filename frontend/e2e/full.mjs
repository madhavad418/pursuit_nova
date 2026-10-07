import { chromium } from 'playwright-core'

const CHROME = process.env.CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = process.env.BASE || 'http://localhost:5173'

const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })

const problems = []
page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))
let authed = false
page.on('response', r => { if (authed && r.status() >= 400) problems.push(`${r.status()} ${r.url().replace(BASE, '')}`) })

const txt = async sel => (await page.$(sel)) ? (await page.$eval(sel, e => e.textContent.trim().replace(/\s+/g, ' '))) : null
const check = (name, ok, detail = '') => console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`)

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

// ---------------------------------------------------------------- Dashboard
await page.waitForSelector('.region-currency', { timeout: 20000 })
const cards = await page.$$eval('.region-card', els => els.length)
check('dashboard: region panel renders', cards > 0, `${cards} region cards`)
// The warning must appear exactly when the API reports missing rates - no more, no less.
const fx = await page.evaluate(() => fetch('/api/dashboard/analytics', { credentials: 'include' }).then(r => r.json()).then(d => d.fx))
const missing = fx.missing_rates || []
check('dashboard: FX warning matches API state', !!(await page.$('.warning-callout.stacked')) === (missing.length > 0),
  missing.length ? `warned about ${missing.join(', ')}` : 'no missing rates, no warning')
check('dashboard: unrated legs match API state',
  (await page.$$('.region-leg.is-unrated')).length > 0 === (missing.length > 0))
check('dashboard: native currency symbols differ',
  new Set(await page.$$eval('.region-leg .leg-figures b', e => e.map(x => x.textContent.trim()[0]))).size > 1)

// ---------------------------------------------------------------- Leadership (incl. last change)
await page.goto(`${BASE}/#/leadership`, { waitUntil: 'networkidle' })
await page.waitForSelector('.donut-wrap', { timeout: 20000 })
check('leadership: page renders', !!(await page.$('.donut-wrap')))
check('leadership: FX warning matches API state',
  !!(await page.$('.warning-callout.stacked')) === (missing.length > 0))

// The donut->table filter shipped last session must still work.
const before = await page.$$eval('.table-panel tbody tr', r => r.length)
await page.click('.chart-legend > span')
await page.waitForTimeout(500)
const after = await page.$$eval('.table-panel tbody tr', r => r.length)
const chip = await txt('.filter-chip')
check('leadership: donut legend still filters the tables', after !== before && !!chip,
  `${before} -> ${after} rows, chip "${chip}"`)
await page.click('.filter-chip')
await page.waitForTimeout(400)
check('leadership: filter clears', (await page.$$eval('.table-panel tbody tr', r => r.length)) === before)

// ---------------------------------------------------------------- other money pages
for (const [name, hash, sel] of [['forecast', '#/forecast', '.panel'], ['pipeline', '#/pipeline', '.mini-kpis'], ['kpi', '#/kpi', '.panel']]) {
  await page.goto(`${BASE}/${hash}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(900)
  check(`${name}: page renders`, !!(await page.$(sel)))
}

console.log('\nproblems after login:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
