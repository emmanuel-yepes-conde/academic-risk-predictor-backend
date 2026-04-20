"""API Endpoints."""

from app.api.v1.endpoints import auth, courses, health, prediction, programs, users

__all__ = [
    "auth",
    "courses",
    "health",
    "prediction",
    "programs",
    "users",
]
