
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime
from pydantic import Field

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


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(
        default=None,
        pattern="^(pending|in_progress|completed|cancelled)$",
    )


class TaskResponse(BaseModel):
    id: int
    owner_id: int
    title: str
    description: str | None
    status: str
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


from typing import Literal

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

class ApprovalExecutionResponse(BaseModel):
    approval_id: int
    status: str
    message: str
