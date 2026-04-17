# Feature: jwt-role-authentication, Property 6: RB-04 Professor Student Visibility
"""
Property-based tests for the ``require_self_or_roles`` dependency — specifically
the RB-04 rule that governs professor → student data visibility.

**Property 6 — RB-04 Professor Student Visibility
(Validates: Requirements 5.5):**

For any professor and any student, the professor SHALL be able to access the
student's data if and only if the student is enrolled in at least one course
assigned to that professor via the professor_courses table.  If no such
enrollment-course-assignment relationship exists, access SHALL be denied with
HTTP 403.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.api.v1.dependencies.auth import CurrentUser, require_self_or_roles
from app.domain.enums import RoleEnum

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

user_id_strategy = st.uuids()
# Generate small sets of course UUIDs to model professor-course-student graphs
course_ids_strategy = st.frozensets(st.uuids(), min_size=0, max_size=5)


def _mock_session_with_enrollment(has_enrollment: bool) -> AsyncMock:
    """Return a mock ``AsyncSession`` whose execute() simulates an enrollment query.

    When *has_enrollment* is ``True`` the mock returns a non-None scalar
    (i.e. a matching row exists), otherwise ``None``.
    """
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        uuid.uuid4() if has_enrollment else None
    )

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@h_settings(max_examples=100)
@given(
    professor_id=user_id_strategy,
    student_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_professor_can_access_student_when_enrolled_in_their_course(
    professor_id: uuid.UUID,
    student_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.5**

    Property 6 (grant path): For any professor and any student, when the
    student IS enrolled in at least one course assigned to the professor,
    the dependency SHALL allow access and return the CurrentUser.
    """
    # Ensure professor != student so we don't hit the self-access shortcut
    if professor_id == student_id:
        return  # trivially true — self-access is always allowed

    current_user = CurrentUser(id=professor_id, role=RoleEnum.PROFESSOR)
    mock_session = _mock_session_with_enrollment(has_enrollment=True)

    result = await require_self_or_roles(
        user_id=student_id,
        current_user=current_user,
        session=mock_session,
    )

    assert result.id == professor_id
    assert result.role == RoleEnum.PROFESSOR


@h_settings(max_examples=100)
@given(
    professor_id=user_id_strategy,
    student_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_professor_denied_when_student_not_enrolled_in_their_course(
    professor_id: uuid.UUID,
    student_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.5**

    Property 6 (denial path): For any professor and any student, when the
    student is NOT enrolled in any course assigned to the professor, the
    dependency SHALL raise HTTPException 403.
    """
    if professor_id == student_id:
        return  # self-access is always allowed — not the case under test

    current_user = CurrentUser(id=professor_id, role=RoleEnum.PROFESSOR)
    mock_session = _mock_session_with_enrollment(has_enrollment=False)

    with pytest.raises(HTTPException) as exc_info:
        await require_self_or_roles(
            user_id=student_id,
            current_user=current_user,
            session=mock_session,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "No tiene permisos para esta acción"


@h_settings(max_examples=100)
@given(
    professor_id=user_id_strategy,
    student_id=user_id_strategy,
    has_enrollment=st.booleans(),
)
@pytest.mark.anyio
async def test_professor_visibility_iff_enrollment_exists(
    professor_id: uuid.UUID,
    student_id: uuid.UUID,
    has_enrollment: bool,
):
    """
    **Validates: Requirements 5.5**

    Property 6 (biconditional): For any professor and any student (where
    professor ≠ student), the professor can access student data if and only if
    an enrollment-course-assignment relationship exists.
    """
    if professor_id == student_id:
        return  # self-access short-circuits — skip

    current_user = CurrentUser(id=professor_id, role=RoleEnum.PROFESSOR)
    mock_session = _mock_session_with_enrollment(has_enrollment=has_enrollment)

    if has_enrollment:
        result = await require_self_or_roles(
            user_id=student_id,
            current_user=current_user,
            session=mock_session,
        )
        assert result.id == professor_id
        assert result.role == RoleEnum.PROFESSOR
    else:
        with pytest.raises(HTTPException) as exc_info:
            await require_self_or_roles(
                user_id=student_id,
                current_user=current_user,
                session=mock_session,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "No tiene permisos para esta acción"


@h_settings(max_examples=100)
@given(
    user_id=user_id_strategy,
    target_id=user_id_strategy,
    has_enrollment=st.booleans(),
)
@pytest.mark.anyio
async def test_admin_always_bypasses_rb04(
    user_id: uuid.UUID,
    target_id: uuid.UUID,
    has_enrollment: bool,
):
    """
    **Validates: Requirements 5.4 (ADMIN bypass within RB-04 context)**

    For any ADMIN and any target user, access SHALL always be granted
    regardless of whether an enrollment relationship exists.
    """
    current_user = CurrentUser(id=user_id, role=RoleEnum.ADMIN)
    mock_session = _mock_session_with_enrollment(has_enrollment=has_enrollment)

    result = await require_self_or_roles(
        user_id=target_id,
        current_user=current_user,
        session=mock_session,
    )

    assert result.id == user_id
    assert result.role == RoleEnum.ADMIN
    # Session should NOT have been queried — ADMIN shortcut fires first
    mock_session.execute.assert_not_called()


@h_settings(max_examples=100)
@given(
    user_id=user_id_strategy,
    role=st.sampled_from(list(RoleEnum)),
)
@pytest.mark.anyio
async def test_self_access_always_allowed_regardless_of_role(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 5.6 (self-access within RB-04 context)**

    For any user accessing their own data (user_id == current_user.id),
    access SHALL always be granted regardless of role or enrollment status.
    """
    current_user = CurrentUser(id=user_id, role=role)
    mock_session = _mock_session_with_enrollment(has_enrollment=False)

    result = await require_self_or_roles(
        user_id=user_id,
        current_user=current_user,
        session=mock_session,
    )

    assert result.id == user_id
    assert result.role == role
    # Session should NOT have been queried — self-access shortcut fires first
    mock_session.execute.assert_not_called()


@h_settings(max_examples=100)
@given(
    student_id=user_id_strategy,
    other_student_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_student_cannot_access_other_student_data(
    student_id: uuid.UUID,
    other_student_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.6 (student restriction within RB-04 context)**

    For any STUDENT, accessing another student's data SHALL be denied with
    HTTP 403 — students have no enrollment-based visibility bypass.
    """
    if student_id == other_student_id:
        return  # self-access is always allowed — skip

    current_user = CurrentUser(id=student_id, role=RoleEnum.STUDENT)
    mock_session = _mock_session_with_enrollment(has_enrollment=False)

    with pytest.raises(HTTPException) as exc_info:
        await require_self_or_roles(
            user_id=other_student_id,
            current_user=current_user,
            session=mock_session,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "No tiene permisos para esta acción"
