// KPI Tracker → Review team: picking a month alone shows nobody's data; picking a person loads
// theirs; "All people" is an explicit opt-in.
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
const txt = async sel => (await page.$(sel)) ? (await page.$eval(sel, e => e.textContent.trim().replace(/\s+/g, ' '))) : null

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

// Any reviewable person.
const people = await page.evaluate(() => fetch('/api/kpi/users-with-category', { credentials: 'include' }).then(r => r.json()))
const person = people[0]
if (!person) { console.log('FAIL  no reviewable person in data'); process.exit(1) }
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

// 2. Choose the person: only their data loads.
await page.selectOption('select[aria-label="Person to review"]', String(person.id))
await page.waitForTimeout(1000)
const rows = await page.$$eval('.kpi-tbl tbody tr', r => r.length)
check('review: the chosen person\'s submission loads', rows > 0 || !!(await page.$('.kpi-summary-card')), `${rows} rows`)
check('review: only /api/kpi/review calls carry user_id', reviewCalls.length > 0 && reviewCalls.every(u => u.includes(`user_id=${person.id}`)), reviewCalls.map(u => u.replace(BASE, '')).join(' | '))
// 3. "All people" is an explicit opt-in, never the default.
await page.selectOption('select[aria-label="Person to review"]', 'all'); await page.waitForTimeout(700)
check('review: "All people" opt-in loads everyone', reviewCalls.some(u => !u.includes('user_id=')), '')

console.log('\nproblems after login:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
