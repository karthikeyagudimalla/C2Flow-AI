# Deploy Tricity to Render

The root `render.yaml` defines a FastAPI service, the Vite frontend, and a
persistent PostgreSQL database. The API and database are placed in Singapore;
Render supplies the frontend URL, API URL, database connection string, and a
generated JWT secret.

## Deploy

1. Commit and push the project to the GitHub `main` branch. The root `.env` is
   ignored by Git; do not force-add it.
2. Sign in to [Render](https://dashboard.render.com/), choose **New → Blueprint**,
   connect `karthikeyagudimalla/C2Flow-AI`, and select `main`.
3. Review the resources and the database plan shown by Render, then create the
   Blueprint. The database uses Render's smallest persistent Postgres plan and
   incurs a recurring charge. The API and static frontend use the free plan.
4. Wait for both services to finish deploying. Open the frontend URL shown in
   Render and create an account.

The Google sign-in and Calendar integrations remain disabled until Google OAuth
credentials and production callback URLs are configured. Gemini planning also
uses the deterministic fallback until `GEMINI_API_KEY` is added to the API
service's environment. These optional credentials belong in Render's service
environment, never in this repository or the frontend.

## Enable Google integrations later

After Render assigns the API URL, set these API service variables using that
exact HTTPS URL:

```text
GOOGLE_AUTH_REDIRECT_URI=https://<api-host>/api/auth/google/callback
GOOGLE_REDIRECT_URI=https://<api-host>/api/integrations/google-calendar/callback
FRONTEND_URL=https://<frontend-host>
```

Add the matching callback URLs to the Google OAuth Web client, then add
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and a generated Fernet key as API
service secrets in Render. Set `GEMINI_API_KEY` there as well if Gemini planning
is needed. Each environment change requires a redeploy.
