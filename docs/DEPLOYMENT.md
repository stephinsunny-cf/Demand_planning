# Deployment Guide

## Frontend (Vercel)
- **Location:** https://demand-planning.vercel.app (Note: check Vercel dashboard for actual Next.js project URL if this points to a legacy Vite app).
- **Trigger:** Automatic. Pushing to the `main` branch triggers a build.
- **Troubleshooting:** If the live site looks stale but commits are showing in Vercel, the Next.js build is failing. Vercel silently serves the last successful build. Check Vercel build logs to fix the root cause (often a strict TypeScript error or OOM).

## Backend (Render)
- **Location:** https://demand-planning-8r9g.onrender.com
- **Trigger:** **MANUAL**. Pushing to GitHub does *not* automatically deploy the backend.
- **How to Deploy:** Log into the Render dashboard, go to the `demand-planning-8r9g` web service, click **Manual Deploy -> Deploy latest commit**.
- **Cold Starts:** Because it's on a free tier, Render spins down after 15 minutes of inactivity. The first request (like logging in) will take 30-60 seconds while the server wakes up.

## Database (PostgreSQL)
- **Location:** Hosted remotely (IP: ***REDACTED-DB-HOST***).
- **Migrations:** Managed via ad-hoc scripts (e.g., `pipeline/create_postgres_tables.py`).
