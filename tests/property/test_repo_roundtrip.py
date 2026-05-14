# Feature: postgresql-database-integration, Property 6: Repository round trip
"""
Property-based tests for repository round trips: create → get.

Verifies that after creating an entity via the repository, retrieving it
by id (and by email/identifier where applicable) returns exactly the same
field values that were passed to create.

**Validates: Requirements 6.1, 6.2, 6.4**
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.application.schemas.course import CourseCreate
from app.application.schemas.user import UserCreate
from app.domain.enums import RoleEnum
from app.infrastructure.models.consent import Consent
from app.infrastructure.models.course import Course
from app.infrastructure.models.user import User
from app.infrastructure.repositories.consent_repository import ConsentRepository
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.user_repository import UserRepository

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

role_strategy = st.sampled_from(list(RoleEnum))

user_create_strategy = st.builds(
    UserCreate,
    email=st.emails(),
    full_name=st.text(min_size=1, max_size=100),
    role=role_strategy,
    microsoft_oid=st.none(),
    google_oid=st.none(),
    password_hash=st.none(),
    ml_consent=st.booleans(),
)

course_create_strategy = st.builds(
    CourseCreate,
    code=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_")),
    name=st.text(min_size=1, max_size=100),
    credits=st.integers(min_value=1, max_value=10),
    academic_period=st.text(min_size=1, max_size=20),
)

version_strategy = st.text(min_size=1, max_size=20)

# ---------------------------------------------------------------------------
# Mock session helpers
# ---------------------------------------------------------------------------

def _make_mock_session_for(entity_type: type) -> AsyncMock:
    """
    Return a mock AsyncSession that simulates DB behaviour for a repository.

    Each repository calls session.add() twice per create: once for the entity
    and once for the AuditLog entry.  We only store the first object whose
    type matches `entity_type` so that the audit log add() does not overwrite
    the entity reference.
    """
    stored: list = []

    def _add(obj):
        if isinstance(obj, entity_type) and not stored:
            stored.append(obj)

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = stored[0] if stored else None
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    return mock_session


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(user_data=user_create_strategy)
async def test_user_roundtrip_get_by_id(user_data: UserCreate):
    """
    **Validates: Requirements 6.1**

    Property 6 (User – get_by_id): For any valid UserCreate input, the User
    returned by get_by_id(created.id) must have the same email, full_name,
    role, and ml_consent as the original UserCreate.
    """
    mock_session = _make_mock_session_for(User)
    repo = UserRepository(session=mock_session)

    created = await repo.create(user_data)

    retrieved = await repo.get_by_id(created.id)

    assert retrieved is not None, "get_by_id must return the created user"
    assert retrieved.email == user_data.email
    assert retrieved.full_name == user_data.full_name
    assert retrieved.role == user_data.role
    assert retrieved.ml_consent == user_data.ml_consent


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(user_data=user_create_strategy)
async def test_user_roundtrip_get_by_email(user_data: UserCreate):
    """
    **Validates: Requirements 6.1**

    Property 6 (User – get_by_email): For any valid UserCreate input, the User
    returned by get_by_email(created.email) must have the same id, full_name,
    role, and ml_consent as the created user.
    """
    mock_session = _make_mock_session_for(User)
    repo = UserRepository(session=mock_session)

    created = await repo.create(user_data)

    retrieved = await repo.get_by_email(created.email)

    assert retrieved is not None, "get_by_email must return the created user"
    assert retrieved.id == created.id
    assert retrieved.full_name == user_data.full_name
    assert retrieved.role == user_data.role
    assert retrieved.ml_consent == user_data.ml_consent


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(course_data=course_create_strategy)
async def test_course_roundtrip_get_by_id(course_data: CourseCreate):
    """
    **Validates: Requirements 6.2**

    Property 6 (Course – obtener_por_id): For any valid CourseCreate input,
    the Course returned by obtener_por_id(created.id) must have the same
    code, name, credits, and academic_period as the original CourseCreate.
    """
    mock_session = _make_mock_session_for(Course)
    repo = CourseRepository(session=mock_session)

    created = await repo.crear(course_data)

    retrieved = await repo.obtener_por_id(created.id)

    assert retrieved is not None, "obtener_por_id must return the created course"
    assert retrieved.code == course_data.code
    assert retrieved.name == course_data.name
    assert retrieved.credits == course_data.credits
    assert retrieved.academic_period == course_data.academic_period


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=st.uuids(), version=version_strategy)
async def test_consent_roundtrip_get_consent(student_id: uuid.UUID, version: str):
    """
    **Validates: Requirements 6.4**

    Property 6 (Consent – get_consent): For any student_id and terms_version,
    the Consent returned by get_consent(student_id) must have the same
    student_id, terms_version, and accepted=True as the registered consent.
    """
    mock_session = _make_mock_session_for(Consent)
    repo = ConsentRepository(session=mock_session)

    created = await repo.register_consent(student_id=student_id, version=version)

    retrieved = await repo.get_consent(student_id)

    assert retrieved is not None, "get_consent must return the registered consent"
    assert retrieved.student_id == student_id
    assert retrieved.terms_version == version
    assert retrieved.accepted is True
    assert retrieved.id == created.id
