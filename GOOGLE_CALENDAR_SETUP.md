# Google account and Calendar setup

Google OAuth powers both account sign-in and the optional Calendar connection.
Google-only users are matched by Google's stable account ID, and a verified
Google email can link an existing C2Flow account. Calendar refresh tokens are
encrypted before storage. The frontend never receives Google credentials.

## Google Cloud setup

1. Create or select a project in Google Cloud Console.
2. Enable the **Google Calendar API** for that project.
3. Configure the OAuth consent screen. While the app is in testing, add the
   Google accounts that will connect as test users.
4. Create an OAuth client with application type **Web application**.
5. Add both authorized redirect URIs:

   ```text
   http://127.0.0.1:8000/api/auth/google/callback
   http://127.0.0.1:8000/api/integrations/google-calendar/callback
   ```

6. Copy the OAuth client ID and client secret into the backend `.env` file.

Google's [web server OAuth guide](https://developers.google.com/identity/protocols/oauth2/web-server)
has the current console steps. Account login asks only for OpenID and email.
Calendar event creation uses the
[`calendar.events` scope](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).

## Backend environment

Copy `.env.example` to `.env` if needed, then set:

```dotenv
GOOGLE_CLIENT_ID=your-oauth-client-id
GOOGLE_CLIENT_SECRET=your-oauth-client-secret
GOOGLE_AUTH_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/integrations/google-calendar/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=generated-fernet-key
FRONTEND_URL=http://localhost:5173
```

Generate a Fernet encryption key after installing the requirements:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep the generated key stable. If it is lost or changed, saved Google refresh
tokens can no longer be decrypted and users need to connect again.

Install dependencies and restart the API:

```powershell
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Sign in and connect Calendar

Choose **Continue with Google** on the C2Flow sign-in page to sign in or create
an account. To also sync reminders, open **Settings** after sign-in and choose
**Connect Google Calendar**. Newly created or edited reminders are synchronized
to the connected user's primary calendar as 15-minute events with a 10-minute
popup reminder. Failed syncs stay visible in the Reminders page and can be
retried.
