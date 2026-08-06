# Environment Variables

These environment variables must be present in `.env` (backend) and `.env.local` (frontend).

> ⚠️ **Never put real credentials in this file.** Use placeholder values only.  
> Ask an admin for actual values, or retrieve them from the secure secrets store.

## Backend (`.env`)

```env
# PostgreSQL (Production DB)
PG_HOST=<your-db-host>
PG_PORT=5432
PG_USER=<your-db-user>
PG_PASS=<your-db-password>
PG_DB=demand_planning

# Supabase Auth
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_KEY=<supabase-anon-public-key>
SUPABASE_SERVICE_ROLE_KEY=<supabase-service-role-secret-key>

# Data Pipeline Credentials
SUPPLYNOTE_USER=<supplynote-username>
SUPPLYNOTE_PASSWORD=<supplynote-password>
METABASE_URL=https://<your-metabase-host>
METABASE_API_KEY=<metabase-api-key>

# App Settings
USE_DUMMY_DATA=false
DEMO_MODE=true
LOG_LEVEL=INFO
TZ=Asia/Kolkata

# Public URL of the deployed frontend (Vercel). Used to build Supabase
# invite / password-reset redirect links in backend/routers/admin.py.
# If this is missing, it silently defaults to http://localhost:3000 and
# invited users receive a link only reachable from the dev machine.
# In production this must be set in the Render dashboard's Environment
# tab (not just here) — currently: https://cfi-demand-planning.vercel.app
APP_URL=https://<your-frontend-domain>

# Interactive API docs (/docs, /redoc, /openapi.json) are OFF by default in
# production (2026-08-06 — they were previously public, exposing the full
# API surface with no auth). Set this to "true" temporarily — in the Render
# dashboard's Environment tab, not here — when someone genuinely needs to
# browse them (onboarding a new developer, debugging an integration), then
# set it back to unset/false afterward. Locally you don't need this: running
# `uvicorn backend.main:app --reload` and only leaving it unset still means
# nobody outside your own machine can reach localhost:8000/docs anyway.
ENABLE_API_DOCS=false

# Comma-separated list of origins allowed to call this API from a browser
# (CORS). Defaults to the real frontend + localhost if unset — only add to
# this (in the Render dashboard, not here) if another origin genuinely needs
# access, e.g. a specific Vercel preview-deployment URL. Never set this to
# "*" as a shortcut.
ALLOWED_ORIGINS=https://cfi-demand-planning.vercel.app,http://localhost:3000
```

## Frontend (`.env.local`)

```env
# Points to Render in production, localhost:8000 in dev.
# NEXT_PUBLIC_* vars are inlined at Next.js BUILD time, so this file is
# only used for local dev — production value must be set directly in the
# Vercel project's Environment Variables (Settings > Environment Variables),
# followed by a redeploy for the change to take effect.
NEXT_PUBLIC_API_URL=https://<your-render-app>.onrender.com

# Supabase Auth for client-side login
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
# NOTE: the code reads NEXT_PUBLIC_SUPABASE_KEY (see frontend/src/lib/supabase.ts),
# not NEXT_PUBLIC_SUPABASE_ANON_KEY. Use this exact name or auth silently
# falls back to a dummy key.
NEXT_PUBLIC_SUPABASE_KEY=<supabase-anon-key>
```
