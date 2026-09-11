# PursuitNova v6 Validation Report

## Backend

Command:

```bash
cd backend
PYTHONPATH=. pytest -q
```

Result at packaging time:

**28 passed**

The 28th test is a v6 full seller-workflow contract covering:

1. create Company + primary Contact + Prospect
2. add Meeting
3. add structured MoM
4. create assigned Action
5. create Opportunity
6. add Follow-up
7. reload Lead 360 and confirm nested records/timeline
8. confirm server-side Prospect query
9. confirm server-side Opportunity query
10. confirm Dashboard summary and analytics remain available

Existing tests continue to cover hierarchy isolation, Presales sharing, duplicate controls, outcome validation, MFA/security, saved views, field permissions and enterprise controls.

## Frontend

- Node helper test: PASS
- Vite production compile: PASS
- React route-level chunks emitted: PASS
- compiled SPA served successfully by FastAPI: PASS (HTTP static asset smoke test)

The container execution environment blocks automated Chromium navigation by policy, so a browser-driven Playwright test could not be executed here. Browser UAT remains a release gate for the target JSAN environment.
