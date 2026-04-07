"""
Modelo ORM SQLModel para la entidad AuditLog (solo inserción).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.domain.enums import OperationEnum


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    table_name: str = Field(nullable=False)
    operation: OperationEnum = Field(nullable=False)
    record_id: uuid.UUID = Field(nullable=False)
    user_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    previous_data: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON)
    )
    new_data: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON)
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        index=True,
    )
