# Tech Stack

## Frontend
- **Framework:** Next.js (App Router)
- **Language:** TypeScript
- **Styling:** TailwindCSS
- **State/Fetching:** React hooks, Axios
- **Icons:** Lucide React
- **Why:** Next.js provides excellent routing and component structuring. Tailwind allows for rapid, consistent UI development.

## Backend
- **Framework:** FastAPI
- **Language:** Python 3.11+
- **Data Manipulation:** Pandas (heavy reliance for aggregations and data frame JSON serialization)
- **Database Driver:** psycopg2
- **Why:** FastAPI is extremely fast and integrates perfectly with Python's data ecosystem (Pandas/NumPy) which is essential for the forecasting and variance calculations.

## Database
- **Engine:** PostgreSQL
- **Why:** Replaced ClickHouse for the main operational DB because Postgres handles relationships, updates, and transaction concurrency better for a web application backend.

## Data Pipeline
- **Scraping:** Playwright (Python)
- **API Requests:** `requests` module
- **Why:** SupplyNote lacks a clean REST API for bulk consumption data, so a headless browser (Playwright) was required to mimic user login and CSV downloads.

## Hosting & Infrastructure
- **Frontend Hosting:** Vercel (Auto-deploys from GitHub)
- **Backend Hosting:** Render (Free tier currently, **Manual deploy required**)
- **Authentication:** Supabase (Provides secure JWT-based auth without needing to manage user password hashing manually).
