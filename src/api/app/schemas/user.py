import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.core.enums import UserRole
from app.schemas.common import PaginatedResponse


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: UserRole
    name: str
    email: EmailStr
    phone: str
    zone: str | None
    skills: list[str]
    active: bool
    email_verified: bool
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TechCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    email: EmailStr
    phone: str
    password: str
    zone: str | None = None
    skills: list[str] = []

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            msg = "Password must be at least 8 characters"
            raise ValueError(msg)
        return v


class TechUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    phone: str | None = None
    zone: str | None = None
    skills: list[str] | None = None
    active: bool | None = None


class CustomerCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    email: EmailStr
    phone: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            msg = "Password must be at least 8 characters"
            raise ValueError(msg)
        return v


PaginatedUsers = PaginatedResponse[UserOut]
