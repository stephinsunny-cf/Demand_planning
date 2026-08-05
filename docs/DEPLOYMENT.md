# Deployment Guide

## Frontend (Vercel)
- **Location:** https://cfi-demand-planning.vercel.app (confirmed live/correct — Aug 2026. `https://demand-planning.vercel.app` is a different/legacy project, do not use it as the reference URL).
- **Trigger:** Automatic. Pushing to the `main` branch triggers a build.
- **Required env var:** `NEXT_PUBLIC_API_URL` must point to the Render backend URL (`https://demand-planning-8r9g.onrender.com`), set in the Vercel project's Environment Variables — **not** in a local `.env.local`, which is gitignored and never reaches Vercel's build. `NEXT_PUBLIC_*` vars are baked in at build time, so changing this value requires a redeploy to take effect.
- **Troubleshooting:** If the live site looks stale but commits are showing in Vercel, the Next.js build is failing. Vercel silently serves the last successful build. Check Vercel build logs to fix the root cause (often a strict TypeScript error or OOM).

## Backend (Render)
- **Location:** https://demand-planning-8r9g.onrender.com
- **Trigger:** Automatic — Auto-Deploy is set to **"After CI Checks Pass"** (Render Settings → Deploy). Every push to `main` runs `.github/workflows/ci.yml` (clean install of `requirements.txt` + import check on `backend.main:app`) first; Render only deploys if that check goes green. This replaced the old fully-manual process (Aug 2026) after a stale/broken deploy caused a production outage.
- **Manual override:** Still available if needed — Render dashboard → `demand-planning-8r9g` → **Manual Deploy -> Deploy latest commit**.
- **Required env var:** `APP_URL` must be set to the production frontend URL (`https://cfi-demand-planning.vercel.app`). This is used to build Supabase invite/reset-password redirect links (`backend/routers/admin.py`) — if unset, it silently falls back to `http://localhost:3000` and invited users get a link they can't open.
- **Cold Starts:** Running on the free tier by choice (Aug 2026 decision — not upgrading). Render spins down after 15 minutes of inactivity; the first request after idle (e.g. login) can take 50+ seconds while the server wakes up. This is expected behavior, not a bug.

## Database (PostgreSQL)
- **Location:** Hosted remotely (IP: ***REDACTED-DB-HOST***).
- **Migrations:** Managed via ad-hoc scripts (e.g., `pipeline/create_postgres_tables.py`).
