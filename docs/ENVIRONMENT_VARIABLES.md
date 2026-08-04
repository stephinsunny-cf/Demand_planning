# Environment Variables

These environment variables must be present in `.env` (backend) and `.env.local` (frontend).

## Backend (`.env`)

```env
# PostgreSQL (Production DB)
PG_HOST=***REDACTED-DB-HOST***
PG_PORT=5432
PG_USER=new_user
PG_PASS=***REDACTED-DB-PASSWORD***
PG_DB=demand_planning

# Supabase Auth
SUPABASE_URL=https://***REDACTED-SUPABASE-PROJECT-REF***.supabase.co
SUPABASE_KEY=eyJhbG... (anon public key)
SUPABASE_SERVICE_ROLE_KEY=eyJhbG... (secret key for admin actions)

# Data Pipeline Credentials
SUPPLYNOTE_USER=stephin_sunny
SUPPLYNOTE_PASSWORD=***REDACTED-SUPPLYNOTE-PASSWORD***
METABASE_URL=https://clickhouse.eatfit.in
METABASE_API_KEY=mb_UdeamMfmq5sx...

# App Settings
USE_DUMMY_DATA=false
DEMO_MODE=true
LOG_LEVEL=INFO
TZ=Asia/Kolkata
```

## Frontend (`.env.local`)

```env
# Points to Render in production, localhost:8000 in dev
NEXT_PUBLIC_API_URL=https://demand-planning-8r9g.onrender.com

# Supabase Auth for client-side login
NEXT_PUBLIC_SUPABASE_URL=https://***REDACTED-SUPABASE-PROJECT-REF***.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbG...
```
