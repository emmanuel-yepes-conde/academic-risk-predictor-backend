"""API Endpoints."""

from app.api.v1.endpoints import auth, campuses, health, prediction, universities, users

__all__ = [
    "auth",
    "campuses",
    "health",
    "prediction",
    "universities",
    "users",
]

