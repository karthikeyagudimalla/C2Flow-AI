
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from datetime import datetime
from typing import Literal

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(
        default=None,
        pattern="^(pending|in_progress|completed|cancelled)$",
    )
    priority: str | None = Field(default=None, pattern="^(low|medium|high)$")
    due_at: datetime | None = None


class TaskResponse(BaseModel):
    id: int
    owner_id: int
    title: str
    description: str | None
    status: str
    priority: str
    due_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

from datetime import datetime, timezone

class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    remind_at: datetime


class ReminderResponse(BaseModel):
    id: int
    owner_id: int
    title: str
    remind_at: datetime
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    remind_at: datetime | None = None

class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(default=None, pattern="^(draft|active|paused|completed)$")


class WorkflowResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    description: str | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalCreate(BaseModel):
    action_type: Literal[
        "send_email",
        "create_calendar_event",
    ]
    payload: dict


class ApprovalResponse(BaseModel):
    id: int
    owner_id: int
    action_type: str
    payload_json: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]

class ApprovalPreview(BaseModel):
    id: int
    action_type: str
    payload: dict
    status: str
    created_at: datetime

class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AIPlanTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    priority: Literal["low", "medium", "high"] = "medium"
    due_at: str | None = Field(
        default=None,
        description=(
            "ISO 8601 date-time with a timezone offset, or null if the goal "
            "does not imply a deadline."
        ),
    )

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Task title cannot be blank.")
        return title

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        description = value.strip()
        return description or None


class AIPlanGenerateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        goal = value.strip()
        if not goal:
            raise ValueError("Describe a goal to generate a plan.")
        return goal


class AIPlanCommitRequest(AIPlanGenerateRequest):
    tasks: list[AIPlanTask] = Field(min_length=1, max_length=12)


class AIPlanResponse(BaseModel):
    goal: str
    timezone: str
    provider: Literal["gemini", "deterministic"]
    message: str
    tasks: list[AIPlanTask]

class ApprovalExecutionResponse(BaseModel):
    approval_id: int
    status: str
    message: str
