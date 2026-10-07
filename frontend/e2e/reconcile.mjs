// The money figures a reader can compare across pages must agree, in whatever currency they view:
// Pipeline "Open pipeline" == Dashboard "Open pipeline" == Leadership "Open pipeline today", and
// Dashboard "Closed won" == Leadership "All time won". Leadership's headline cards must say which
// period they cover.
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
// Compact money ("€1.3M", "₹142.6M") back to a number; compact rounding allows ~1% slack.
const num = s => { const m = String(s).replace(/,/g, '').match(/([0-9.]+)\s*([KMB])?/); if (!m) return NaN; return Number(m[1]) * ({ K: 1e3, M: 1e6, B: 1e9 }[m[2]] || 1) }
const close = (a, b) => Math.abs(a - b) <= Math.max(1, Math.max(a, b) * 0.011)

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.fill('input[type=email]', 'superadmin@jsan.local')
await page.fill('input[type=password]', 'PursuitNovaDemo@2026')
await page.click('button[type=submit]')
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
authed = true

const apiActive = await page.evaluate(() => fetch('/api/query/opportunities?page_size=200', { credentials: 'include' }).then(r => r.json()).then(d => d.summary.active))
for (const view of ['USD', 'EUR']) {
  // Dashboard
  await page.goto(`${BASE}/#/dashboard`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.currency-picker select', { timeout: 20000 })
  await page.selectOption('.currency-picker select', view); await page.waitForTimeout(500)
  const dashOpen = num(await txt('.kpi-grid .kpi-card:nth-child(1) strong'))
  const dashWon = num(await txt('.kpi-grid .kpi-card:nth-child(3) strong'))
  const dashWins = Number((await txt('.kpi-grid .kpi-card:nth-child(3) small') || '').match(/(\d+) wins/)?.[1])

  // Pipeline (same odd path the user is on)
  await page.goto(`${BASE}/admin/users#/pipeline`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.mini-kpis strong', { timeout: 20000 })
  await page.waitForTimeout(400)
  const pipeOpen = num(await txt('.mini-kpis > div:first-child strong'))

  // Leadership (same odd path)
  await page.goto(`${BASE}/admin/users#/leadership`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.kpi-grid .kpi-card .kpi-alltime', { timeout: 20000 })
  await page.waitForTimeout(400)
  const label1 = await txt('.kpi-grid .kpi-card:nth-child(1) .kpi-top span')
  const label2 = await txt('.kpi-grid .kpi-card:nth-child(2) .kpi-top span')
  const created = await txt('.kpi-grid .kpi-card:nth-child(1) strong')
  const alltime1 = await txt('.kpi-grid .kpi-card:nth-child(1) .kpi-alltime')
  const alltime2 = await txt('.kpi-grid .kpi-card:nth-child(2) .kpi-alltime')
  const leadOpen = num(alltime1.match(/Open pipeline today: ([^·]+)/)?.[1])
  const leadActive = Number(alltime1.match(/(\d+) active/)?.[1])
  const leadWon = num(alltime2.match(/All time: ([^·]+)/)?.[1])
  const leadWins = Number(alltime2.match(/(\d+) wins/)?.[1])

  check(`[${view}] leadership cards name their period`, /Pipeline created · Q\d \d{4}/.test(label1) && /Won value · Q\d \d{4}/.test(label2), `${label1} | ${label2}`)
  check(`[${view}] open pipeline: Pipeline == Dashboard == Leadership`, close(pipeOpen, dashOpen) && close(leadOpen, dashOpen), `pipeline ${pipeOpen} | dashboard ${dashOpen} | leadership ${leadOpen}`)
  check(`[${view}] active count: Leadership == Pipeline API`, leadActive === apiActive, `${leadActive} vs ${apiActive}`)
  check(`[${view}] closed won: Dashboard == Leadership all-time`, close(leadWon, dashWon) && leadWins === dashWins, `dashboard ${dashWon} (${dashWins}) | leadership ${leadWon} (${leadWins})`)
  check(`[${view}] figures carry the view currency`, [created, alltime1, alltime2].every(t => t.includes(view === 'EUR' ? '€' : '$')), `${created} / ${alltime1.slice(0, 40)}`)
}

const api = await page.evaluate(() => Promise.all([
  fetch('/api/query/opportunities?page_size=200', { credentials: 'include' }).then(r => r.json()),
  fetch('/api/dashboard/summary', { credentials: 'include' }).then(r => r.json()),
]))
check('API: active counts agree', api[0].summary.active === api[1].active_opportunities, `${api[0].summary.active} vs ${api[1].active_opportunities}`)

await page.goto(`${BASE}/#/dashboard`, { waitUntil: 'networkidle' })
await page.waitForSelector('.currency-picker select', { timeout: 20000 })
await page.selectOption('.currency-picker select', 'USD')
console.log('\nproblems after login:', problems.length ? problems : 'none')
await browser.close()
process.exit(problems.length ? 1 : 0)
