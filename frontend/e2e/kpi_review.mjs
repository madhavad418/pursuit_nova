// KPI Tracker → Review team: picking a month alone shows nobody's data; picking a person loads
// theirs; and the person's assigned regions each show their currency and live conversion —
// two regions, two conversions.
import { chromium } from 'playwright-core'

const CHROME = process.env.CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = process.env.BASE || 'http://localhost:5173'
const API = process.env.API || 'http://localhost:8000'
const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })
const problems = []
let authed = false
page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))
page.on('response', r => { if (authed && r.status() >= 400) problems.push(`${r.status()} ${r.url().replace(BASE, '')}`) })
const check = (name, ok, detail = '') => console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`)
const txt = async sel => (await page.$(sel)) ? (await page.$eval(sel, e => e.textContent.trim().replace(/\s+/g, ' '))) : null

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

// A reviewable person; give them two regions for the duration of the check, then restore.
const people = await page.evaluate(() => fetch('/api/kpi/users-with-category', { credentials: 'include' }).then(r => r.json()))
const person = people[0]
if (!person) { console.log('FAIL  no reviewable person in data'); process.exit(1) }
const original = await page.evaluate(id => fetch('/api/users', { credentials: 'include' }).then(r => r.json()).then(l => l.find(u => u.id === id)?.region ?? ''), person.id)
const setRegion = region => page.evaluate(async ([id, region]) => {
  const csrf = await fetch('/api/auth/csrf', { credentials: 'include' }).then(r => r.json()).then(d => d.csrf_token)
  return fetch(`/api/users/${id}`, { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ data: { region } }) }).then(r => r.status)
}, [person.id, region])
check('setup: person given two regions', (await setRegion('India, UK')) === 200)

try {
  await page.goto(`${BASE}/#/kpi`, { waitUntil: 'networkidle' })
  await page.click('text=Review team')
  await page.waitForSelector('input.month-picker', { timeout: 20000 })
  await page.fill('input.month-picker', '2026-09')
  await page.waitForTimeout(700)

  // 1. Month alone: no data, a prompt, and the person dropdown has no "all" default.
  const sel = await page.$eval('select[aria-label="Person to review"]', s => ({ value: s.value, first: s.options[0].textContent.trim(), last: s.options[s.options.length - 1].textContent.trim() }))
  check('review: person dropdown defaults to "Select a person…"', sel.value === '' && sel.first.startsWith('Select a person'), JSON.stringify(sel))
  check('review: no submissions shown for the month alone', !(await page.$('.kpi-summary-card')) && !(await page.$('.kpi-tbl tbody tr')), await txt('.empty-state, [class*="empty"]') || '')
  check('review: prompt asks for a person', ((await page.$eval('body', e => e.innerText)) || '').includes('Choose a person to review'))
  const reviewCalls = []
  page.on('request', r => { if (r.url().includes('/api/kpi/review?')) reviewCalls.push(r.url()) })
  await page.fill('input.month-picker', '2026-08'); await page.waitForTimeout(500)
  await page.fill('input.month-picker', '2026-09'); await page.waitForTimeout(500)
  check('review: changing the month fetches nothing without a person', reviewCalls.length === 0, `${reviewCalls.length} calls`)

  // 2. Choose the person: their data loads, and both regions show a conversion.
  await page.selectOption('select[aria-label="Person to review"]', String(person.id))
  await page.waitForSelector('.kpi-regions', { timeout: 20000 })
  await page.waitForTimeout(800)
  const rows = await page.$$eval('.kpi-tbl tbody tr', r => r.length)
  check('review: the chosen person\'s submission loads', rows > 0 || !!(await page.$('.kpi-summary-card')), `${rows} rows`)
  check('review: only /api/kpi/review calls carry user_id', reviewCalls.length > 0 && reviewCalls.every(u => u.includes(`user_id=${person.id}`)), reviewCalls.map(u => u.replace(BASE, '')).join(' | '))
  const regions = await page.$$eval('.kpi-regions li', li => li.map(x => ({ region: x.querySelector('em').textContent.trim(), code: x.querySelector('b').textContent.trim(), rate: x.querySelector('small').textContent.trim() })))
  check('review: two regions -> two currency conversions', regions.length === 2 && regions.map(r => r.code).join(',') === '₹ INR,£ GBP', JSON.stringify(regions.map(r => r.code)))
  check('review: each conversion shows both directions with live rates', regions.every(r => /1 [A-Z]{3} = \$[0-9.]+ · 1 USD = [^0-9]*[0-9,.]+/.test(r.rate)), regions.map(r => r.rate).join(' | '))
  const rates = await page.evaluate(() => fetch('/api/currency/rates', { credentials: 'include' }).then(r => r.json()))
  const inr = Number(regions[0].rate.match(/1 INR = \$([0-9.]+)/)?.[1])
  check('review: INR conversion matches the rate table', Math.abs(inr - rates.rates.INR) < 1e-4, `${inr} vs ${rates.rates.INR}`)
  check('review: rate date shown', ((await txt('.kpi-regions-asof')) || '').startsWith('Rates as of'), await txt('.kpi-regions-asof'))

  // 3. "All people" is an explicit opt-in, never the default.
  await page.selectOption('select[aria-label="Person to review"]', 'all'); await page.waitForTimeout(700)
  check('review: "All people" opt-in loads everyone', reviewCalls.some(u => !u.includes('user_id=')), '')
} finally {
  check('teardown: regions restored', (await setRegion(original)) === 200, JSON.stringify(original))
}

console.log('\nproblems after login:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
