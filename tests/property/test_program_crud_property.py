# Feature: program-crud-endpoints, Property 1: ProgramCreate rejects incomplete input
"""
Property-based test for ProgramCreate schema validation.

Verifies that constructing a ProgramCreate instance with any subset of
required fields missing at least one field raises a ValidationError.

**Validates: Requirements 1.1, 1.2**
"""

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.application.schemas.program import ProgramCreate

# ---------------------------------------------------------------------------
# All required fields for ProgramCreate
# ---------------------------------------------------------------------------

ALL_REQUIRED_FIELDS = {
    "institution": "USBCO",
    "program_code": "M0200",
    "program_name": "Psicología",
    "snies_code": 12345,
}

FIELD_NAMES = list(ALL_REQUIRED_FIELDS.keys())


# Strategy: generate a non-empty subset of field names to REMOVE
# (at least 1 field missing, at most all fields missing)
missing_fields_strategy = st.lists(
    st.sampled_from(FIELD_NAMES),
    min_size=1,
    max_size=len(FIELD_NAMES),
    unique=True,
)


@h_settings(max_examples=100)
@given(fields_to_remove=missing_fields_strategy)
def test_program_create_rejects_incomplete_input(fields_to_remove: list[str]):
    """
    **Validates: Requirements 1.1, 1.2**

    Property 1: ProgramCreate rejects incomplete input.

    For any subset of required fields missing at least one, constructing
    ProgramCreate must raise ValidationError.
    """
    incomplete_data = {
        k: v for k, v in ALL_REQUIRED_FIELDS.items() if k not in fields_to_remove
    }

    with pytest.raises(ValidationError):
        ProgramCreate(**incomplete_data)


# ---------------------------------------------------------------------------
# Feature: program-crud-endpoints, Property 5: Round-trip search by unique fields
# ---------------------------------------------------------------------------

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.application.schemas.program import ProgramUpdate
from app.domain.enums import OperationEnum, RoleEnum
from app.infrastructure.models.program import Program
from app.infrastructure.repositories.program_repository import ProgramRepository
from app.infrastructure.models.audit_log import AuditLog


# ---------------------------------------------------------------------------
# Strategies for generating valid program data
# ---------------------------------------------------------------------------

program_code_st = st.text(
    alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
    min_size=3,
    max_size=10,
)

snies_code_st = st.integers(min_value=1, max_value=99999)

valid_program_data_st = st.fixed_dictionaries({
    "institution": st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    "degree_type": st.text(min_size=1, max_size=10).filter(lambda s: s.strip()),
    "program_code": program_code_st,
    "program_name": st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    "location": st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
    "snies_code": snies_code_st,
})


# ---------------------------------------------------------------------------
# Helper: build a mock AsyncSession that tracks programs and audit logs
# ---------------------------------------------------------------------------

def _make_tracking_session():
    """
    Build a mock AsyncSession that:
    - Stores added Program objects in a dict keyed by (program_code, snies_code, id)
    - Stores added AuditLog objects in a list
    - Returns the correct Program on execute() based on the WHERE clause
    """
    programs: dict[uuid.UUID, Program] = {}
    audit_logs: list[AuditLog] = []
    added: list = []

    def _add(obj):
        added.append(obj)
        if isinstance(obj, Program):
            programs[obj.id] = obj
        elif isinstance(obj, AuditLog):
            audit_logs.append(obj)

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        # Try to extract the WHERE clause to find the right program
        found = None
        try:
            whereclause = stmt.whereclause
            if whereclause is not None:
                # Check which column is being filtered
                left = str(whereclause.left)
                right_val = whereclause.right.effective_value if hasattr(whereclause.right, 'effective_value') else whereclause.right.value
                for p in programs.values():
                    if "program_code" in left and p.program_code == right_val:
                        found = p
                        break
                    elif "snies_code" in left and p.snies_code == right_val:
                        found = p
                        break
                    elif ".id" in left and p.id == right_val:
                        found = p
                        break
        except Exception:
            # Fallback: return last added non-audit object
            non_audit = [o for o in added if isinstance(o, Program)]
            found = non_audit[-1] if non_audit else None

        result.scalar_one_or_none.return_value = found
        return result

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_execute)
    mock_session._programs = programs
    mock_session._audit_logs = audit_logs
    mock_session._added = added
    return mock_session


# ---------------------------------------------------------------------------
# Property 5: Round-trip search by unique fields
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(data=valid_program_data_st)
async def test_round_trip_search_by_unique_fields(data: dict):
    """
    **Validates: Requirements 4.6, 4.7**

    Property 5: Round-trip search by unique fields.

    For any program persisted via create, get_by_program_code(program.program_code)
    and get_by_snies_code(program.snies_code) must return a program with the same id.
    """
    session = _make_tracking_session()
    repo = ProgramRepository(session)

    program = await repo.create(data)

    by_code = await repo.get_by_program_code(program.program_code)
    assert by_code is not None, "get_by_program_code returned None for a persisted program"
    assert by_code.id == program.id

    by_snies = await repo.get_by_snies_code(program.snies_code)
    assert by_snies is not None, "get_by_snies_code returned None for a persisted program"
    assert by_snies.id == program.id


# ---------------------------------------------------------------------------
# Property 3: Creation registers INSERT audit log
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(data=valid_program_data_st)
async def test_creation_registers_insert_audit_log(data: dict):
    """
    **Validates: Requirements 4.2**

    Property 3: Creation registers INSERT audit log.

    For any valid data, ProgramRepository.create must register an AuditLog
    with operation=INSERT, table_name="programs", and new_data matching
    the input data.
    """
    session = _make_tracking_session()
    repo = ProgramRepository(session)

    program = await repo.create(data)

    # Find the audit log entry for this program
    audit_entries = [
        log for log in session._audit_logs
        if log.record_id == program.id
    ]
    assert len(audit_entries) == 1, f"Expected 1 audit log, got {len(audit_entries)}"

    audit = audit_entries[0]
    assert audit.table_name == "programs"
    assert audit.operation == OperationEnum.INSERT
    assert audit.new_data == data
    assert audit.previous_data is None


# ---------------------------------------------------------------------------
# Property 4: Update registers UPDATE audit log with previous and new data
# ---------------------------------------------------------------------------

UPDATABLE_FIELDS = ["institution", "degree_type", "program_code",
                    "program_name", "location", "snies_code"]

# Strategy: generate a non-empty subset of fields to update
update_fields_st = st.lists(
    st.sampled_from(UPDATABLE_FIELDS),
    min_size=1,
    max_size=len(UPDATABLE_FIELDS),
    unique=True,
)

# Strategy: generate new values for the selected fields
def _make_update_values(fields: list[str]) -> dict:
    """Generate deterministic new values for the given fields."""
    values = {}
    for f in fields:
        if f == "snies_code":
            values[f] = 99999
        else:
            values[f] = f"NEW_{f.upper()}"
    return values


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    data=valid_program_data_st,
    fields_to_update=update_fields_st,
)
async def test_update_registers_update_audit_log(data: dict, fields_to_update: list[str]):
    """
    **Validates: Requirements 4.4**

    Property 4: Update registers UPDATE audit log with previous and new data.

    For any existing program and non-empty subset of fields,
    ProgramRepository.update must register an AuditLog with operation=UPDATE,
    previous_data with previous values, and new_data with new values.
    """
    session = _make_tracking_session()
    repo = ProgramRepository(session)

    # Create the program first
    program = await repo.create(data)

    # Build update data with only the selected fields
    update_values = _make_update_values(fields_to_update)
    update_schema = ProgramUpdate(**update_values)

    # Capture previous values before update
    previous_snapshot = {
        k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
        for k, v in program.model_dump().items()
    }

    updated = await repo.update(program.id, update_schema)
    assert updated is not None, "update returned None for an existing program"

    # Find the UPDATE audit log entry (skip the INSERT one)
    update_audits = [
        log for log in session._audit_logs
        if log.operation == OperationEnum.UPDATE and log.record_id == program.id
    ]
    assert len(update_audits) == 1, f"Expected 1 UPDATE audit log, got {len(update_audits)}"

    audit = update_audits[0]
    assert audit.table_name == "programs"
    assert audit.operation == OperationEnum.UPDATE
    assert audit.previous_data == previous_snapshot
    assert audit.new_data == update_values


# ---------------------------------------------------------------------------
# Feature: program-crud-endpoints, Property 6: Creation rejects duplicate unique fields
# ---------------------------------------------------------------------------

from fastapi import HTTPException
from app.application.services.program_service import ProgramService
from app.application.schemas.program import ProgramCreate, ProgramRead


def _make_mock_program(data: dict, program_id: uuid.UUID | None = None) -> MagicMock:
    """Build a MagicMock that looks like a Program ORM instance."""
    prog = MagicMock()
    prog.id = program_id or uuid.uuid4()
    prog.institution = data.get("institution", "INST")
    prog.degree_type = data.get("degree_type", "PREG")
    prog.program_code = data.get("program_code", "CODE")
    prog.program_name = data.get("program_name", "Name")
    prog.location = data.get("location", "LOC")
    prog.snies_code = data.get("snies_code", 1)
    prog.created_at = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    return prog


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(data=valid_program_data_st)
async def test_creation_rejects_duplicate_program_code(data: dict):
    """
    **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 8.1, 8.2**

    Property 6 (part a): Creation rejects duplicate program_code.

    For any program_code that already belongs to an existing program,
    create_program must raise HTTPException with code 409.
    """
    existing = _make_mock_program(data)

    repo = AsyncMock()
    repo.get_by_program_code.return_value = existing
    repo.get_by_snies_code.return_value = None

    service = ProgramService(repo)
    create_data = ProgramCreate(**data)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_program(create_data)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "El program_code ya está registrado"


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(data=valid_program_data_st)
async def test_creation_rejects_duplicate_snies_code(data: dict):
    """
    **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 8.1, 8.2**

    Property 6 (part b): Creation rejects duplicate snies_code.

    For any snies_code that already belongs to an existing program,
    create_program must raise HTTPException with code 409.
    """
    existing = _make_mock_program(data)

    repo = AsyncMock()
    repo.get_by_program_code.return_value = None
    repo.get_by_snies_code.return_value = existing

    service = ProgramService(repo)
    create_data = ProgramCreate(**data)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_program(create_data)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "El snies_code ya está registrado"


# ---------------------------------------------------------------------------
# Feature: program-crud-endpoints, Property 7: Update rejects unique fields
# belonging to another program
# ---------------------------------------------------------------------------

# Strategy: generate two distinct program data dicts
two_programs_st = st.tuples(valid_program_data_st, valid_program_data_st).filter(
    lambda pair: pair[0]["program_code"] != pair[1]["program_code"]
    and pair[0]["snies_code"] != pair[1]["snies_code"]
)


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(pair=two_programs_st)
async def test_update_rejects_program_code_belonging_to_another(pair: tuple[dict, dict]):
    """
    **Validates: Requirements 5.7, 5.8, 8.3, 8.4**

    Property 7 (part a): Update rejects program_code belonging to another program.

    For any two distinct programs A and B, update_program(A.id,
    ProgramUpdate(program_code=B.program_code)) must raise HTTPException 409.
    """
    data_a, data_b = pair
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()
    program_b = _make_mock_program(data_b, program_id=id_b)

    repo = AsyncMock()
    repo.get_by_program_code.return_value = program_b
    repo.get_by_snies_code.return_value = None

    service = ProgramService(repo)
    update_data = ProgramUpdate(program_code=data_b["program_code"])

    with pytest.raises(HTTPException) as exc_info:
        await service.update_program(id_a, update_data)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "El program_code ya está registrado"


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(pair=two_programs_st)
async def test_update_rejects_snies_code_belonging_to_another(pair: tuple[dict, dict]):
    """
    **Validates: Requirements 5.7, 5.8, 8.3, 8.4**

    Property 7 (part b): Update rejects snies_code belonging to another program.

    For any two distinct programs A and B, update_program(A.id,
    ProgramUpdate(snies_code=B.snies_code)) must raise HTTPException 409.
    """
    data_a, data_b = pair
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()
    program_b = _make_mock_program(data_b, program_id=id_b)

    repo = AsyncMock()
    repo.get_by_program_code.return_value = None
    repo.get_by_snies_code.return_value = program_b

    service = ProgramService(repo)
    update_data = ProgramUpdate(snies_code=data_b["snies_code"])

    with pytest.raises(HTTPException) as exc_info:
        await service.update_program(id_a, update_data)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "El snies_code ya está registrado"


# ---------------------------------------------------------------------------
# Feature: program-crud-endpoints, Property 8: Self-update with own unique
# fields succeeds
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(data=valid_program_data_st)
async def test_self_update_with_own_program_code_succeeds(data: dict):
    """
    **Validates: Requirements 5.9, 8.5**

    Property 8 (part a): Self-update with own program_code succeeds.

    For any existing program, update_program(program.id,
    ProgramUpdate(program_code=program.program_code)) must succeed.
    """
    prog_id = uuid.uuid4()
    existing = _make_mock_program(data, program_id=prog_id)
    updated = _make_mock_program(data, program_id=prog_id)

    repo = AsyncMock()
    repo.get_by_program_code.return_value = existing
    repo.get_by_snies_code.return_value = None
    repo.update.return_value = updated

    service = ProgramService(repo)
    update_data = ProgramUpdate(program_code=data["program_code"])

    result = await service.update_program(prog_id, update_data)
    assert isinstance(result, ProgramRead)
    assert result.id == prog_id


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(data=valid_program_data_st)
async def test_self_update_with_own_snies_code_succeeds(data: dict):
    """
    **Validates: Requirements 5.9, 8.5**

    Property 8 (part b): Self-update with own snies_code succeeds.

    For any existing program, update_program(program.id,
    ProgramUpdate(snies_code=program.snies_code)) must succeed.
    """
    prog_id = uuid.uuid4()
    existing = _make_mock_program(data, program_id=prog_id)
    updated = _make_mock_program(data, program_id=prog_id)

    repo = AsyncMock()
    repo.get_by_program_code.return_value = None
    repo.get_by_snies_code.return_value = existing
    repo.update.return_value = updated

    service = ProgramService(repo)
    update_data = ProgramUpdate(snies_code=data["snies_code"])

    result = await service.update_program(prog_id, update_data)
    assert isinstance(result, ProgramRead)
    assert result.id == prog_id


# ---------------------------------------------------------------------------
# Feature: program-crud-endpoints, Property 2: Partial update preserves
# omitted fields
# ---------------------------------------------------------------------------

# Strategy: generate a non-empty subset of ProgramUpdate fields to SET
_PROGRAM_UPDATE_FIELDS = [
    "institution", "degree_type", "program_code",
    "program_name", "location", "snies_code",
]

partial_fields_st = st.lists(
    st.sampled_from(_PROGRAM_UPDATE_FIELDS),
    min_size=1,
    max_size=len(_PROGRAM_UPDATE_FIELDS),
    unique=True,
)


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    original_data=valid_program_data_st,
    new_data=valid_program_data_st,
    fields_to_update=partial_fields_st,
)
async def test_partial_update_preserves_omitted_fields(
    original_data: dict, new_data: dict, fields_to_update: list[str]
):
    """
    **Validates: Requirements 2.2, 4.3**

    Property 2: Partial update preserves omitted fields.

    For any existing program and any non-empty subset of ProgramUpdate fields,
    update_program must modify only the provided fields and leave omitted
    fields unchanged.
    """
    prog_id = uuid.uuid4()

    # Build the update payload with only the selected fields
    update_values = {f: new_data[f] for f in fields_to_update}
    update_schema = ProgramUpdate(**update_values)

    # The "updated" program should have original values for omitted fields
    # and new values for provided fields
    expected_data = dict(original_data)
    for f in fields_to_update:
        expected_data[f] = new_data[f]

    updated_program = _make_mock_program(expected_data, program_id=prog_id)

    # For uniqueness checks: if program_code or snies_code is being updated,
    # return the same program (self-update) to avoid 409
    same_program = _make_mock_program(original_data, program_id=prog_id)

    repo = AsyncMock()
    repo.get_by_program_code.return_value = (
        same_program if "program_code" in fields_to_update else None
    )
    repo.get_by_snies_code.return_value = (
        same_program if "snies_code" in fields_to_update else None
    )
    repo.update.return_value = updated_program

    service = ProgramService(repo)
    result = await service.update_program(prog_id, update_schema)

    assert isinstance(result, ProgramRead)

    # Verify provided fields were updated
    for f in fields_to_update:
        assert getattr(result, f) == new_data[f], (
            f"Field '{f}' should be updated to {new_data[f]}, got {getattr(result, f)}"
        )

    # Verify omitted fields were preserved
    omitted = set(_PROGRAM_UPDATE_FIELDS) - set(fields_to_update)
    for f in omitted:
        assert getattr(result, f) == original_data[f], (
            f"Omitted field '{f}' should be preserved as {original_data[f]}, "
            f"got {getattr(result, f)}"
        )


# ---------------------------------------------------------------------------
# Feature: program-crud-endpoints, Property 9: Non-ADMIN role rejection
# ---------------------------------------------------------------------------

import jwt as _jwt
from datetime import timedelta
from httpx import ASGITransport, AsyncClient as _AsyncClient

from app.core.config import settings as _settings
from app.main import app as _app
from app.infrastructure.database import get_session as _get_session

# Non-ADMIN roles to test
_NON_ADMIN_ROLES = [r for r in RoleEnum if r != RoleEnum.ADMIN]

non_admin_role_st = st.sampled_from(_NON_ADMIN_ROLES)


def _create_access_token_for_role(role: RoleEnum) -> str:
    """Create a valid JWT access token with the given role."""
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return _jwt.encode(claims, _settings.JWT_SECRET_KEY, algorithm=_settings.JWT_ALGORITHM)


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    role=non_admin_role_st,
    data=valid_program_data_st,
)
async def test_non_admin_post_programs_returns_403(role: RoleEnum, data: dict):
    """
    **Validates: Requirements 6.4, 6.6, 7.5, 7.7**

    Property 9 (part a): Non-ADMIN role rejection for POST /programs.

    For any authenticated user whose role is not ADMIN, POST /programs
    must return status code 403.
    """
    token = _create_access_token_for_role(role)
    mock_session = AsyncMock()

    async def _override():
        yield mock_session

    _app.dependency_overrides[_get_session] = _override
    try:
        async with _AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/programs",
                json=data,
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 403
    finally:
        _app.dependency_overrides.clear()


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(role=non_admin_role_st)
async def test_non_admin_patch_programs_returns_403(role: RoleEnum):
    """
    **Validates: Requirements 6.4, 6.6, 7.5, 7.7**

    Property 9 (part b): Non-ADMIN role rejection for PATCH /programs/{id}.

    For any authenticated user whose role is not ADMIN, PATCH /programs/{id}
    must return status code 403.
    """
    token = _create_access_token_for_role(role)
    prog_id = uuid.uuid4()
    mock_session = AsyncMock()

    async def _override():
        yield mock_session

    _app.dependency_overrides[_get_session] = _override
    try:
        async with _AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as client:
            response = await client.patch(
                f"/api/v1/programs/{prog_id}",
                json={"program_name": "Test"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 403
    finally:
        _app.dependency_overrides.clear()
