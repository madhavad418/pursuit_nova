import { chromium } from 'playwright-core'

const CHROME = process.env.CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = process.env.BASE || 'http://localhost:5173'
const KEY = process.env.EXCHANGERATE_API_KEY || ''  // set it to also assert the key never reaches the browser

const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })

const problems = []
let authed = false
page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))
page.on('response', r => { if (authed && r.status() >= 400) problems.push(`${r.status()} ${r.url().replace(BASE, '')}`) })

const check = (name, ok, detail = '') => console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`)

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

// ------------------------------------------------------------------ Admin: the rates panel
await page.goto(`${BASE}/#/admin`, { waitUntil: 'networkidle' })
await page.waitForSelector('.fx-rates tbody tr', { timeout: 20000 })  // the panel paints before its data arrives

const rows = await page.$$eval('.fx-rates tbody tr', trs =>
  trs.map(tr => [...tr.querySelectorAll('td')].map(td => td.textContent.trim())))
check('admin: rates table renders', rows.length > 0, `${rows.length} rows`)
console.log('        ' + rows.map(r => r.join(' | ')).join('\n        '))

check('admin: rates show live provenance', rows.every(r => r[0] === 'USD' ? r.includes('CORPORATE-BASE') : r.includes('exchangerate-api.com')), 'base row is CORPORATE-BASE, every other row names the provider')
check('admin: subtitle names the provider',
  (await page.$eval('.fx-rates .inline-head p', e => e.textContent)).includes('exchangerate-api.com'))
check('admin: no placeholder warning left', !(await page.$('.fx-rates .warning-callout')))

// The refresh button must actually call the endpoint and report back.
const btn = await page.$('.fx-rates button')
check('admin: refresh button present', !!btn, await btn?.textContent())
const [resp] = await Promise.all([
  page.waitForResponse(r => r.url().includes('/api/admin/currency/refresh'), { timeout: 20000 }),
  btn.click(),
])
check('admin: refresh hits the API', resp.status() === 200, `HTTP ${resp.status()}`)
const body = await resp.text()
if (KEY) check('admin: API key never reaches the browser', !body.includes(KEY))
await page.waitForTimeout(1200)
const toast = await page.$eval('body', b => b.textContent.match(/\d+ rates? updated from [^·\n]+/)?.[0] || '')
check('admin: result is reported to the user', !!toast, toast)

// ------------------------------------------------------- Dashboard reflects the live rates
await page.goto(`${BASE}/#/dashboard`, { waitUntil: 'networkidle' })
await page.waitForSelector('.region-currency', { timeout: 20000 })
check('dashboard: AED now converts, so no FX warning', !(await page.$('.warning-callout.stacked')))
check('dashboard: no unrated legs left', !(await page.$('.region-leg.is-unrated')))
const footers = await page.$$eval('.region-card footer', e => e.map(x => x.textContent.trim()))
check('dashboard: every region has a corporate total', footers.every(f => f.startsWith('≈')))
console.log('        ' + footers.join('\n        '))

console.log('\nproblems after login:', problems.length ? problems : 'none')
await page.screenshot({ path: 'admin-fx.png' })
await browser.close()
process.exit(problems.length ? 1 : 0)
