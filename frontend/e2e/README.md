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
| `kpi_review.mjs` | KPI Tracker → Review team: a month alone shows nobody; choosing a person loads only theirs; two assigned regions → two live currency conversions |
| `reconcile.mjs` | Open pipeline agrees across Pipeline / Dashboard / Leadership and closed-won across Dashboard / Leadership, in USD and EUR; Leadership cards name their period |

```bash
# once: playwright-core only (drives the Chrome you already have)
npm i --no-save playwright-core

# with backend + `npm run dev` running
node e2e/full.mjs && node e2e/fx.mjs && node e2e/picker.mjs && node e2e/pipeline.mjs && node e2e/smoke360.mjs && node e2e/prospects.mjs && node e2e/reconcile.mjs && node e2e/kpi_review.mjs
```

Set `CHROME` / `BASE` to override the Chrome path or app URL. Each script prints `PASS`/`FAIL` per
check and exits non-zero on any uncaught page error or failed request after login.
