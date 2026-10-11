import logging
from datetime import timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GoogleCalendarConnection, Reminder


logger = logging.getLogger(__name__)
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def calendar_is_configured() -> bool:
    configured = bool(
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.GOOGLE_TOKEN_ENCRYPTION_KEY
        and settings.JWT_SECRET
    )
    if not configured:
        return False
    try:
        _token_cipher()
    except (ValueError, UnicodeError):
        return False
    return True


def _client_config() -> dict:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Google Calendar OAuth credentials are not configured.")
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
        }
    }


def _token_cipher() -> Fernet:
    if not settings.GOOGLE_TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("Google Calendar token encryption is not configured.")
    return Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode("ascii"))


def _state_signer() -> URLSafeTimedSerializer:
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is required to secure Google OAuth state.")
    return URLSafeTimedSerializer(settings.JWT_SECRET, salt="google-calendar-oauth")


def begin_google_oauth(user_id: int) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=[CALENDAR_SCOPE])
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    signed_state = _state_signer().dumps({"user_id": user_id})
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=signed_state,
    )
    return authorization_url


def finish_google_oauth(*, callback_url: str, state: str, db: Session) -> int:
    try:
        state_payload = _state_signer().loads(state, max_age=600)
        user_id = int(state_payload["user_id"])
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError) as error:
        raise ValueError("Google Calendar authorization expired. Please try again.") from error

    flow = Flow.from_client_config(
        _client_config(),
        scopes=[CALENDAR_SCOPE],
        state=state,
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    flow.fetch_token(authorization_response=callback_url)
    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        existing = db.scalar(
            select(GoogleCalendarConnection).where(
                GoogleCalendarConnection.owner_id == user_id
            )
        )
        if existing is None:
            raise ValueError(
                "Google did not return a refresh token. Reconnect and grant offline access."
            )
        return user_id

    encrypted_token = _token_cipher().encrypt(refresh_token.encode("utf-8")).decode(
        "ascii"
    )
    connection = db.scalar(
        select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.owner_id == user_id
        )
    )
    if connection is None:
        connection = GoogleCalendarConnection(
            owner_id=user_id,
            encrypted_refresh_token=encrypted_token,
            calendar_id="primary",
        )
        db.add(connection)
    else:
        connection.encrypted_refresh_token = encrypted_token
    db.commit()
    return user_id


def _calendar_service(connection: GoogleCalendarConnection):
    try:
        refresh_token = _token_cipher().decrypt(
            connection.encrypted_refresh_token.encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as error:
        raise RuntimeError(
            "Saved Google Calendar credentials cannot be decrypted."
        ) from error

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=[CALENDAR_SCOPE],
    )
    credentials.refresh(GoogleRequest())
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _event_body(reminder: Reminder) -> dict:
    start = reminder.remind_at
    if start.tzinfo is None or start.utcoffset() is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = start + timedelta(minutes=15)
    return {
        "summary": reminder.title,
        "description": "Reminder created from C2Flow AI.",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 10}],
        },
    }


def _write_calendar_event(
    service,
    connection: GoogleCalendarConnection,
    reminder: Reminder,
) -> str:
    body = _event_body(reminder)
    if reminder.google_event_id:
        try:
            service.events().patch(
                calendarId=connection.calendar_id,
                eventId=reminder.google_event_id,
                body=body,
            ).execute()
            return reminder.google_event_id
        except HttpError as error:
            if error.resp.status != 404:
                raise

    event = service.events().insert(
        calendarId=connection.calendar_id,
        body=body,
    ).execute()
    return event["id"]


def sync_reminder_to_google_calendar(db: Session, reminder: Reminder) -> str:
    connection = db.scalar(
        select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.owner_id == reminder.owner_id
        )
    )
    if connection is None:
        reminder.calendar_sync_status = "not_connected"
        db.commit()
        return reminder.calendar_sync_status

    try:
        service = _calendar_service(connection)
        reminder.google_event_id = _write_calendar_event(service, connection, reminder)
        reminder.calendar_sync_status = "synced"
        db.commit()
    except Exception:
        db.rollback()
        reminder.calendar_sync_status = "failed"
        db.commit()
        logger.exception("Google Calendar sync failed for reminder %s.", reminder.id)
    return reminder.calendar_sync_status


def delete_google_calendar_event(
    db: Session,
    owner_id: int,
    event_id: str | None,
) -> None:
    if not event_id:
        return
    connection = db.scalar(
        select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.owner_id == owner_id
        )
    )
    if connection is None:
        return
    try:
        _calendar_service(connection).events().delete(
            calendarId=connection.calendar_id,
            eventId=event_id,
        ).execute()
    except HttpError as error:
        if error.resp.status != 404:
            logger.exception("Could not remove a Google Calendar reminder event.")
    except Exception:
        logger.exception("Could not remove a Google Calendar reminder event.")

