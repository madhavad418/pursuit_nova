// Both 360 pages render their create-opportunity modal with a currency select driven by the live
// rate table. This guards the regression where the hook was declared in the page but used in the
// modal component ("fx is not defined" -> whole page error boundary).
import { chromium } from 'playwright-core'

const CHROME = process.env.CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = process.env.BASE || 'http://localhost:5173'
const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })
const problems = []
page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))
const check = (name, ok, detail = '') => console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`)

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
const rates = await page.evaluate(() => fetch('/api/currency/rates', { credentials: 'include' }).then(r => r.json()))

for (const [label, listPath, route] of [['lead360', '/api/leads', 'lead'], ['partnership360', '/api/partnerships', 'partnership']]) {
  const list = await page.evaluate(p => fetch(p, { credentials: 'include' }).then(r => r.json()), listPath)
  const first = Array.isArray(list) ? list[0] : (list.items || [])[0]
  if (!first) { check(`${label}: has a record to open`, false, 'none in data'); continue }
  await page.goto(`${BASE}/#/${route}/${first.id}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(900)
  const text = await page.$eval('body', e => e.innerText)
  check(`${label}: page renders without an error boundary`, !text.includes('ran into a problem'), text.includes('ran into a problem') ? text.slice(text.indexOf('ran into a problem'), text.indexOf('ran into a problem') + 80) : '')
  const opener = await page.$('text=Create opportunity') || await page.$('text=New opportunity')
  if (opener) { await opener.click(); await page.waitForTimeout(500) }
  const sel = await page.$$eval('select', sels => sels.map(s => ({ value: s.value, options: [...s.options].map(o => o.value) })).find(s => s.options.includes('USD') && s.options.length > 1))
  // A prospect's new opportunity defaults to the prospect's own currency; a partnership has none, so corporate.
  const expected = route === 'lead' ? (first.currency || rates.corporate_currency) : rates.corporate_currency
  check(`${label}: currency select defaults to ${route === 'lead' ? "the prospect's currency" : 'corporate'} and lists rated currencies`, !!sel && sel.value === expected && sel.options.length >= Object.keys(rates.rates).length, `${JSON.stringify(sel)} expected ${expected}`)
  await page.keyboard.press('Escape')
}

console.log('\nproblems:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
