"""Pydantic DTOs for AuditLog operations."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import OperationEnum


class AuditLogCreate(BaseModel):
    table_name: str
    operation: OperationEnum
    record_id: UUID
    user_id: UUID | None = None
    previous_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None
