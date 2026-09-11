# PursuitNova v6 Architecture

## Recommended production topology

```text
User Browser
    |
    | HTTPS
    v
PursuitNova Web Service (same origin)
    |-- React/Vite compiled SPA
    |-- FastAPI /api
    |-- Auth / RBAC / CSRF / MFA
    |-- CRM business services
    |-- Forecast / FX / Workflow / Audit
    |
    +------ PostgreSQL (managed)
    |
    +------ Microsoft Graph (Outlook / Calendar / Teams)
    |
    +------ OTLP / metrics / centralized logging
```

The same-origin topology is intentional. PursuitNova uses secure HttpOnly session cookies. Serving React and FastAPI on one origin avoids third-party-cookie and cross-site CSRF complexity.

## Frontend

- React 19
- Vite 8
- Recharts
- modular page/feature components
- hash-based client navigation so the compiled SPA has no server-side route dependency
- lazy-loaded feature pages
- relative `/api` calls by default
- credentials included for HttpOnly session cookies
- CSRF token acquisition/refresh handled by the API client

Main workflow pages:

1. Dashboard / Revenue Command Center
2. Prospects
3. Lead 360
4. Actions
5. Opportunity Pipeline
6. Forecast
7. Leadership Analytics
8. Admin Center (permission-gated)

## Backend

- FastAPI
- SQLAlchemy 2
- Alembic
- PostgreSQL production; SQLite test/demo
- object-level authorization and recursive reporting hierarchy
- field-level permissions
- explicit record sharing
- opportunity teams / Presales collaboration
- corporate-currency FX normalization
- workflow notifications
- business + security audit
- Microsoft Graph integration foundation
- OpenTelemetry hooks + metrics / health endpoints

## Data flow

```text
React form
  -> /api mutation
  -> CSRF + session validation
  -> permission + record-scope validation
  -> CRM business rule validation
  -> transaction / database
  -> audit / notification
  -> JSON response
  -> React refreshes live state
```

No primary CRM screen depends on hard-coded static HTML data.
