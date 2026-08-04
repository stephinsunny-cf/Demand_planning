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
```

## Frontend (`.env.local`)

```env
# Points to Render in production, localhost:8000 in dev
NEXT_PUBLIC_API_URL=https://<your-render-app>.onrender.com

# Supabase Auth for client-side login
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase-anon-key>
```
