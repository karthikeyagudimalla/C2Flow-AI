# Free-tier deployment: Vercel + Neon

Deploy the frontend and API as separate Vercel projects from this GitHub
repository, and use a Neon Free PostgreSQL database. Vercel's Python runtime
supports FastAPI but is currently in Beta. Neon Free has usage limits; review
the current limits before storing important data.

## 1. Create the database

1. Create a project at [Neon](https://console.neon.tech/).
2. Choose a region near the Vercel function region (for India, Mumbai or
   Singapore if available).
3. In **Connect**, select the pooled connection string and copy it. Keep it
   private; it contains the database password.

## 2. Deploy the FastAPI backend

1. In [Vercel](https://vercel.com/new), import
   `karthikeyagudimalla/C2Flow-AI` from GitHub.
2. Create a project named `tricity-api`. Set **Root Directory** to `.` (the
   repository root). Vercel detects `main.py` and `requirements.txt` and
   deploys the FastAPI `app` as a Python Function.
3. Add these environment variables for **Production** before deploying:

   ```text
   DATABASE_URL=<Neon pooled connection string>
   JWT_SECRET=<a long random secret>
   ENVIRONMENT=production
   FRONTEND_URL=https://<your-frontend-project>.vercel.app
   CORS_ORIGINS=https://<your-frontend-project>.vercel.app
   ```

   Generate `JWT_SECRET` locally with:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

4. Deploy and copy the backend's `https://...vercel.app` URL.

## 3. Deploy the frontend

1. Import the same GitHub repository again in Vercel as a second project named
   `tricity-frontend`.
2. Set **Root Directory** to `frontend/C2Flow-ai`. Use the defaults for Vite:
   build command `npm run build`, output directory `dist`.
3. Set this Production environment variable before deploying:

   ```text
   VITE_API_BASE_URL=https://<your-api-project>.vercel.app
   ```

4. Deploy. If Vercel assigned a different frontend URL than the one entered in
   the backend settings, update the backend's `FRONTEND_URL` and `CORS_ORIGINS`
   to the exact frontend origin, then redeploy the backend.

## Optional integrations

The app works without these credentials. Gemini uses the deterministic
interpreter until `GEMINI_API_KEY` is added to the backend project. Google
sign-in and Calendar sync stay disabled until Google OAuth is configured.
After the API and frontend URLs are known, use these exact callback URLs in the
Google OAuth Web client:

```text
https://<your-api-project>.vercel.app/api/auth/google/callback
https://<your-api-project>.vercel.app/api/integrations/google-calendar/callback
```

Add Google credentials and `GOOGLE_TOKEN_ENCRYPTION_KEY` only as backend
environment variables in Vercel. Do not put server secrets in `VITE_*` variables
or commit them to the repository.
