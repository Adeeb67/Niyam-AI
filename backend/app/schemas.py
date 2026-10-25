import re

from pydantic import BaseModel, Field, field_validator


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def clean_email(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class BootstrapIn(BaseModel):
    secret: str = Field(min_length=24, max_length=256)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    industry: str = Field(min_length=1, max_length=250)
    activities: str = ""
    state: str = ""
    employee_count: int | None = Field(default=None, ge=0)
    annual_turnover: str | None = None
    registrations: str = ""
    jurisdictions: list[str] = Field(default_factory=list, max_length=20)
    facilities: list[str] = Field(default_factory=list, max_length=30)
    operational_facts: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=40)


class ActionStatusIn(BaseModel):
    status: str = Field(pattern="^(Pending|In progress|Completed|Needs review)$")


class SyncSettingsIn(BaseModel):
    enabled: bool


class ChangeInterpretation(BaseModel):
    id: str
    explanation: str | None = None
    impact: str | None = None
    action: str | None = None
    deadline: str | None = None
    deadline_evidence: str | None = None


class FindingReviewIn(BaseModel):
    status: str = Field(pattern="^(NEEDS_REVIEW|REVIEWED|REQUIRES_FOLLOW_UP)$")


class ActionUpdateIn(BaseModel):
    status: str | None = Field(default=None, pattern="^(Pending|In progress|Completed|Needs review)$")
    assigned_role: str | None = Field(default=None, max_length=160)
