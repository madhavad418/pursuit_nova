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
const num = s => Number(String(s).replace(/[^0-9.]/g, ''))

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

// --------------------------------------------------------------- Dashboard: picker + conversion
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
const options = await page.$$eval('.currency-picker select option', o => o.map(x => x.value))
check('dashboard: picker lists corporate first then rated currencies', options[0] === 'USD' && options.includes('INR') && options.includes('AED'), options.join(','))
check('dashboard: caption names provider rates and their date', /^Provider rates · \d{2} \w{3} \d{4}$/.test(await txt('.currency-picker small') || ''), await txt('.currency-picker small'))

const usdPipeline = await txt('.kpi-grid .kpi-card:first-child strong')
const usdFooter = await txt('.region-card:first-child footer')
const nativeBefore = await page.$$eval('.region-leg .leg-figures b', e => e.map(x => x.textContent.trim()))

await page.selectOption('.currency-picker select', 'INR')
await page.waitForTimeout(300)
const inrPipeline = await txt('.kpi-grid .kpi-card:first-child strong')
const inrFooter = await txt('.region-card:first-child footer')
const nativeAfter = await page.$$eval('.region-leg .leg-figures b', e => e.map(x => x.textContent.trim()))

check('dashboard: KPI re-renders in ₹', inrPipeline.startsWith('₹') && inrPipeline !== usdPipeline, `${usdPipeline} -> ${inrPipeline}`)
check('dashboard: region footer converts to view currency', inrFooter.includes('₹') && inrFooter.includes('in INR'), inrFooter)
check('dashboard: native per-leg amounts are NOT re-converted', JSON.stringify(nativeBefore) === JSON.stringify(nativeAfter), nativeAfter.join(' / '))
check('dashboard: corporate label stays USD', (await txt('.region-currency .subtle')) === 'Corporate currency: USD')

// Maths: fetch the rate and check the footer is footer_usd / rate_INR (compact formatting => ~1% tolerance)
const rates = await page.evaluate(() => fetch('/api/currency/rates', { credentials: 'include' }).then(r => r.json()))
const expected = num(usdFooter) / rates.rates.INR
const shown = num(inrFooter)
check('dashboard: conversion maths correct', Math.abs(shown - expected) / expected < 0.01, `$${num(usdFooter)} / ${rates.rates.INR} = ₹${Math.round(expected)} ; shown ₹${shown}`)

// Chart data must follow (ForecastBars y-axis ticks should now carry ₹)
// Recharts re-measures asynchronously inside ResponsiveContainer, so wait for the ticks, not a timer.
await page.waitForTimeout(1500)
const tickHasRupee = await page.$$eval('.dashboard-grid svg text', e => e.some(x => x.textContent.includes('₹')))
check('dashboard: charts re-render in view currency', tickHasRupee)

// --------------------------------------------------------------- persists across pages
await page.goto(`${BASE}/#/leadership`, { waitUntil: 'networkidle' })
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
check('leadership: choice persists', (await page.$eval('.currency-picker select', s => s.value)) === 'INR')
check('leadership: KPIs in ₹', (await txt('.kpi-grid .kpi-card:first-child strong') || '').startsWith('₹'))
check('leadership: table values in ₹', (await page.$$eval('.table-panel tbody td', t => t.map(x => x.textContent))).some(t => t.includes('₹')))
check('leadership: normalisation label explains conversion', (await txt('.table-panel .subtle') || '').includes('Converted from USD to INR'), await txt('.table-panel .subtle'))

await page.goto(`${BASE}/#/forecast`, { waitUntil: 'networkidle' })
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
await page.waitForSelector('.kpi-card strong', { timeout: 20000 })  // rates can arrive before the report does
check('forecast: choice persists', (await page.$eval('.currency-picker select', s => s.value)) === 'INR')
check('forecast: KPIs in ₹', (await page.$$eval('.kpi-card strong', e => e.map(x => x.textContent))).some(t => t.includes('₹')))

// Reset to corporate and confirm it clears
await page.selectOption('.currency-picker select', 'USD')
await page.waitForTimeout(200)
check('forecast: back to USD', (await page.$$eval('.kpi-card strong', e => e.map(x => x.textContent))).some(t => t.includes('$')))
const saved = await page.evaluate(() => { try { return localStorage.getItem('pn.viewCurrency') } catch { return 'n/a' } })
check('corporate choice is not persisted (null)', saved === null, String(saved))

await page.goto(`${BASE}/#/dashboard`, { waitUntil: 'networkidle' })
await page.waitForSelector('.region-currency', { timeout: 20000 })
await page.selectOption('.currency-picker select', 'INR')
await page.waitForTimeout(400)
await page.screenshot({ path: 'dashboard-inr.png' })
await page.selectOption('.currency-picker select', 'USD')

console.log('\nproblems after login:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
