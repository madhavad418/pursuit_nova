# JSAN PursuitNova v6.0 — Real Full-Stack Product

**Business Development & Revenue Intelligence Platform**  
**Tagline:** From pursuit to predictable revenue.

PursuitNova v6 replaces the previous static-shell handover with a real React/Vite application wired to the proven FastAPI CRM backend.

## What is actually runnable

- React 19 + Vite frontend with route-level code splitting
- FastAPI backend with server-side authorization and CRM business rules
- PostgreSQL production path + Alembic migrations
- SQLite demo/test mode
- HttpOnly session cookies + CSRF + MFA foundation
- hierarchy-aware Prospect and Opportunity access
- Company + multiple Contacts
- Lead 360 with Meetings, MoM, Actions, Opportunities, Follow-ups and Timeline
- visual Opportunity Pipeline
- corporate-currency Forecast / Best Case / Commit / Won
- quarterly / half-year Leadership Analytics
- saved views, dashboard preferences, server-side pagination/filtering
- Microsoft Graph integration foundation
- monitoring / audit / backup utilities

## Primary user journey

**Dashboard → Prospects → Lead 360 → Actions → Opportunity Pipeline → Forecast → Leadership Analytics**

## Quick start — real React development mode

Prerequisites: Python 3.11+ and Node 22+.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### 2. Frontend

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to FastAPI on port 8000.

Or use `start-dev.bat` / `./start-dev.sh` after dependencies are installed.

### Demo login

- `director@jsan.local`
- password: `PursuitNovaDemo@2026`

Other seeded roles are described in `docs/DEVELOPER_HANDOVER.md`.

## Production-like local run

```bash
docker compose up --build
```

Open **http://localhost:8000**. The multi-stage Docker image compiles React and serves the compiled SPA and FastAPI from the same origin, backed by PostgreSQL.

## Validation

Backend:

```bash
cd backend
PYTHONPATH=. pytest -q
```

Expected: **28 passed**.

Frontend:

```bash
cd frontend
npm test
npm run build
```

The release artifact already contains a compiled `frontend/dist` generated from the included React source.

## Deployment recommendation

The recommended first production deployment is **one same-origin container + managed PostgreSQL**. This avoids cross-site cookie problems and gives the simplest secure operational model.

See `docs/DEPLOYMENT.md` for Railway and optional Vercel split deployment.

## Important production gates

Before real customer/contact data is loaded:

1. corporate SSO / OIDC
2. production PostgreSQL and migration validation
3. secrets manager + HTTPS
4. Microsoft 365 tenant registration and consent
5. centralized logs/traces/alerts
6. live PostgreSQL backup/restore drill
7. independent penetration test
8. JSAN UAT and SVP sign-off

This package is a full-stack product candidate, not a claim that the environment-dependent production gates above have already been completed.
