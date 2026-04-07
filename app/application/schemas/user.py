"""Pydantic DTOs for User operations."""

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.domain.enums import RoleEnum, UserStatusEnum

T = TypeVar("T")


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: RoleEnum
    microsoft_oid: str | None = None
    google_oid: str | None = None
    password_hash: str | None = None
    ml_consent: bool = False


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: RoleEnum | None = None
    microsoft_oid: str | None = None
    google_oid: str | None = None
    password_hash: str | None = None
    ml_consent: bool | None = None


class UserRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: RoleEnum
    status: UserStatusEnum
    ml_consent: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserStatusUpdate(BaseModel):
    status: UserStatusEnum


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    total: int
    skip: int
    limit: int
