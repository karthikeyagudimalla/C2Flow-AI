import secrets

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User


GOOGLE_IDENTITY_SCOPES = ["openid", "email"]


def google_login_is_configured() -> bool:
    return bool(
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.JWT_SECRET
    )


def _state_signer() -> URLSafeTimedSerializer:
    if not google_login_is_configured():
        raise RuntimeError("Google sign-in is not configured.")
    return URLSafeTimedSerializer(settings.JWT_SECRET, salt="google-login-oauth")


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_AUTH_REDIRECT_URI],
        }
    }


def begin_google_login() -> str:
    flow = Flow.from_client_config(
        _client_config(),
        scopes=GOOGLE_IDENTITY_SCOPES,
    )
    flow.redirect_uri = settings.GOOGLE_AUTH_REDIRECT_URI
    nonce = secrets.token_urlsafe(24)
    state = _state_signer().dumps({"nonce": nonce})
    authorization_url, _ = flow.authorization_url(
        access_type="online",
        include_granted_scopes="true",
        prompt="select_account",
        nonce=nonce,
        state=state,
    )
    return authorization_url


def complete_google_login(*, callback_url: str, state: str, db: Session) -> User:
    try:
        state_payload = _state_signer().loads(state, max_age=600)
    except (BadSignature, SignatureExpired) as error:
        raise ValueError("Google sign-in expired. Please try again.") from error

    flow = Flow.from_client_config(
        _client_config(),
        scopes=GOOGLE_IDENTITY_SCOPES,
        state=state,
    )
    flow.redirect_uri = settings.GOOGLE_AUTH_REDIRECT_URI
    flow.fetch_token(authorization_response=callback_url)
    if not flow.credentials.id_token:
        raise ValueError("Google did not return a verified identity token.")

    claims = id_token.verify_oauth2_token(
        flow.credentials.id_token,
        GoogleRequest(),
        settings.GOOGLE_CLIENT_ID,
    )
    google_sub = claims.get("sub")
    email = claims.get("email")
    if (
        not isinstance(google_sub, str)
        or not google_sub
        or not isinstance(email, str)
        or not email
        or claims.get("email_verified") is not True
        or claims.get("nonce") != state_payload.get("nonce")
    ):
        raise ValueError("Google must provide a verified email address to continue.")

    email = email.strip().lower()
    user = db.scalar(select(User).where(User.google_sub == google_sub))
    if user is not None:
        return user

    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        if user.google_sub and user.google_sub != google_sub:
            raise ValueError(
                "This email is already linked to a different Google account."
            )
        user.google_sub = google_sub
    else:
        user = User(email=email, password_hash=None, google_sub=google_sub)
        db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        user = db.scalar(select(User).where(User.google_sub == google_sub))
        if user is None:
            raise ValueError("Could not create this Google account. Please retry.")
    return user
