# Deployment Guide

## Option A — Recommended: Railway full-stack service + Railway/managed PostgreSQL

This is the preferred initial production architecture. **Step-by-step guide: [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md).**

1. Create PostgreSQL service.
2. Deploy repository using the root `Dockerfile`.
3. Set production environment variables:

```text
APP_ENV=production
DATABASE_URL=<managed PostgreSQL URL>
JWT_SECRET=<32+ char random secret>
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
SEED_DEMO=false
AUTO_CREATE_SCHEMA=false
CORS_ORIGINS=https://<pursuitnova-domain>
METRICS_TOKEN=<random secret>
INTEGRATION_ENCRYPTION_KEY=<Fernet key when Microsoft integration enabled>
```

4. The container runs `alembic upgrade head` before starting FastAPI.
5. Point a JSAN domain to the Railway service.
6. Health check: `/readyz`.

The Docker build compiles React first and copies `frontend/dist` into the Python runtime image. FastAPI serves the SPA and `/api` from one origin.

## Option B — Split frontend/backend

Use only when independent frontend release cycles are required.

- React: Vercel
- FastAPI: Railway/Azure/AWS
- PostgreSQL: managed database

Recommended domains:

```text
https://pursuitnova.jsanconsulting.com
https://api.pursuitnova.jsanconsulting.com
```

Set:

```text
frontend: VITE_API_BASE_URL=https://api.pursuitnova.jsanconsulting.com
backend:  CORS_ORIGINS=https://pursuitnova.jsanconsulting.com
backend:  COOKIE_SECURE=true
```

Keep frontend and API under the same registrable corporate domain. Avoid pairing a `vercel.app` frontend with a `railway.app` API for final production session handling because browser third-party-cookie behavior can vary.

## Development

Vite runs at `localhost:5173` and proxies API calls to `localhost:8000`, so the React code still uses relative `/api` URLs.

## Database

- migrations: `cd backend && alembic upgrade head`
- rollback rehearsal: `alembic downgrade -1`
- production backups: `pg_dump`
- restore drill: `pg_restore` into an isolated validation database
