# PursuitNova v6.0 Release Notes

## Why v6 exists

v5.2 had real backend logic but the handover frontend was a vanilla static JavaScript shell. v6 corrects that packaging and engineering gap.

## v6 changes

- replaced static shell with React/Vite SPA
- modular components and feature pages
- live API login/session/CSRF handling
- route-level code splitting
- server-driven Dashboard charts
- real Prospect list with pagination/filtering/saved views
- real Prospect creation with existing Company reuse
- Lead 360 workflow mutations
- Action workflow page
- Opportunity Kanban + list and detail controls
- Forecast charts and target management
- Leadership quarterly/half-year analytics
- Admin hierarchy / Microsoft status / monitoring view
- multi-stage production Docker build
- PostgreSQL docker-compose development path
- Railway deployment manifest
- v6 seller-workflow contract test

## Known production gates

Corporate SSO, live Microsoft tenant integration, live Postgres load testing, centralized observability backend, independent penetration test and formal UAT remain environment-specific release gates.
