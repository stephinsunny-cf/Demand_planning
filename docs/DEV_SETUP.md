# Local Development Setup

## Prerequisites
- Node.js (v18+)
- Python (3.11+)
- Git

## 1. Environment Variables
You need two environment files. Ask an admin for the actual credentials.

**Backend:** Create `.env` in the root `d:\demand-planning\` directory.
**Frontend:** Create `.env.local` in `d:\demand-planning\frontend\`.

## 2. Running the Backend
1. Open a terminal in the root directory.
2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI server:
   ```bash
   uvicorn backend.main:app --reload
   ```
   The backend will run on `http://localhost:8000`.

## 3. Running the Frontend
1. Open a new terminal and navigate to the frontend:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
   The frontend will run on `http://localhost:3000`.

## 4. Testing
- Go to `http://localhost:3000/login` and log in with your Supabase credentials.
- The local frontend will communicate with your local backend, which will query the live remote PostgreSQL database.
