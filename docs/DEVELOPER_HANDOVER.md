# Developer Handover

## Source layout

```text
frontend/
  src/
    components/      shared UI, auth, shell, charts
    lib/             API client, formatting, lightweight router
    pages/           Dashboard, Prospects, Lead360, Actions, Pipeline, Forecast, Leadership, Admin
  public/
  dist/              validated compiled output

backend/
  app/main.py        FastAPI routes / services
  app/db.py          SQLAlchemy tables, seed, DB helpers
  migrations/        Alembic migrations
  tests/             regression + full seller-workflow contract
```

## Demo users

Password for disposable demo only: `PursuitNovaDemo@2026`

- director@jsan.local
- bd.manager@jsan.local
- bd.lead@jsan.local
- bd.exec1@jsan.local
- bd.exec2@jsan.local
- presales@jsan.local
- admin@jsan.local
- superadmin@jsan.local

## Frontend implementation notes

- Login is a real `/api/auth/login` call; it is not a static login screen.
- API mutations automatically attach the CSRF token.
- Lead/Opportunity lists use server-side query endpoints.
- Dashboard/Forecast/Leadership charts are populated from API JSON.
- Prospect creation supports new Company or reuse of an existing Company.
- Lead 360 writes Meetings, MoM, Actions, Contacts, Opportunities and Follow-ups.
- Opportunity closing rules remain server-enforced.
- React pages are lazy-loaded to keep the main bundle smaller.

## Do not deploy `index.html` by itself

The old v5 problem was a static shell handover. v6 is designed as a compiled React SPA plus API. Deploy either:

- the root Docker image (recommended), or
- `frontend/dist` + the API with the documented split configuration.
