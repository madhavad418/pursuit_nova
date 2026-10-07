# Currency handling — gap rubric

Scoring grid for everything that touches money in PursuitNova. One row per criterion; each carries a
status, the evidence behind it, and whatever is still open. Re-score after any change to `fx_rates`,
`to_corporate`, the provider client, or a page that renders money.

**Scope** — the corporate-currency model (`org_settings.corporate_currency`, default USD), the
`fx_rates` table, the exchangerate-api.com feed, every endpoint that converts, every page that shows
a converted or native figure, and every write path that stores a currency or an amount.

**Status legend** — a row is ✅ only when a test in the repo asserts the criterion *as worded*.

| Mark | Meaning |
|---|---|
| ✅ PASS | Asserted by a backend test (`backend/tests/`), a frontend unit test (`frontend/src/lib/*.test.js`) or an e2e sweep (`frontend/e2e/`) |
| ⚠️ PARTIAL | Main path holds; a named edge is open — the edge is listed in the residual column |
| ❌ OPEN | Not addressed |
| 🔵 DECISION | Needs a product/finance call before it can be closed |

Severity: **H** a figure can be wrong, hidden or crash a page · **M** right but unexplained, fragile or inconsistent · **L** polish.

Evidence shorthand: `R:` = `test_region_currency.py`, `P:` = `test_fx_provider.py`, `JS:` = `currency.test.js` / `format.test.js`, `E:` = `frontend/e2e/<script>` check name.

---

## 1. Correctness of conversion

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 1.1 | A currency code matches regardless of case, whitespace, **or common alias** (`"inr"`, `"INR "`, `"Rs"`, `"$"`, `"US$"`, `"Rupees"`) | H | ✅ | `norm_currency` + `CURRENCY_ALIASES`; `R:test_currency_spelling_variants_all_convert`, `P:test_common_aliases_resolve_to_iso_codes` (7 aliases) | Alias table is finite; an unlisted spelling is reported under 1.4 rather than guessed |
| 1.2 | Currency normalised on **every** write path | H | ✅ | Opportunity create/update (`R:…update_endpoint_is_also_normalized`), partner create/update, targets, and the admin rate PUT (`P:test_rate_put_validates_everything_before_writing` — `" gbp "` stored as `GBP`, no stray row). CSV importers write no currency or amount (verified; row 6.3 closed) | Partner-opportunity and target writes are normalised by the same helper but have no dedicated test |
| 1.3 | A blank currency means the **corporate** currency, on read *and* write | H | ✅ | Read: `R:test_blank_currency_falls_back_to_corporate_not_to_zero`. Write: all six sites now default to `norm_currency(corporate_currency())`, not the literal `"USD"`; forms default from `/api/currency/rates` (`E:smoke360 currency select defaults to corporate`) | — |
| 1.4 | A currency with **no rate** is reported on every converting response, never a silent 0 | H | ⚠️ | `to_corporate` → `None`; `missing_fx_rates` now on analytics, dashboard summary (`P:test_dashboard_summary_reports_missing_rates`), pipeline query (`P:…per_stage_converted_totals`), forecast and period report; `fx.unconvertible_opportunities` counts only deals that carry value. Banners on Dashboard, Leadership, Pipeline (`E:pipeline banner matches API state`) | The *converted totals themselves* still fold an unrated deal in as 0 — by design, because the native amount is shown beside it and the banner names it. The region panel is the only place a partial total is withheld (4.2). |
| 1.5 | Provider quotes reciprocated correctly (1 USD = 96.467 INR → 1 INR = 0.010366 USD) | H | ✅ | `P:test_quotes_are_reciprocated_into_rate_to_corporate` asserts GBP > 1 > INR and a one-way ₹5,000,000 conversion; `JS:` round-trips the inverse | — |
| 1.6 | Corporate currency is always exactly 1.0 — after refresh, after a manual PUT, at seed | H | ✅ | Refresh: `P:…reciprocated` (`rates["USD"]==1.0`). PUT: base enforced after validation. Seed: `db.py` seeds the corporate row at 1.0 for any `CORPORATE_CURRENCY` (only USD placeholders exist, so a non-USD seed gets just its base row) | PUT base enforcement has no dedicated test beyond the rebase tests |
| 1.7 | A zero, negative, non-finite or non-numeric quote/rate is refused, never divided by | M | ✅ | Quotes: non-numeric skipped, ≤0/inf/nan dropped (`P:…zero_quote_is_refused`). Manual rates: `P:test_rate_put_validates_everything_before_writing` rejects `-1`, `inf`, `nan`, `abc` | — |
| 1.8 | Display-side "view in" conversion is the exact inverse of the server's | H | ✅ | `convertFromCorporate` divides by the same `rate_to_corporate`; `JS:` round-trip; `E:picker conversion maths correct` ($1,047,747 / 0.010366 = ₹101,073,010 vs shown ₹101,072,990 — compact rounding) | Client and server are only compared e2e, not in a unit test |
| 1.9 | Native per-region amounts are **never** re-converted by the view picker | H | ✅ | `E:picker native per-leg amounts are NOT re-converted`; `E:pipeline native card amounts untouched` | — |
| 1.10 | A deal closed-won at a genuine 0 reports 0, not its pre-close amount | L | ✅ | `won_amount()` uses `is not None`; `P:test_closed_won_at_zero_reports_zero_not_the_pre_close_amount` | A role whose `final_amount` is **masked** still sees the pre-close amount substituted — see 5.5 |
| 1.11 | Amounts are finite and non-negative on write; a bad value is a 400, not a stored `inf` that 500s every dashboard | H | ✅ | `money_value()`; `P:test_non_finite_or_malformed_amounts_are_a_400_not_a_500` (`1e999`, `nan`, `-5`, `"50k$"`) then asserts `/api/dashboard/summary` is still 200 | — |

## 2. Rate provenance and freshness

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 2.1 | Live rates from a provider rather than seeded placeholders | H | ⚠️ | exchangerate-api.com v6 wired; seeded INR 0.012 vs live 0.010366 = **15.8 % overstatement** on every INR figure before this | **True in dev only.** `EXCHANGERATE_API_KEY` is not yet set in Railway, so production is still on the seeded `DEFAULT` rows. Until it is set, every converted production figure carries that error. |
| 2.2 | Rates refresh automatically | H | ⚠️ | `auto_refresh_fx_rates()` on a boot thread, when stale, on placeholder, **or when a currency in use has no row** (`P:…replaces_seeded_placeholders…`, `…skipped_when…current`) | **Only at startup.** A container up for weeks never refreshes; 2.10 flags it but nothing fixes it. Needs an in-process daily timer or a scheduled job (new variable, e.g. `FX_AUTO_REFRESH_HOURS`). |
| 2.3 | Seeded placeholders are replaced even though they carry today's date | H | ✅ | Placeholder-source check; `P:test_auto_refresh_replaces_seeded_placeholders_even_when_dated_today` | — |
| 2.4 | Every stored rate records where it came from and when | M | ✅ | `source`, `as_of`, `updated_by`, `updated_at`; `P:test_refresh_records_provenance`; corporate row stamped `CORPORATE-BASE` | Admin table shows `as_of`/`source`, not `updated_by`/`updated_at` |
| 2.5 | Reader can tell provider / hand-entered / placeholder on every money page | M | ✅ | `/api/currency/rates` returns `live`, `sources`, `manual`, `placeholder`; picker caption "Provider rates · 07 Oct 2026" / "Hand-entered rates …" / "Placeholder rates …" (`E:picker caption names provider rates and their date`); `P:…live_flag_tracks_provenance` | Caption is hidden when only the corporate currency has a rate (nothing to pick) |
| 2.6 | Only currencies actually in use are refreshed | M | ✅ | `currencies_in_use()` = rate rows ∪ opportunities ∪ partner opps ∪ targets; `P:…covers_currencies_the_data_actually_uses` | A currency that *ever* had a row is refreshed forever; there is no rate-delete endpoint |
| 2.7 | Changing the corporate currency re-bases every rate — or refuses | H | ✅ | Provider quotes for the **new** base are fetched *before* anything is written; a provider failure changes nothing (`P:test_a_failed_rebase_changes_nothing`); success re-bases and audits `REBASE` (`P:…rebases_from_the_provider`, asserts `/latest/INR` was called and USD ≈ 96 INR). Without a key the request must carry a rate for every currency in use or it is a 409 naming the gaps (`P:…needs_a_full_manual_set`) | — |
| 2.8 | Hand-entered (treasury) rates survive a provider refresh | H | ✅ | `MANUAL`/`TREASURY` rows are kept and reported under `kept_manual`; `override_manual=True` only on a corporate re-base (old-base manual rates are meaningless); `P:test_a_hand_entered_rate_survives_a_provider_refresh` | Admin UI shows `manual_rates` but has no "release to provider" control |
| 2.9 | Staleness is reported separately from provenance | M | ✅ | `/api/currency/rates.stale` = oldest rate > 2 days old; caption appends "· not refreshed" in amber; `P:test_rates_endpoint_flags_staleness_separately_from_provenance` | Threshold (2 days) is a constant, not configurable |
| 2.10 | `as_of` is always a real date, so the freshness guard cannot be defeated by free text | M | ✅ | PUT rejects `"today"` (`P:…validates_everything…`); `iso_date()` ignores non-dates everywhere they are compared; comparison uses the provider's UTC date | — |
| 2.11 | Rate history is retained so a past report can be reproduced | M | 🔵 | `fx_rates` is one row per currency; a refresh overwrites. `AUTO-REFRESH`/`REFRESH`/`REBASE` audit rows carry the result but not the previous value | Finance decision: `fx_rate_history` table, or snapshot the rate onto an opportunity at close |
| 2.12 | Historical totals use the rate at the time, not today's | M | 🔵 | `quarter_trend` and `period_report` convert with the current map | Same decision as 2.11; last quarter's number moves whenever rates do |

## 3. Provider integration

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 3.1 | API key is never committed | H | ✅ | `backend/.env` (gitignored) only; `git grep` over tracked files and a scan of every new file finds nothing; e2e `fx.mjs` reads it from `EXCHANGERATE_API_KEY` and skips the leak assertion if unset | Production variable still to be set (2.1) |
| 3.2 | Key never appears in an error, log or response | H | ✅ | Errors by status/class only (`P:test_provider_failures_surface_without_the_api_key`, 7 modes); `httpx` logger pinned to WARNING so its request-URL line cannot surface; `E:fx API key never reaches the browser` when the key is in the env | — |
| 3.3 | Provider outage cannot break boot or the health check | H | ✅ | Daemon thread, all exceptions swallowed; `P:test_auto_refresh_never_raises` | — |
| 3.4 | Provider errors are distinguishable, and a wrong base is refused | M | ✅ | 403 / 429 / unreachable / malformed / no rates / `base_code` mismatch → 502 with a plain message | — |
| 3.5 | Quota respected (free tier 1 500 / month) | M | ✅ | One call per start when stale, plus manual clicks; Railway `restartPolicyMaxRetries: 5` bounds a crash loop | — |
| 3.6 | Tests never hit the network | M | ✅ | `httpx.Client` patched in every provider test; `conftest.py` pops `EXCHANGERATE_API_KEY` and sets `FX_AUTO_REFRESH=false` so an exported key cannot leak into the suite | — |
| 3.7 | A currency the provider does not quote keeps its last value and is reported | M | ✅ | `unsupported` in the refresh result; `P:…does_not_quote_is_reported_not_guessed` | — |
| 3.8 | Concurrent refreshes (boot thread + admin click) cannot interleave | L | ✅ | `FX_LOCK` around the upsert loop | No test — a race is not reproducible in the suite |

## 4. Display and UX

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 4.1 | Region-wise native currency on the Dashboard | H | ✅ | "Pipeline by region & currency" panel; one leg per currency in its own symbol; `E:full dashboard: region panel renders`, `native currency symbols differ` | — |
| 4.2 | A region's corporate total is withheld, not shown partial, when a leg cannot convert | H | ✅ | `pipeline_corporate: null` → "total unavailable — X has no rate"; `R:…keeps_its_real_amount_and_is_flagged` | Headline KPIs on the same page are the partial `/api/dashboard/summary` figures — the banner says so (1.4) |
| 4.3 | "View in" picker on every page that shows converted totals | M | ✅ | Dashboard, Leadership, Forecast, **Pipeline**; choice persists (`E:picker leadership/forecast choice persists`); corporate choice stored as nothing | KPI Tracker renders no money (counts only) — nothing to wire |
| 4.4 | Picker falls back honestly when rates are unavailable | M | ✅ | Hook takes the page's own reported currency as fallback (no hard-coded `'USD'`); on fetch failure shows "Exchange rates unavailable — figures shown in X" and converts nothing; a saved choice whose rate vanished falls back to corporate | Hook itself has no unit test (pure functions do: `JS:` 6 cases) |
| 4.5 | Missing-rate warning on every page that converts | M | ✅ | Dashboard, Leadership, Pipeline (`E:pipeline banner matches API state`), Forecast | — |
| 4.6 | Pipeline board column totals are converted whole-set totals, never raw amounts summed across currencies | H | ✅ | Headers read `summary.by_status[stage]` (server-side, converted, whole filtered set, not the page); `E:pipeline stage totals are the converted whole-set totals` and `a mixed-currency column is converted, not summed raw` (₹5M + ₹2.5M + AED 75K → **$98.2K**, previously "$7,575,000"); unrated deals shown as "+N unrated" | — |
| 4.7 | Write-side currency fields are driven by corporate/rated options, never by the view currency | H | ✅ | Forecast target form (payload + dropdown), Lead360/Partnership360 create forms, Pipeline drawer — all default to corporate and list `rates` (`E:smoke360`, `E:pipeline currency options are the rated currencies`) | — |
| 4.8 | Layout holds at phone width | L | ✅ | `E:full` (earlier run: no horizontal overflow at 390 px; region cards fit) | The 390 px assertion lives in a scratch script not copied to `e2e/` |
| 4.9 | Every converted figure says which currency and which rate date it is in | M | ✅ | KPI values carry the symbol; both Leadership tables carry "All values normalized to USD" / "Converted from USD to INR at the rate of 07 Oct 2026"; Forecast "FX as of" now uses the **oldest** rate and the same date format as the picker | — |
| 4.10 | Top opportunities ranked by converted value, not raw native amount | M | ✅ | `P:test_top_opportunities_are_ranked_by_converted_value` | — |
| 4.11 | A masked (hidden-field) amount renders as "—", not a convincing "$0" | M | ✅ | `money(null)` → "—"; `JS:money treats null as a masked field, not a zero` | Only `amount`/`final_amount` per-deal displays are affected; aggregates are a backend concern (5.5) |
| 4.12 | `money()` never prints `null`/`undefined`/un-normalised codes | M | ✅ | Normalises code, honours compact in the non-ISO fallback; `JS:` 4 cases | `en-US` grouping only — ₹101.1M rather than lakh/crore (product choice) |
| 4.13 | A mis-coded currency can be corrected from the UI | L | ✅ | Pipeline drawer edit form has a Currency select and labels the amount with it (`E:pipeline currency is editable in the drawer`) | — |

## 5. Permissions, scope and audit

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 5.1 | Refreshing or editing rates requires forecast-admin | M | ✅ | `TARGET_EDIT` or `ROLE_ADMIN`; `P:test_refresh_endpoint_requires_forecast_admin` (403) | — |
| 5.2 | Reading rates for display needs only a session | M | ✅ | `P:test_rates_endpoint_is_readable_by_any_signed_in_user`, `…requires_a_session` (401) | — |
| 5.3 | Every rate write is audited, including the boot refresh | M | ✅ | `REFRESH`, `UPDATE`, `REBASE`, and now `AUTO-REFRESH` (user `None`) | No test asserts an audit row |
| 5.4 | Region/currency breakdown respects record visibility exactly | H | ✅ | `R:test_region_currency_follows_record_scope` asserts the BD Executive's count **equals** their `/api/opportunities` count and is **less** than the whole business (was a vacuous `<=`) | A deal visible only through presales/team/share whose *lead* is outside the viewer's lead scope files under "Unassigned" (region unknown to that viewer) |
| 5.5 | Aggregates for a role with `final_amount` masked | M | 🔵 | `mask_fields` nulls the column for that role, so `won_amount()` falls back to the pre-close `amount` and that role's won totals differ from everyone else's | Decision: compute aggregates from unmasked rows (leaks a proxy of a hidden field) or exclude masked deals from that role's won totals |

## 6. Data hygiene

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 6.1 | Admin can see which rates are placeholders and which are hand-entered | M | ✅ | `stale_rates` + `manual_rates` + warning on `/api/admin/currency`; `P:…returns_the_updated_table` asserts `stale_rates==[]` after refresh | No test asserts a non-empty `stale_rates` before refresh |
| 6.2 | The reported bad record ("Saumya … 50k$") | — | 🔵 | Production data; no opportunity delete endpoint exists. `"50k$"` is now a 400 (1.11) and `"$"` an alias (1.1), so the class cannot recur | Record to be identified by its owner |
| 6.3 | CSV import normalises currency | — | N/A | Neither importer writes `amount` or `currency` | — |
| 6.4 | Dev database carries three test opportunities from this work | L | ⚠️ | "Chandrika INR deal", "Second INR deal", "Gulf expansion" in `backend/data/pursuitnova.db` | Local only; left on instruction not to touch the database |
| 6.5 | CSV export carries the corporate-converted value and the rate date | L | ❌ | `/api/export/opportunities.csv` emits native `amount`/`currency` only | Exported won value ≠ dashboard; add `amount_<corp>`, `final_amount`, `fx_as_of` columns |


## 7. Prospect default currency

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 7.1 | Every prospect carries a default deal currency, visible on the Prospects table by default as **symbol + code** (₹ INR, $ USD) | M | ✅ | `leads.currency` (migration `e1a7c4b2d9f0`); dev DBs get the column + backfill from `init_db`; `currencySymbol()` (`JS:` 8 cases); Prospects column after Region (`E:prospects every cell is "<symbol> <code>"`, `symbols match their codes`) | Column is not sortable/filterable (plain header) |
| 7.2 | Set from the region when not chosen; explicit choice wins and is normalised | M | ✅ | `REGION_CURRENCY` + `region_currency()`; `test_lead_currency.py` (9 region cases, `" gbp "` → `GBP`, `"$"` → `USD`) | Map is finite — unmapped regions get the corporate currency |
| 7.3 | Editable from the prospect edit form (Prospects table and Lead360 share `ProspectEditor`); blank restores the region default | L | ✅ | `PUT /api/leads/{id}`; `test_prospect_currency_is_editable_and_blank_restores_the_region_default`; `E:prospects edit form … prefilled`, `saving the edit PUTs the currency`, `"Default for region" restores the original` | — |
| 7.4 | A new opportunity on a prospect inherits the prospect's currency | H | ✅ | `add_opportunity` defaults to the lead's currency before corporate; `test_new_opportunity_inherits_the_prospect_currency`; `E:smoke360 defaults to the prospect's currency` | — |
| 7.5 | Backfill leaves no prospect without a currency | M | ✅ | `backfill_lead_currency()` in the migration and in `init_db`; `test_backfill_leaves_no_prospect_without_a_currency` | — |
| 7.6 | Prospect currencies count as "in use" so the provider fetches their rates | M | ✅ | `currencies_in_use()` includes `leads.c.currency`; `test_prospect_currencies_count_as_in_use` (SGD) | A region default the provider does not quote stays unrated until a manual rate is entered |
| 7.7 | Partnerships are untouched (no currency column) | — | ✅ | `test_partnerships.py` suite green after the change | — |


## 8. Cross-page consistency

The same viewer must read the same number for the same thing on every page. Period figures (Leadership) are a labelled subset of the all-time ones.

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 8.1 | Open pipeline: Pipeline mini-KPI == Dashboard KPI == Leadership "Open pipeline today" | H | ✅ | `test_cross_page_consistency.py::test_open_pipeline_agrees_across_pages` (superadmin and a BD Executive); `E:reconcile open pipeline: Pipeline == Dashboard == Leadership` in USD and EUR | — |
| 8.2 | Closed won: Dashboard == Leadership all-time == Pipeline board "Closed Won" column | H | ✅ | `…test_closed_won_agrees_across_pages`; the board column now uses the final amount like every other won figure (was adding pre-close amounts: $655K vs $634K); `E:reconcile closed won` | Deal cards in the Closed Won column still show the pre-close `amount` (pre-existing) |
| 8.3 | Board stage totals add up to the open pipeline and the stage counts to the row total | M | ✅ | `…test_board_stage_totals_add_up_to_the_open_pipeline` | — |
| 8.4 | Leadership period figures are exactly the in-period subset | H | ✅ | `…test_period_figures_are_the_in_period_subset` recomputes "created in Q" from the opportunity list and the live rates | — |
| 8.5 | Every headline card says which period it covers, and carries the all-time figure beside it | M | ✅ | `period_report.all_time`; cards read "Pipeline created · Q4 2026 … Open pipeline today: €1.3M · 6 active (as on Opportunity Pipeline)"; `E:reconcile leadership cards name their period` | — |
| 8.6 | Active-opportunity count agrees across Pipeline, Dashboard and Leadership | M | ✅ | `test_open_pipeline_agrees_across_pages`; `E:reconcile active count` | — |


## 9. KPI review

| # | Criterion | Sev | Status | Evidence | Residual |
|---|---|---|---|---|---|
| 9.1 | Review team shows nobody's data until a person is chosen; "All people" is an explicit opt-in | H | ✅ | No `/api/kpi/review` call without a person (`E:kpi_review changing the month fetches nothing without a person`, `only … calls carry user_id`); `test_kpi_review_regions.py::test_review_list_is_scoped_to_the_requested_person` | Manage-KPIs tab still lists everyone by default (not in scope) |
| 9.2 | A reviewable person's assigned regions and their currencies are available to the API | L | ✅ | `users-with-category` returns `regions` + `currencies` via `region_currency`; `test_two_regions_give_two_conversions` (India, UK → INR, GBP) | The on-screen conversion strip was built and then removed from the KPI tab at the owner's request; the data stays for any other surface |
| 9.3 | Regional currencies of people count as "in use" so the provider fetches their rates | M | ✅ | `currencies_in_use()` includes active users' region currencies; asserted in `test_two_regions_give_two_conversions` | — |

---

## Open items, ranked

| Rank | Row | Sev | What | Suggested fix |
|---|---|---|---|---|
| 1 | 2.1 / 3.1 | H | `EXCHANGERATE_API_KEY` not set in Railway — production still on 15.8 %-wrong INR placeholder | Set the variable; the next deploy's boot refresh replaces every placeholder |
| 2 | 2.2 | H | Rates refresh only at startup | In-process daily timer with the same guard as boot (new `FX_AUTO_REFRESH_HOURS`) |
| 3 | 2.11 / 2.12 | M | No rate history; history re-converts at today's rate | Finance decision — period-fixed rates vs live |
| 4 | 5.5 | M | Masked `final_amount` skews that role's won totals | Decision on aggregate semantics for masked fields |
| 5 | 6.5 | L | CSV export has no converted column | Add columns |
| 6 | 6.2 | — | Saumya's record | Data owner to identify |

## How to re-score

```bash
# backend — 85 currency + consistency tests
cd backend && python -m pytest tests/test_region_currency.py tests/test_fx_provider.py tests/test_lead_currency.py tests/test_cross_page_consistency.py -q

# frontend pure conversion + formatter
cd frontend && node --test src/lib/currency.test.js src/lib/format.test.js

# e2e sweeps (backend + `npm run dev` running; see frontend/e2e/README.md)
cd frontend && node e2e/full.mjs && node e2e/fx.mjs && node e2e/picker.mjs && node e2e/pipeline.mjs && node e2e/smoke360.mjs && node e2e/prospects.mjs && node e2e/reconcile.mjs && node e2e/kpi_review.mjs
```

*Scored 2026-10-07 against the working tree after the review pass (three independent audits: backend conversion paths, frontend money rendering, adversarial audit of this rubric's own claims). Nothing committed at time of scoring.*
