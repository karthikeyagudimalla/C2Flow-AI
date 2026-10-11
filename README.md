# C2Flow AI

C2Flow AI is a task and workflow planning app with a React frontend and a Python FastAPI backend. It supports account registration and sign-in, tasks and reminders, AI-assisted plan proposals, and optional Google sign-in and Calendar sync.

## Project structure

```text
.
├── app/                    # FastAPI configuration, database models, and integrations
├── frontend/C2Flow-ai/      # React + Vite web application
├── tests/                  # Backend tests
├── main.py                 # FastAPI application and API routes
├── requirements.txt        # Python dependencies
├── .env.example            # Backend environment variable template
├── DEPLOYMENT.md           # Vercel + Neon deployment guide
└── GOOGLE_CALENDAR_SETUP.md
```

## Requirements

- Python 3.12
- Node.js and npm
- A PostgreSQL database (Neon works for local development and deployment)

## Run locally

### 1. Configure the backend

From the repository root, create a virtual environment and install the Python dependencies:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then set at least:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
JWT_SECRET=replace-with-a-long-random-secret
```

Generate a secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Keep `.env` and all credentials private. Do not commit them or put backend secrets in frontend variables. Start the API:

```powershell
uvicorn main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation is at `http://127.0.0.1:8000/docs`; the health endpoint is `http://127.0.0.1:8000/health`.

### 2. Configure and run the frontend

In a second terminal:

```powershell
cd frontend/C2Flow-ai
npm ci
```

Copy `frontend/C2Flow-ai/.env.example` to `frontend/C2Flow-ai/.env`, and set the API URL:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Run the Vite development server:

```powershell
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). The backend's `CORS_ORIGINS` setting must include that exact origin; the example backend configuration already allows `http://localhost:5173`.

## Optional integrations

The core app can run without these integrations:

- **Gemini planning:** set `GEMINI_API_KEY` in the backend `.env`. If Gemini is unavailable, plan generation falls back to the deterministic interpreter.
- **Google sign-in:** configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_AUTH_REDIRECT_URI` on the backend.
- **Google Calendar sync:** configure the Google OAuth credentials, `GOOGLE_REDIRECT_URI`, and `GOOGLE_TOKEN_ENCRYPTION_KEY` on the backend. Follow [Google Calendar setup](GOOGLE_CALENDAR_SETUP.md).

Never prefix server credentials with `VITE_`; Vite exposes `VITE_*` values to browser code. Only the non-secret API base URL belongs in the frontend environment.

## Deployment

The repository is configured for a separately deployed Vercel frontend and FastAPI backend with a Neon PostgreSQL database. Follow [DEPLOYMENT.md](DEPLOYMENT.md) for project root directories and environment variables. The frontend needs `VITE_API_BASE_URL` set to the deployed API origin. The backend needs `FRONTEND_URL` and `CORS_ORIGINS` set to the deployed frontend origin.

Production uses its own database. Accounts created in a local development database do not automatically exist in production; register again on the deployed app or migrate the data deliberately.

## Main API areas

- `/api/auth/*` — email/password and Google authentication
- `/api/tasks` — task management
- `/api/reminders` — reminders and optional Calendar synchronization
- `/api/workflows` — workflow management
- `/api/ai/plan` — generate and commit reviewed AI task plans
- `/api/assistant` — deterministic natural-language command handling

Open `/docs` on the running backend for the full route list and request schemas.

## Tests

Run the backend test suite from the repository root:

```powershell
python -m pytest
```
