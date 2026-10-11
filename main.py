import logging
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    Base,
    engine,
    ensure_google_auth_columns,
    ensure_reminder_calendar_columns,
    ensure_task_columns,
)
from app.ai_planner import generate_gemini_plan
from app.google_calendar import (
    begin_google_oauth,
    calendar_is_configured,
    delete_google_calendar_event,
    finish_google_oauth,
    sync_reminder_to_google_calendar,
)
from app.google_auth import (
    begin_google_login,
    complete_google_login,
    google_login_is_configured,
)
from app.dependencies import get_db
from app.models import GoogleCalendarConnection, GoogleLoginHandoff, User
from app.schemas import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalExecutionResponse,
    ApprovalPreview,
    ApprovalResponse,
    AssistantRequest,
    AIPlanCommitRequest,
    AIPlanGenerateRequest,
    AIPlanResponse,
    AIPlanTask,
    GoogleLoginExchangeRequest,
    LoginResponse,
    ReminderCreate,
    ReminderResponse,
    ReminderUpdate,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
    UserRegister,
    UserResponse,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.security import hash_password, verify_password
from app.tokens import create_access_token, decode_access_token

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from app.assistant_engine import interpret_command


bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_task_columns()
    ensure_reminder_calendar_columns()
    ensure_google_auth_columns()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend engine for Garuda Ops",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Garuda Ops backend is running!"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


def _validate_future_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must include a timezone.",
        )
    if value <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be in the future.",
        )
    return value.astimezone(timezone.utc)


def _parse_plan_deadline(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None
    try:
        deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task deadline must be a valid ISO 8601 date-time.",
        )
    if deadline.tzinfo is None or deadline.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task deadlines must include a timezone offset.",
        )
    _validate_future_datetime(deadline, "Task deadline")
    return deadline.astimezone(timezone.utc)


@app.post(
    "/api/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    return user


@app.post("/api/auth/login", response_model=LoginResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form.username.lower()
    user = db.scalar(select(User).where(User.email == email))

    if (
        user is None
        or user.password_hash is None
        or not verify_password(form.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return LoginResponse(
        access_token=create_access_token(user.id),
        expires_in=1800,
    )


@app.post("/api/auth/google")
def start_google_login():
    if not google_login_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.",
        )
    try:
        return {"authorization_url": begin_google_login()}
    except Exception as error:
        logger.exception("Could not start Google sign-in.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not available right now.",
        ) from error


@app.get("/api/auth/google/callback")
def google_login_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    outcome = "failed"
    if error == "access_denied":
        outcome = "cancelled"
    elif not error and code and state:
        try:
            user = complete_google_login(
                callback_url=str(request.url),
                state=state,
                db=db,
            )
            now = datetime.now(timezone.utc)
            db.execute(
                delete(GoogleLoginHandoff).where(
                    GoogleLoginHandoff.expires_at <= now
                )
            )
            handoff_code = secrets.token_urlsafe(32)
            db.add(
                GoogleLoginHandoff(
                    user_id=user.id,
                    code_hash=hashlib.sha256(
                        handoff_code.encode("utf-8")
                    ).hexdigest(),
                    expires_at=now + timedelta(minutes=2),
                )
            )
            db.commit()
            outcome = handoff_code
        except Exception as callback_error:
            db.rollback()
            logger.warning(
                "Google sign-in callback failed (%s).",
                type(callback_error).__name__,
            )

    if outcome in {"failed", "cancelled"}:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}?google_auth={outcome}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        url=(
            f"{settings.FRONTEND_URL.rstrip('/')}#google_auth_code="
            f"{outcome}"
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/api/auth/google/exchange", response_model=LoginResponse)
def exchange_google_login_code(
    payload: GoogleLoginExchangeRequest,
    db: Session = Depends(get_db),
):
    code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    handoff = db.scalar(
        select(GoogleLoginHandoff)
        .where(
            GoogleLoginHandoff.code_hash == code_hash,
            GoogleLoginHandoff.expires_at > now,
        )
        .with_for_update()
    )
    if handoff is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in code expired or already used. Please try again.",
        )

    user_id = handoff.user_id
    db.delete(handoff)
    db.commit()
    if db.get(User, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account is no longer available.",
        )
    return LoginResponse(access_token=create_access_token(user_id))


@app.get("/api/auth/me", response_model=UserResponse)
def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    return user


@app.get("/api/integrations/google-calendar/status")
def google_calendar_status(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    connection = db.scalar(
        select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.owner_id == user.id
        )
    )
    return {
        "configured": calendar_is_configured(),
        "connected": connection is not None,
    }


@app.post("/api/integrations/google-calendar/connect")
def connect_google_calendar(user: User = Depends(current_user)):
    if not calendar_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and "
                "GOOGLE_TOKEN_ENCRYPTION_KEY in the backend environment first."
            ),
        )
    try:
        return {"authorization_url": begin_google_oauth(user.id)}
    except Exception as error:
        logger.exception("Could not start Google Calendar authorization.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar could not be configured.",
        ) from error


@app.delete("/api/integrations/google-calendar")
def disconnect_google_calendar(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    connection = db.scalar(
        select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.owner_id == user.id
        )
    )
    if connection is not None:
        db.delete(connection)
        db.commit()
    return {"connected": False}


@app.get("/api/integrations/google-calendar/callback")
def google_calendar_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    result = "error"
    if not error and code and state:
        try:
            user_id = finish_google_oauth(
                callback_url=str(request.url),
                state=state,
                db=db,
            )
            if db.get(User, user_id) is not None:
                result = "connected"
            else:
                logger.warning("Google Calendar OAuth returned for a missing user.")
        except Exception:
            logger.exception("Google Calendar authorization callback failed.")
    elif error == "access_denied":
        result = "cancelled"

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}?google_calendar={result}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/api/tasks", response_model=list[TaskResponse])
def list_tasks(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    from app.models import Task

    return list(
        db.scalars(
            select(Task)
            .where(Task.owner_id == user_id)
            .order_by(Task.created_at.desc())
        ).all()
    )

@app.post(
    "/api/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    payload: TaskCreate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    from app.models import Task

    task = Task(
        owner_id=user_id,
        title=payload.title.strip(),
        description=payload.description,
        priority=payload.priority,
        due_at=(
            _validate_future_datetime(payload.due_at, "Task deadline")
            if payload.due_at is not None
            else None
        ),
    )

    if not task.title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task title cannot be blank.",
        )

    db.add(task)
    db.commit()
    db.refresh(task)

    return task

@app.patch("/api/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Task

    task = db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.owner_id == user_id,
        )
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    changes = payload.model_dump(exclude_unset=True)

    if "title" in changes:
        changes["title"] = changes["title"].strip()
        if not changes["title"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Task title cannot be blank.",
            )

    if changes.get("due_at") is not None:
        changes["due_at"] = _validate_future_datetime(
            changes["due_at"],
            "Task deadline",
        )

    for field, value in changes.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return task


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Task

    task = db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.owner_id == user_id,
        )
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    db.delete(task)
    db.commit()

@app.post(
    "/api/reminders",
    response_model=ReminderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reminder(
    payload: ReminderCreate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    remind_at = payload.remind_at
    if remind_at.tzinfo is None or remind_at.utcoffset() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="remind_at must include a timezone.",
        )

    if remind_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reminder time must be in the future.",
        )

    from app.models import Reminder

    reminder = Reminder(
        owner_id=user_id,
        title=payload.title.strip(),
        remind_at=remind_at,
    )

    if not reminder.title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reminder title cannot be blank.",
        )

    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    sync_reminder_to_google_calendar(db, reminder)
    db.refresh(reminder)

    return reminder


@app.get("/api/reminders", response_model=list[ReminderResponse])
def list_reminders(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Reminder

    return list(
        db.scalars(
            select(Reminder)
            .where(Reminder.owner_id == user_id)
            .order_by(Reminder.remind_at.asc())
        ).all()
    )

@app.patch("/api/reminders/{reminder_id}", response_model=ReminderResponse)
def update_reminder(
    reminder_id: int,
    payload: ReminderUpdate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Reminder

    reminder = db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.owner_id == user_id,
        )
    )

    if reminder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder not found.",
        )

    changes = payload.model_dump(exclude_unset=True)

    if "title" in changes:
        title = changes["title"].strip() if changes["title"] else ""
        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reminder title cannot be blank.",
            )
        changes["title"] = title

    if "remind_at" in changes:
        remind_at = changes["remind_at"]
        if (
            remind_at is None
            or remind_at.tzinfo is None
            or remind_at.utcoffset() is None
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="remind_at must include a timezone.",
            )
        if remind_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reminder time must be in the future.",
            )

    for field, value in changes.items():
        setattr(reminder, field, value)

    db.commit()
    db.refresh(reminder)
    sync_reminder_to_google_calendar(db, reminder)
    db.refresh(reminder)

    return reminder


@app.post("/api/reminders/{reminder_id}/sync", response_model=ReminderResponse)
def sync_reminder(
    reminder_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    from app.models import Reminder

    reminder = db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.owner_id == user.id,
        )
    )
    if reminder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder not found.",
        )
    sync_reminder_to_google_calendar(db, reminder)
    db.refresh(reminder)
    return reminder


@app.delete(
    "/api/reminders/{reminder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_reminder(
    reminder_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Reminder

    reminder = db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.owner_id == user_id,
        )
    )

    if reminder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reminder not found.",
        )

    delete_google_calendar_event(db, user_id, reminder.google_event_id)
    db.delete(reminder)
    db.commit()

@app.post(
    "/api/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow(
    payload: WorkflowCreate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workflow name cannot be blank.",
        )

    from app.models import Workflow

    workflow = Workflow(
        owner_id=user_id,
        name=name,
        description=payload.description,
    )

    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    return workflow


@app.get("/api/workflows", response_model=list[WorkflowResponse])
def list_workflows(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Workflow

    return list(
        db.scalars(
            select(Workflow)
            .where(Workflow.owner_id == user_id)
            .order_by(Workflow.created_at.desc())
        ).all()
    )

@app.patch("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Workflow

    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.owner_id == user_id,
        )
    )

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found.",
        )

    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes:
        name = changes["name"].strip() if changes["name"] else ""
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Workflow name cannot be blank.",
            )
        changes["name"] = name

    for field, value in changes.items():
        setattr(workflow, field, value)

    db.commit()
    db.refresh(workflow)

    return workflow

@app.delete(
    "/api/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_workflow(
    workflow_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Workflow

    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.owner_id == user_id,
        )
    )

    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found.",
        )

    db.delete(workflow)
    db.commit()

import json

@app.post(
    "/api/approvals",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_approval(
    payload: ApprovalCreate,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    action_data = payload.payload

    if payload.action_type == "send_email":
        required = {"to", "subject", "body"}
        if not required.issubset(action_data):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email payload requires to, subject, and body.",
            )
        if not all(
            isinstance(action_data[key], str) and action_data[key].strip()
            for key in required
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email fields must be non-empty strings.",
            )

    elif payload.action_type == "create_calendar_event":
        required = {"title", "start", "end"}
        if not required.issubset(action_data):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Calendar payload requires title, start, and end.",
            )
        if not all(
            isinstance(action_data[key], str) and action_data[key].strip()
            for key in required
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Calendar fields must be non-empty strings.",
            )

    from app.models import Approval

    approval = Approval(
        owner_id=user_id,
        action_type=payload.action_type,
        payload_json=json.dumps(action_data),
        status="pending",
    )

    db.add(approval)
    db.commit()
    db.refresh(approval)

    return approval

@app.get("/api/approvals", response_model=list[ApprovalResponse])
def list_approvals(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Approval

    return list(
        db.scalars(
            select(Approval)
            .where(Approval.owner_id == user_id)
            .order_by(Approval.created_at.desc())
        ).all()
    )

@app.patch("/api/approvals/{approval_id}", response_model=ApprovalResponse)
def decide_approval(
    approval_id: int,
    payload: ApprovalDecision,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Approval

    approval = db.scalar(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.owner_id == user_id,
        )
    )

    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found.",
        )

    if approval.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This approval has already been decided.",
        )

    approval.status = payload.decision
    db.commit()
    db.refresh(approval)

    return approval

@app.get("/api/approvals/{approval_id}/preview", response_model=ApprovalPreview)
def preview_approval(
    approval_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Approval

    approval = db.scalar(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.owner_id == user_id,
        )
    )

    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found.",
        )

    try:
        action_payload = json.loads(approval.payload_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored approval payload is invalid.",
        )

    return ApprovalPreview(
        id=approval.id,
        action_type=approval.action_type,
        payload=action_payload,
        status=approval.status,
        created_at=approval.created_at,
    )

@app.post("/api/ai/plan", response_model=AIPlanResponse)
def generate_ai_plan(
    request: AIPlanGenerateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=401, detail="User not found.")

    try:
        user_timezone = ZoneInfo(request.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid IANA timezone is required.",
        )

    current_time = datetime.now(user_timezone)
    if settings.GEMINI_API_KEY:
        try:
            generated = generate_gemini_plan(
                api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_MODEL,
                goal=request.goal,
                current_time=current_time,
                timezone_name=request.timezone,
            )
            validated_tasks = []
            for task in generated.tasks:
                due_at = _parse_plan_deadline(task.due_at)
                validated_tasks.append(
                    task.model_copy(
                        update={"due_at": due_at.isoformat() if due_at else None}
                    )
                )
            return AIPlanResponse(
                goal=request.goal,
                timezone=request.timezone,
                provider="gemini",
                message="Gemini prepared a plan. Review it before saving tasks.",
                tasks=validated_tasks,
            )
        except Exception as error:
            logger.warning(
                "Gemini plan generation failed for model %s (%s): %s; "
                "using deterministic fallback.",
                settings.GEMINI_MODEL,
                type(error).__name__,
                error,
                exc_info=True,
            )

    fallback = interpret_command(f"create task: {request.goal}")
    title = fallback.get("parameters", {}).get("title", request.goal).strip()[:200]
    fallback_task = AIPlanTask(
        title=title,
        description="Review this goal and split it into smaller steps.",
        priority="medium",
        due_at=None,
    )
    return AIPlanResponse(
        goal=request.goal,
        timezone=request.timezone,
        provider="deterministic",
        message=(
            "Gemini is unavailable. The deterministic command interpreter "
            "created a simple draft without an inferred deadline. Review it "
            "and add dates before saving if needed."
        ),
        tasks=[fallback_task],
    )


@app.post(
    "/api/ai/plan/confirm",
    response_model=list[TaskResponse],
    status_code=status.HTTP_201_CREATED,
)
def save_ai_plan(
    request: AIPlanCommitRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=401, detail="User not found.")

    try:
        ZoneInfo(request.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid IANA timezone is required.",
        )

    from app.models import Task

    tasks = [
        Task(
            owner_id=user_id,
            title=proposed.title,
            description=proposed.description,
            priority=proposed.priority,
            due_at=_parse_plan_deadline(proposed.due_at),
        )
        for proposed in request.tasks
    ]
    db.add_all(tasks)
    db.commit()
    for task in tasks:
        db.refresh(task)
    return tasks


@app.post("/api/assistant")
def assistant(
    payload: AssistantRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    
    result = interpret_command(payload.message)

    if result["intent"] == "list_tasks":
        from app.models import Task

        tasks = db.scalars(
            select(Task)
            .where(Task.owner_id == user_id)
            .order_by(Task.created_at.desc())
        ).all()

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "data": [
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "status": task.status,
                    "created_at": task.created_at,
                }
                for task in tasks
            ],
        }

    
    if result["intent"] == "list_pending_tasks":
        from app.models import Task

        tasks = db.scalars(
            select(Task)
            .where(
                Task.owner_id == user_id,
                Task.status == "pending",
            )
            .order_by(Task.created_at.desc())
        ).all()

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "data": [
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "status": task.status,
                }
                for task in tasks
            ],
        }

    
    if result["intent"] == "list_reminders":
        from app.models import Reminder

        reminders = db.scalars(
            select(Reminder)
            .where(Reminder.owner_id == user_id)
            .order_by(Reminder.remind_at.asc())
        ).all()

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "data": [
                {
                    "id": reminder.id,
                    "title": reminder.title,
                    "remind_at": reminder.remind_at,
                    "status": reminder.status,
                }
                for reminder in reminders
            ],
        }

    
    
    if result["intent"] == "create_reminder":
        from datetime import datetime, timezone
        from app.models import Reminder

        parameters = result["parameters"]

        if "remind_at" not in parameters:
            return {
                **result,
                "user_id": user_id,
                "engine": "deterministic",
                "message": (
                    "Please include a scheduled time, for example: "
                    "create reminder: Review demo at "
                    "2026-10-12T11:00+05:30"
                ),
                "needs_schedule": True,
            }

        try:
            remind_at = datetime.fromisoformat(
                parameters["remind_at"].replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid reminder date/time format.",
            )

        if remind_at.tzinfo is None or remind_at.utcoffset() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reminder time must include a timezone.",
            )

        if remind_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reminder time must be in the future.",
            )

        title = parameters["title"].strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reminder title cannot be blank.",
            )

        reminder = Reminder(
            owner_id=user_id,
            title=title,
            remind_at=remind_at,
        )
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        sync_reminder_to_google_calendar(db, reminder)
        db.refresh(reminder)

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "data": {
                "id": reminder.id,
                "title": reminder.title,
                "remind_at": reminder.remind_at,
                "status": reminder.status,
                "calendar_sync_status": reminder.calendar_sync_status,
            },
        }

    
    
    if result["intent"] == "propose_email":
        parameters = result.get("parameters", {})
        required = ("to", "subject", "body")

        if not all(
            isinstance(parameters.get(key), str)
            and parameters[key].strip()
            for key in required
        ):
            return {
                **result,
                "user_id": user_id,
                "engine": "deterministic",
                "message": (
                    "Please provide the recipient, subject, and body "
                    "using: send email to demo@example.com | "
                    "subject: Demo update | body: The demo is ready."
                ),
                "needs_details": list(required),
            }

        from app.models import Approval
        import json

        approval = Approval(
            owner_id=user_id,
            action_type="send_email",
            payload_json=json.dumps({
                "to": parameters["to"].strip(),
                "subject": parameters["subject"].strip(),
                "body": parameters["body"].strip(),
            }),
            status="pending",
        )

        db.add(approval)
        db.commit()
        db.refresh(approval)

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "message": "Email proposal created. Approval is required before sending.",
            "requires_approval": True,
            "data": {
                "approval_id": approval.id,
                "action_type": approval.action_type,
                "status": approval.status,
            },
        }

    
    if result["intent"] == "propose_calendar_event":
        from datetime import datetime
        from app.models import Approval
        import json

        parameters = result.get("parameters", {})
        required = ("title", "start", "end")

        if not all(
            isinstance(parameters.get(key), str)
            and parameters[key].strip()
            for key in required
        ):
            return {
                **result,
                "user_id": user_id,
                "engine": "deterministic",
                "message": (
                    "Please provide a title, start, and end time. "
                    "Example: create calendar event Team demo | "
                    "start: 2026-10-12T14:00+05:30 | "
                    "end: 2026-10-12T14:30+05:30"
                ),
                "needs_details": list(required),
            }

        try:
            start = datetime.fromisoformat(
                parameters["start"].replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(
                parameters["end"].replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid calendar date/time format.",
            )

        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Calendar times must include timezones.",
            )

        if end <= start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Event end time must be after its start time.",
            )

        approval = Approval(
            owner_id=user_id,
            action_type="create_calendar_event",
            payload_json=json.dumps({
                "title": parameters["title"].strip(),
                "start": start.isoformat(),
                "end": end.isoformat(),
            }),
            status="pending",
        )

        db.add(approval)
        db.commit()
        db.refresh(approval)

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "message": (
                "Calendar event proposal created. "
                "Approval is required before creating the event."
            ),
            "requires_approval": True,
            "data": {
                "approval_id": approval.id,
                "action_type": approval.action_type,
                "status": approval.status,
            },
        }



    
    if result["intent"] == "list_workflows":
        from app.models import Workflow

        workflows = db.scalars(
            select(Workflow)
            .where(Workflow.owner_id == user_id)
            .order_by(Workflow.created_at.desc())
        ).all()

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "data": [
                {
                    "id": workflow.id,
                    "name": workflow.name,
                    "description": workflow.description,
                    "status": workflow.status,
                    "created_at": workflow.created_at,
                }
                for workflow in workflows
            ],
        }
    
    if result["intent"] == "create_task":
        from app.models import Task

        title = result["parameters"]["title"].strip()

        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Task title cannot be blank.",
            )

        task = Task(
            owner_id=user_id,
            title=title,
            status="pending",
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "data": {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "status": task.status,
            },
        }

    
    if result["intent"] == "complete_task":
        from app.models import Task

        task_id = result["parameters"]["task_id"]

        task = db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.owner_id == user_id,
            )
        )

        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found.",
            )

        task.status = "completed"
        db.commit()
        db.refresh(task)

        return {
            **result,
            "user_id": user_id,
            "engine": "deterministic",
            "data": {
                "id": task.id,
                "title": task.title,
                "status": task.status,
            },
        }


    return {
        **result,
        "user_id": user_id,
        "engine": "deterministic",
    }


@app.post(
    "/api/approvals/{approval_id}/execute",
    response_model=ApprovalExecutionResponse,
)
def execute_approval(
    approval_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        user_id = int(token_payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    from app.models import Approval

    approval = db.scalar(
        select(Approval).where(
            Approval.id == approval_id,
            Approval.owner_id == user_id,
        )
    )

    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found.",
        )

    if approval.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved actions can be executed.",
        )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Action execution is not configured yet. "
            "Connect and configure the relevant integration first."
        ),
    )
