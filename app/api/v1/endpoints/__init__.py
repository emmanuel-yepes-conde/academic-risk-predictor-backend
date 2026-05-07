"""API Endpoints."""

from app.api.v1.endpoints import auth, courses, enrollments, health, prediction, programs, referrals, users

__all__ = [
    "auth",
    "courses",
    "enrollments",
    "health",
    "prediction",
    "programs",
    "referrals",
    "users",
]
