# Feature: jwt-role-authentication, Property 7: Student Self-Access Restriction
"""
Property-based tests for the ``require_self_or_roles`` dependency — specifically
the restriction that STUDENT users can only access their own data.

**Property 7 — Student Self-Access Restriction
(Validates: Requirements 5.6):**

For any two distinct user IDs where the requesting user has role STUDENT,
the system SHALL allow access to user data only when the requested user ID
matches the requesting user's own ID.  Access to any other user's data SHALL
be denied with HTTP 403.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from hypothesis import assume, given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.api.v1.dependencies.auth import CurrentUser, require_self_or_roles
from app.domain.enums import RoleEnum

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

user_id_strategy = st.uuids()


def _mock_session_no_enrollment() -> AsyncMock:
    """Return a mock ``AsyncSession`` that simulates no enrollment rows.

    STUDENT users never have an enrollment-based bypass (that path is only
    for PROFESSOR), so the query — if reached — always returns ``None``.
    """
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@h_settings(max_examples=100)
@given(student_id=user_id_strategy)
@pytest.mark.anyio
async def test_student_can_always_access_own_data(
    student_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.6**

    Property 7 (self-access grant): For any STUDENT, when the requested
    user_id matches their own ID, the dependency SHALL allow access and
    return the CurrentUser with the correct id and role.
    """
    current_user = CurrentUser(id=student_id, role=RoleEnum.STUDENT)
    mock_session = _mock_session_no_enrollment()

    result = await require_self_or_roles(
        user_id=student_id,
        current_user=current_user,
        session=mock_session,
    )

    assert result.id == student_id
    assert result.role == RoleEnum.STUDENT
    # Self-access shortcut should fire before any DB query
    mock_session.execute.assert_not_called()


@h_settings(max_examples=100)
@given(
    student_id=user_id_strategy,
    other_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_student_cannot_access_other_users_data(
    student_id: uuid.UUID,
    other_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.6**

    Property 7 (cross-access denial): For any two distinct user IDs where
    the requesting user has role STUDENT, access SHALL be denied with
    HTTP 403 and the message "No tiene permisos para esta acción".
    """
    assume(student_id != other_id)

    current_user = CurrentUser(id=student_id, role=RoleEnum.STUDENT)
    mock_session = _mock_session_no_enrollment()

    with pytest.raises(HTTPException) as exc_info:
        await require_self_or_roles(
            user_id=other_id,
            current_user=current_user,
            session=mock_session,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "No tiene permisos para esta acción"


@h_settings(max_examples=100)
@given(
    student_id=user_id_strategy,
    target_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_student_access_iff_self(
    student_id: uuid.UUID,
    target_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.6**

    Property 7 (biconditional): For any STUDENT and any target user_id,
    access SHALL be granted if and only if student_id == target_id.
    When student_id != target_id, access SHALL be denied with HTTP 403.
    """
    current_user = CurrentUser(id=student_id, role=RoleEnum.STUDENT)
    mock_session = _mock_session_no_enrollment()

    is_self = student_id == target_id

    if is_self:
        result = await require_self_or_roles(
            user_id=target_id,
            current_user=current_user,
            session=mock_session,
        )
        assert result.id == student_id
        assert result.role == RoleEnum.STUDENT
        # Self-access shortcut — no DB query
        mock_session.execute.assert_not_called()
    else:
        with pytest.raises(HTTPException) as exc_info:
            await require_self_or_roles(
                user_id=target_id,
                current_user=current_user,
                session=mock_session,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "No tiene permisos para esta acción"
