"""
Integration tests for migration 0004: add_university_and_multi_university_support.

Validates:
- Migration on an empty DB completes without errors (Req 7.1, 7.5)
- Migration on a DB with existing data assigns DEFAULT_UNIVERSITY_ID (Req 7.2)
- Migration fails with descriptive message when DEFAULT_UNIVERSITY_ID is not set (Req 7.3)
- upgrade() + downgrade() restores schema without data loss (Req 7.4)

Uses a temporary SQLite database with PostgreSQL-specific types patched to
SQLite-compatible equivalents. Alembic operations unsupported by SQLite
(constraint ALTER, DROP TYPE, etc.) are patched to safe no-ops.

**Requirements: 7.1, 7.2, 7.3, 7.4, 7.5**
"""

import importlib.util
import logging
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

# Silence alembic/sqlalchemy logging during tests
logging.getLogger("alembic").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERSIONS_DIR = PROJECT_ROOT / "alembic" / "versions"


# ---------------------------------------------------------------------------
# SQLite-compatible type stubs
# ---------------------------------------------------------------------------

class _FakeUUID(sa.TypeDecorator):
    """Store UUIDs as VARCHAR(36) in SQLite."""
    impl = sa.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return value


class _FakeJSON(sa.TypeDecorator):
    """Store JSON as TEXT in SQLite. Accepts and ignores astext_type kwarg."""
    impl = sa.Text
    cache_ok = True

    def __init__(self, *args, **kwargs):
        kwargs.pop("astext_type", None)
        super().__init__(*args, **kwargs)


# ---------------------------------------------------------------------------
# SQLite-safe Alembic operation patching
# ---------------------------------------------------------------------------

@contextmanager
def _sqlite_safe_ops():
    """
    Patch Alembic operations unsupported on SQLite to safe no-ops.
    """
    originals = {
        "create_unique_constraint": alembic_op.create_unique_constraint,
        "drop_constraint": alembic_op.drop_constraint,
        "create_foreign_key": alembic_op.create_foreign_key,
        "drop_index": alembic_op.drop_index,
        "execute": alembic_op.execute,
        "alter_column": alembic_op.alter_column,
    }

    def _safe_drop_index(index_name, *args, **kwargs):
        try:
            originals["drop_index"](index_name, *args, **kwargs)
        except Exception:
            pass

    def _safe_execute(sql, *args, **kwargs):
        sql_str = str(sql).strip().upper()
        if sql_str.startswith("DROP TYPE") or sql_str.startswith("CREATE TYPE"):
            return
        return originals["execute"](sql, *args, **kwargs)

    alembic_op.create_unique_constraint = lambda *a, **kw: None
    alembic_op.drop_constraint = lambda *a, **kw: None
    alembic_op.create_foreign_key = lambda *a, **kw: None
    alembic_op.drop_index = _safe_drop_index
    alembic_op.execute = _safe_execute
    alembic_op.alter_column = lambda *a, **kw: None

    try:
        yield
    finally:
        for name, fn in originals.items():
            setattr(alembic_op, name, fn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_migration(revision: str):
    """Dynamically load a migration module by revision ID."""
    for f in VERSIONS_DIR.glob("*.py"):
        spec = importlib.util.spec_from_file_location(f"migration_{revision}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if getattr(mod, "revision", None) == revision:
            return mod
    raise FileNotFoundError(
        f"Migration revision '{revision}' not found in {VERSIONS_DIR}"
    )


def _run_with_ops(engine: sa.Engine, migration_mod, direction: str):
    """Run a migration's upgrade() or downgrade() within an Alembic Operations
    context, with SQLite-safe operation patches applied."""
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            with _sqlite_safe_ops():
                fn = getattr(migration_mod, direction)
                fn()


def _get_schema_snapshot(engine: sa.Engine) -> dict[str, list[str]]:
    """Return table_name → sorted list of column names (excluding alembic_version)."""
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        return {
            table: sorted(c["name"] for c in inspector.get_columns(table))
            for table in sorted(inspector.get_table_names())
            if table != "alembic_version"
        }


def _get_all_rows(engine: sa.Engine, table_name: str) -> list[dict]:
    """Return all rows from a table as a list of dicts."""
    with engine.connect() as conn:
        result = conn.execute(sa.text(f"SELECT * FROM {table_name}"))
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]


def _table_exists(engine: sa.Engine, table_name: str) -> bool:
    """Check if a table exists in the database."""
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        return table_name in inspector.get_table_names()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_type_patches():
    """Patch PostgreSQL-specific types with SQLite-compatible equivalents."""
    from sqlalchemy.dialects import postgresql as pg_dialect
    with (
        patch.object(pg_dialect, "UUID", _FakeUUID),
        patch.object(pg_dialect, "JSON", _FakeJSON),
    ):
        yield


@pytest.fixture
def migrations(pg_type_patches):
    """Load all migration modules (0001–0004)."""
    return {
        rev: _load_migration(rev)
        for rev in ("0001", "0002", "0003", "0004")
    }


@pytest.fixture
def temp_db(pg_type_patches):
    """Create a temporary SQLite database file and return its path. Cleaned up after test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    yield db_path
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def engine(temp_db):
    """Create a SQLAlchemy engine for the temporary SQLite database."""
    eng = sa.create_engine(f"sqlite:///{temp_db}")
    # Disable FK enforcement for SQLite
    with eng.connect() as conn:
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        conn.commit()
    yield eng
    eng.dispose()


@pytest.fixture
def baseline_engine(engine, migrations):
    """Engine with migrations 0001–0003 already applied (pre-0004 state)."""
    _run_with_ops(engine, migrations["0001"], "upgrade")
    _run_with_ops(engine, migrations["0002"], "upgrade")
    _run_with_ops(engine, migrations["0003"], "upgrade")
    return engine


def _seed_programs_and_courses(engine: sa.Engine, num_programs: int = 3, num_courses: int = 5):
    """Insert test programs and courses into a pre-0004 database.
    Returns (program_ids, course_ids, default_university_id)."""
    now = datetime.now(timezone.utc).isoformat()
    default_uni_id = str(uuid.uuid4())
    program_ids = []
    course_ids = []

    with engine.begin() as conn:
        for i in range(num_programs):
            pid = str(uuid.uuid4())
            program_ids.append(pid)
            conn.execute(
                sa.text(
                    "INSERT INTO programs "
                    "(id, institution, campus, degree_type, program_code, "
                    "program_name, pensum, academic_group, location, "
                    "snies_code, created_at) "
                    "VALUES (:id, :inst, :campus, :deg, :code, :name, "
                    ":pensum, :grp, :loc, :snies, :created)"
                ),
                {
                    "id": pid,
                    "inst": f"INST-{i}",
                    "campus": f"CAMPUS-{i}",
                    "deg": "PREG",
                    "code": f"INTPROG{i:04d}",
                    "name": f"Integration Program {i}",
                    "pensum": f"INTPEN{i:04d}",
                    "grp": f"GRP{i}",
                    "loc": f"LOC-{i}",
                    "snies": 50000 + i,
                    "created": now,
                },
            )

        for j in range(num_courses):
            cid = str(uuid.uuid4())
            course_ids.append(cid)
            target_program = program_ids[j % len(program_ids)]
            conn.execute(
                sa.text(
                    "INSERT INTO courses "
                    "(id, code, name, credits, academic_period, "
                    "program_id, created_at) "
                    "VALUES (:id, :code, :name, :credits, :period, "
                    ":program_id, :created)"
                ),
                {
                    "id": cid,
                    "code": f"INTCRS{j:04d}",
                    "name": f"Integration Course {j}",
                    "credits": 3,
                    "period": "2025-1",
                    "program_id": target_program,
                    "created": now,
                },
            )

    return program_ids, course_ids, default_uni_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMigration0004EmptyDB:
    """Migration on an empty DB completes without errors (Req 7.1, 7.5)."""

    def test_upgrade_on_empty_db_succeeds(self, baseline_engine, migrations):
        """
        Applying migration 0004 on a database with no existing programs or
        courses should complete without errors and create the universities table.

        **Requirements: 7.1, 7.5**
        """
        # No DEFAULT_UNIVERSITY_ID needed since there are no programs
        with patch.dict(os.environ, {}, clear=False):
            # Remove DEFAULT_UNIVERSITY_ID if present
            env_copy = os.environ.copy()
            env_copy.pop("DEFAULT_UNIVERSITY_ID", None)
            with patch.dict(os.environ, env_copy, clear=True):
                _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        # Verify universities table was created
        assert _table_exists(baseline_engine, "universities"), (
            "Table 'universities' should exist after migration 0004"
        )

        # Verify schema has expected new structures
        schema = _get_schema_snapshot(baseline_engine)
        assert "universities" in schema
        expected_uni_cols = ["active", "city", "code", "country", "created_at", "id", "name"]
        assert schema["universities"] == expected_uni_cols, (
            f"Universities table columns mismatch. "
            f"Expected: {expected_uni_cols}, Got: {schema['universities']}"
        )

        # Verify programs table has university_id column
        assert "university_id" in schema["programs"], (
            "Column 'university_id' should exist in programs after migration"
        )

    def test_upgrade_on_empty_db_creates_correct_schema(self, baseline_engine, migrations):
        """
        After migration 0004 on empty DB, all expected tables should exist
        with correct columns.

        **Requirements: 7.1, 7.5**
        """
        with patch.dict(os.environ, {}, clear=False):
            env_copy = os.environ.copy()
            env_copy.pop("DEFAULT_UNIVERSITY_ID", None)
            with patch.dict(os.environ, env_copy, clear=True):
                _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        schema = _get_schema_snapshot(baseline_engine)

        # All pre-existing tables should still be present
        expected_tables = {
            "users", "courses", "enrollments", "professor_courses",
            "audit_logs", "consents", "programs", "student_profiles",
            "universities",
        }
        assert expected_tables.issubset(set(schema.keys())), (
            f"Missing tables after migration. "
            f"Expected: {expected_tables}, Got: {set(schema.keys())}"
        )


class TestMigration0004WithData:
    """Migration on a DB with existing data assigns DEFAULT_UNIVERSITY_ID (Req 7.2)."""

    def test_existing_programs_get_default_university_id(self, baseline_engine, migrations):
        """
        When migration 0004 runs on a database with existing programs,
        all programs should be assigned the DEFAULT_UNIVERSITY_ID.

        **Requirements: 7.2**
        """
        program_ids, course_ids, default_uni_id = _seed_programs_and_courses(
            baseline_engine, num_programs=3, num_courses=5
        )

        with patch.dict(os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}):
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        # Verify all programs have the default university_id
        programs = _get_all_rows(baseline_engine, "programs")
        assert len(programs) == 3, (
            f"Expected 3 programs, got {len(programs)}"
        )
        for prog in programs:
            assert prog["university_id"] == default_uni_id, (
                f"Program {prog['id']} should have university_id={default_uni_id}, "
                f"got {prog['university_id']}"
            )

    def test_existing_courses_preserved_after_upgrade(self, baseline_engine, migrations):
        """
        Courses should not be lost or modified during migration 0004.

        **Requirements: 7.2**
        """
        program_ids, course_ids, default_uni_id = _seed_programs_and_courses(
            baseline_engine, num_programs=2, num_courses=4
        )

        courses_before = _get_all_rows(baseline_engine, "courses")

        with patch.dict(os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}):
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        courses_after = _get_all_rows(baseline_engine, "courses")
        assert len(courses_after) == len(courses_before), (
            f"Course count changed: before={len(courses_before)}, after={len(courses_after)}"
        )

        before_ids = {c["id"] for c in courses_before}
        after_ids = {c["id"] for c in courses_after}
        assert before_ids == after_ids, (
            f"Course IDs changed during migration. "
            f"Lost: {before_ids - after_ids}, Extra: {after_ids - before_ids}"
        )

    def test_program_data_integrity_preserved(self, baseline_engine, migrations):
        """
        Program fields (other than university_id) should remain unchanged
        after migration.

        **Requirements: 7.2**
        """
        program_ids, _, default_uni_id = _seed_programs_and_courses(
            baseline_engine, num_programs=3, num_courses=0
        )

        programs_before = _get_all_rows(baseline_engine, "programs")
        # Store original data keyed by id
        before_by_id = {p["id"]: p for p in programs_before}

        with patch.dict(os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}):
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        programs_after = _get_all_rows(baseline_engine, "programs")
        for prog in programs_after:
            original = before_by_id[prog["id"]]
            # All original fields should be preserved
            for field in ("institution", "campus", "degree_type", "program_code",
                          "program_name", "pensum", "academic_group", "location",
                          "snies_code"):
                assert prog[field] == original[field], (
                    f"Program {prog['id']} field '{field}' changed: "
                    f"before={original[field]}, after={prog[field]}"
                )


class TestMigration0004MissingConfig:
    """Migration fails with descriptive message if DEFAULT_UNIVERSITY_ID not configured (Req 7.3)."""

    def test_fails_when_default_university_id_not_set(self, baseline_engine, migrations):
        """
        When there are existing programs and DEFAULT_UNIVERSITY_ID is not set,
        the migration should fail with a descriptive error message.

        **Requirements: 7.3**
        """
        _seed_programs_and_courses(baseline_engine, num_programs=2, num_courses=1)

        # Ensure DEFAULT_UNIVERSITY_ID is NOT in the environment
        env_copy = os.environ.copy()
        env_copy.pop("DEFAULT_UNIVERSITY_ID", None)

        with patch.dict(os.environ, env_copy, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        error_message = str(exc_info.value)
        assert "DEFAULT_UNIVERSITY_ID" in error_message, (
            f"Error message should mention DEFAULT_UNIVERSITY_ID. Got: {error_message}"
        )

    def test_does_not_fail_on_empty_db_without_config(self, baseline_engine, migrations):
        """
        When there are NO existing programs, the migration should succeed
        even without DEFAULT_UNIVERSITY_ID configured.

        **Requirements: 7.3, 7.5**
        """
        # No programs seeded — empty DB
        env_copy = os.environ.copy()
        env_copy.pop("DEFAULT_UNIVERSITY_ID", None)

        with patch.dict(os.environ, env_copy, clear=True):
            # Should NOT raise
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        assert _table_exists(baseline_engine, "universities")


class TestMigration0004Reversibility:
    """upgrade() + downgrade() restores schema without data loss (Req 7.4)."""

    def test_schema_restored_after_roundtrip(self, baseline_engine, migrations):
        """
        After upgrade + downgrade, the schema should match the pre-0004 state.

        **Requirements: 7.4**
        """
        program_ids, course_ids, default_uni_id = _seed_programs_and_courses(
            baseline_engine, num_programs=3, num_courses=5
        )

        schema_before = _get_schema_snapshot(baseline_engine)

        # Upgrade
        with patch.dict(os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}):
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")

        # Verify universities table exists after upgrade
        assert _table_exists(baseline_engine, "universities")

        # Downgrade
        _run_with_ops(baseline_engine, migrations["0004"], "downgrade")

        schema_after = _get_schema_snapshot(baseline_engine)

        # Table sets should match
        assert set(schema_before.keys()) == set(schema_after.keys()), (
            f"Table sets differ after roundtrip.\n"
            f"  Before: {sorted(schema_before.keys())}\n"
            f"  After:  {sorted(schema_after.keys())}"
        )

        # Column sets per table should match
        for table_name in schema_before:
            assert schema_before[table_name] == schema_after[table_name], (
                f"Column mismatch for '{table_name}' after roundtrip.\n"
                f"  Before: {schema_before[table_name]}\n"
                f"  After:  {schema_after[table_name]}"
            )

        # universities table should NOT exist after downgrade
        assert "universities" not in schema_after, (
            "Table 'universities' should not exist after downgrade"
        )

        # university_id should be removed from programs
        assert "university_id" not in schema_after.get("programs", []), (
            "Column 'university_id' should not exist in programs after downgrade"
        )

    def test_no_program_data_loss_after_roundtrip(self, baseline_engine, migrations):
        """
        All program records should be preserved after upgrade + downgrade.

        **Requirements: 7.4**
        """
        program_ids, _, default_uni_id = _seed_programs_and_courses(
            baseline_engine, num_programs=4, num_courses=0
        )

        programs_before = _get_all_rows(baseline_engine, "programs")
        before_ids = {p["id"] for p in programs_before}
        before_codes = {p["program_code"] for p in programs_before}

        # Upgrade + Downgrade
        with patch.dict(os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}):
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")
        _run_with_ops(baseline_engine, migrations["0004"], "downgrade")

        programs_after = _get_all_rows(baseline_engine, "programs")
        after_ids = {p["id"] for p in programs_after}
        after_codes = {p["program_code"] for p in programs_after}

        assert len(programs_after) == len(programs_before), (
            f"Program count changed: before={len(programs_before)}, after={len(programs_after)}"
        )
        assert before_ids == after_ids, (
            f"Program IDs lost: {before_ids - after_ids}"
        )
        assert before_codes == after_codes, (
            f"Program codes lost: {before_codes - after_codes}"
        )

    def test_no_course_data_loss_after_roundtrip(self, baseline_engine, migrations):
        """
        All course records should be preserved after upgrade + downgrade.

        **Requirements: 7.4**
        """
        _, course_ids, default_uni_id = _seed_programs_and_courses(
            baseline_engine, num_programs=2, num_courses=6
        )

        courses_before = _get_all_rows(baseline_engine, "courses")
        before_ids = {c["id"] for c in courses_before}
        before_codes = {c["code"] for c in courses_before}

        # Upgrade + Downgrade
        with patch.dict(os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}):
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")
        _run_with_ops(baseline_engine, migrations["0004"], "downgrade")

        courses_after = _get_all_rows(baseline_engine, "courses")
        after_ids = {c["id"] for c in courses_after}
        after_codes = {c["code"] for c in courses_after}

        assert len(courses_after) == len(courses_before), (
            f"Course count changed: before={len(courses_before)}, after={len(courses_after)}"
        )
        assert before_ids == after_ids, (
            f"Course IDs lost: {before_ids - after_ids}"
        )
        assert before_codes == after_codes, (
            f"Course codes lost: {before_codes - after_codes}"
        )

    def test_field_values_preserved_after_roundtrip(self, baseline_engine, migrations):
        """
        All field values in programs and courses should be identical
        after upgrade + downgrade (except university_id which is removed).

        **Requirements: 7.4**
        """
        _, _, default_uni_id = _seed_programs_and_courses(
            baseline_engine, num_programs=3, num_courses=4
        )

        programs_before = _get_all_rows(baseline_engine, "programs")
        courses_before = _get_all_rows(baseline_engine, "courses")

        # Upgrade + Downgrade
        with patch.dict(os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}):
            _run_with_ops(baseline_engine, migrations["0004"], "upgrade")
        _run_with_ops(baseline_engine, migrations["0004"], "downgrade")

        programs_after = _get_all_rows(baseline_engine, "programs")
        courses_after = _get_all_rows(baseline_engine, "courses")

        # Compare programs field by field (keyed by id)
        before_by_id = {p["id"]: p for p in programs_before}
        for prog in programs_after:
            original = before_by_id[prog["id"]]
            for field in original:
                assert prog[field] == original[field], (
                    f"Program {prog['id']} field '{field}' changed after roundtrip: "
                    f"before={original[field]}, after={prog[field]}"
                )

        # Compare courses field by field (keyed by id)
        before_courses_by_id = {c["id"]: c for c in courses_before}
        for course in courses_after:
            original = before_courses_by_id[course["id"]]
            for field in original:
                assert course[field] == original[field], (
                    f"Course {course['id']} field '{field}' changed after roundtrip: "
                    f"before={original[field]}, after={course[field]}"
                )
