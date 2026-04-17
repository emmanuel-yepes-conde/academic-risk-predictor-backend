# Feature: multi-university-support, Property 4: Actualización parcial no modifica campos no provistos
"""
Property-based test for university partial update.

Verifies that when a PATCH update is applied with a subset of updatable fields,
only those fields change; all other fields (including id, code, created_at and
any updatable field NOT included in the payload) remain identical.

**Validates: Requirements 1.6**
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from app.application.schemas.university import UniversityCreate, UniversityUpdate
from app.infrastructure.models.university import University
from app.infrastructure.repositories.university_repository import UniversityRepository

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

university_create_strategy = st.builds(
    UniversityCreate,
    name=st.text(min_size=1, max_size=200),
    code=st.from_regex(r"[A-Z0-9]{3,20}", fullmatch=True),
    country=st.text(min_size=1, max_size=100),
    city=st.text(min_size=1, max_size=100),
    active=st.booleans(),
)

# Strategy that generates an UniversityUpdate with at least one field set
# and at least one field left as None (to verify it stays unchanged).
# We draw each updatable field independently and ensure the result is a
# valid partial update (not all-None and not all-set).
_UPDATABLE_FIELDS = ["name", "country", "city", "active"]


@st.composite
def partial_update_strategy(draw):
    """
    Generate an UniversityUpdate where a random non-empty strict subset of
    updatable fields is set, and the rest are None.  This guarantees that
    there is always at least one field that IS updated and at least one
    field that is NOT updated, which is the interesting case for this property.
    """
    # Decide which fields to include (at least 1, at most len-1)
    included = draw(
        st.lists(
            st.sampled_from(_UPDATABLE_FIELDS),
            min_size=1,
            max_size=len(_UPDATABLE_FIELDS) - 1,
            unique=True,
        )
    )

    values: dict = {}
    for field in _UPDATABLE_FIELDS:
        if field in included:
            if field == "active":
                values[field] = draw(st.booleans())
            else:
                values[field] = draw(st.text(min_size=1, max_size=200))
        # Fields not in `included` are simply omitted so that
        # model_dump(exclude_unset=True) will not include them.

    return UniversityUpdate(**values)


# ---------------------------------------------------------------------------
# Mock session helper
# ---------------------------------------------------------------------------


def _make_mock_session() -> AsyncMock:
    """
    Return a mock AsyncSession that stores a single University and supports
    create + get_by_id + update flows used by UniversityRepository.
    """
    stored: dict[str, University] = {}  # keyed by str(id)

    def _add(obj):
        if isinstance(obj, University):
            stored[str(obj.id)] = obj

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        """
        Minimal statement introspection: the repository uses
        select(University).where(University.id == <uuid>).
        We return the stored university regardless of the exact statement,
        since in these tests there is only ever one university.
        """
        result = MagicMock()
        if stored:
            # Return the single stored university
            uni = next(iter(stored.values()))
            result.scalar_one_or_none.return_value = uni
        else:
            result.scalar_one_or_none.return_value = None
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    return mock_session


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    create_data=university_create_strategy,
    update_data=partial_update_strategy(),
)
async def test_partial_update_preserves_unset_fields(
    create_data: UniversityCreate,
    update_data: UniversityUpdate,
):
    """
    Property 4: Actualización parcial no modifica campos no provistos.

    For any valid university and any strict subset of updatable fields
    provided in a PATCH payload:
      - The fields included in the payload MUST reflect the new values.
      - The fields NOT included in the payload MUST remain identical to
        their pre-update values.
      - Immutable fields (id, code, created_at) MUST never change.

    **Validates: Requirements 1.6**
    """
    mock_session = _make_mock_session()
    repo = UniversityRepository(session=mock_session)

    # --- Create the university ---
    created = await repo.create(create_data)

    # Snapshot immutable and all updatable fields BEFORE the update
    snapshot_id = created.id
    snapshot_code = created.code
    snapshot_created_at = created.created_at
    snapshot_updatable = {
        field: getattr(created, field) for field in _UPDATABLE_FIELDS
    }

    # --- Apply partial update ---
    provided_fields = update_data.model_dump(exclude_unset=True)
    updated = await repo.update(created.id, update_data)

    assert updated is not None, "update must return the university"

    # --- Immutable fields must NEVER change ---
    assert updated.id == snapshot_id, "id must not change after update"
    assert updated.code == snapshot_code, "code must not change after update"
    assert updated.created_at == snapshot_created_at, (
        "created_at must not change after update"
    )

    # --- Provided fields must reflect new values ---
    for field, new_value in provided_fields.items():
        assert getattr(updated, field) == new_value, (
            f"Field '{field}' should be updated to {new_value!r}, "
            f"got {getattr(updated, field)!r}"
        )

    # --- Non-provided updatable fields must remain unchanged ---
    for field in _UPDATABLE_FIELDS:
        if field not in provided_fields:
            assert getattr(updated, field) == snapshot_updatable[field], (
                f"Field '{field}' was NOT in the update payload but changed "
                f"from {snapshot_updatable[field]!r} to {getattr(updated, field)!r}"
            )
