# Currency e2e sweeps

Headless checks that back the ✅ rows in `docs/currency-gaps.md`. They drive the real app against a
local backend (`:8000`) and dev server (`:5173`) using the README demo account, through your
installed Chrome — no browser download.

| Script | Covers |
|---|---|
| `full.mjs` | Dashboard region panel, FX warning ⇄ API state, Leadership donut filter, Forecast/Pipeline/KPI render |
| `fx.mjs` | Admin rates table + provenance, refresh button hits the API, key never reaches the browser |
| `picker.mjs` | "View in" picker: INR conversion maths, native legs untouched, charts/tables follow, persistence |
| `pipeline.mjs` | Pipeline stage totals are converted whole-set totals, mixed-currency columns, drawer currency editor |
| `smoke360.mjs` | Lead360 / Partnership360 render; new-opportunity currency defaults to the prospect's currency (corporate for partnerships) |
| `prospects.mjs` | Prospects table shows symbol + code by default; create form offers "Default for region"; edit form prefilled, saves, blank restores the default |
| `kpi_review.mjs` | KPI Tracker → Review team: a month alone shows nobody; choosing a person loads only theirs; "All people" is an explicit opt-in |
| `reconcile.mjs` | Open pipeline agrees across Pipeline / Dashboard / Leadership and closed-won across Dashboard / Leadership, in USD and EUR; Leadership cards name their period |
| `rates_freshness.mjs` | Caption names today's provider date with no "not refreshed"; one shared rates request per app rather than one per hook; a table past its TTL re-validates on focus, and choosing a currency re-validates unconditionally |

> **Stale scripts.** `full.mjs`, `picker.mjs`, `pipeline.mjs` and `reconcile.mjs` wait on `.kpi-grid`,
> which the dashboard simplification removed, so they time out at the login gate. `rates_freshness.mjs`
> is current; the others need their selectors updated to the present Dashboard.

> **Stop servers by tree.** `taskkill /PID <pid> /F` on a uvicorn parent leaves its child serving the
> port, bound to whatever `backend/.env` points at — which is the real dev database. Use
> `taskkill /PID <pid> /T /F`, run test servers on their own port, and confirm the port is dead
> before trusting that a restart took your `DATABASE_URL`.

```bash
# once: playwright-core only (drives the Chrome you already have)
npm i --no-save playwright-core

# with backend + `npm run dev` running
node e2e/rates_freshness.mjs
# BASE defaults to the dev server; point it at the backend to test the built bundle:
#   BASE=http://127.0.0.1:8000 node e2e/rates_freshness.mjs
node e2e/full.mjs && node e2e/fx.mjs && node e2e/picker.mjs && node e2e/pipeline.mjs && node e2e/smoke360.mjs && node e2e/prospects.mjs && node e2e/reconcile.mjs && node e2e/kpi_review.mjs
```

Set `CHROME` / `BASE` to override the Chrome path or app URL. Each script prints `PASS`/`FAIL` per
check and exits non-zero on any uncaught page error or failed request after login.
