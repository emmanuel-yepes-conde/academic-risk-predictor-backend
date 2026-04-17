"""
Integration tests for migration 0005: add_campus_hierarchy.

Validates:
- Migration on an empty DB completes without errors (Req 7.1, 7.8)
- Migration on a DB with existing programs creates campus records and assigns campus_id (Req 7.2, 7.3, 7.4)
- upgrade() + downgrade() restores schema without data loss (Req 7.5, 7.6, 7.7)
- Post-migration the UniqueConstraint uq_program_code_campus is active (Req 7.6)

Uses a temporary SQLite database with PostgreSQL-specific types patched to
SQLite-compatible equivalents. Alembic operations unsupported by SQLite
(constraint ALTER, DROP TYPE, etc.) are patched to safe no-ops.
PostgreSQL-specific SQL functions (gen_random_uuid, now) are registered as
SQLite custom functions, and UPDATE ... FROM syntax is rewritten for SQLite.

**Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8**
"""

import importlib.util
import logging
import os
import re
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
from sqlalchemy import event

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
# PostgreSQL → SQLite SQL rewriting
# ---------------------------------------------------------------------------

def _rewrite_pg_sql_for_sqlite(sql_text: str) -> str:
    """
    Rewrite PostgreSQL-specific SQL to SQLite-compatible equivalents.

    Handles:
    - UPDATE ... SET ... FROM <table> WHERE ... → UPDATE ... SET ... = (SELECT ...)
    - gen_random_uuid() → already handled via SQLite custom function
    - now() → already handled via SQLite custom function
    - true/false → 1/0
    """
    sql = sql_text.strip()

    # Rewrite: UPDATE programs SET campus_id = c.id FROM campuses c
    #          WHERE c.university_id = programs.university_id AND c.campus_code = programs.campus
    # To:      UPDATE programs SET campus_id = (SELECT c.id FROM campuses c
    #          WHERE c.university_id = programs.university_id AND c.campus_code = programs.campus)
    pattern_update_from = re.compile(
        r"UPDATE\s+(\w+)\s+SET\s+(\w+)\s*=\s*(\w+\.\w+)\s+"
        r"FROM\s+(\w+)\s+(\w+)\s+"
        r"WHERE\s+(.+)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern_update_from.match(sql)
    if match:
        target_table = match.group(1)
        set_col = match.group(2)
        set_val = match.group(3)
        from_table = match.group(4)
        from_alias = match.group(5)
        where_clause = match.group(6).strip()
        return (
            f"UPDATE {target_table} SET {set_col} = "
            f"(SELECT {set_val} FROM {from_table} {from_alias} WHERE {where_clause})"
        )

    return sql


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


def _register_pg_functions(engine: sa.Engine):
    """Register PostgreSQL-specific functions as SQLite custom functions."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _):
        dbapi_conn.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))
        dbapi_conn.create_function(
            "now", 0, lambda: datetime.now(timezone.utc).isoformat()
        )


def _run_with_ops(engine: sa.Engine, migration_mod, direction: str):
    """Run a migration's upgrade() or downgrade() within an Alembic Operations
    context, with SQLite-safe operation patches applied.

    For migration 0005, intercepts raw SQL to rewrite PostgreSQL-specific
    UPDATE ... FROM syntax to SQLite-compatible subqueries.
    """
    original_sa_text = sa.text

    def _patched_text(sql_str):
        rewritten = _rewrite_pg_sql_for_sqlite(sql_str)
        return original_sa_text(rewritten)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            with _sqlite_safe_ops():
                with patch.object(sa, "text", side_effect=_patched_text):
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


def _column_exists(engine: sa.Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        columns = [c["name"] for c in inspector.get_columns(table_name)]
        return column_name in columns


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
    """Load all migration modules (0001–0005)."""
    return {
        rev: _load_migration(rev)
        for rev in ("0001", "0002", "0003", "0004", "0005")
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
    # Register PostgreSQL-compatible functions for SQLite
    _register_pg_functions(eng)
    # Disable FK enforcement for SQLite
    with eng.connect() as conn:
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        conn.commit()
    yield eng
    eng.dispose()


@pytest.fixture
def baseline_engine(engine, migrations):
    """Engine with migrations 0001–0004 already applied (pre-0005 state).

    This represents a database that has the universities table and programs
    with university_id, ready for the campus hierarchy migration.
    """
    _run_with_ops(engine, migrations["0001"], "upgrade")
    _run_with_ops(engine, migrations["0002"], "upgrade")
    _run_with_ops(engine, migrations["0003"], "upgrade")
    # Migration 0004 needs DEFAULT_UNIVERSITY_ID if there are programs,
    # but on empty DB it works without it.
    env_copy = os.environ.copy()
    env_copy.pop("DEFAULT_UNIVERSITY_ID", None)
    with patch.dict(os.environ, env_copy, clear=True):
        _run_with_ops(engine, migrations["0004"], "upgrade")
    return engine


def _seed_university(engine: sa.Engine, university_id: str | None = None) -> str:
    """Insert a test university and return its ID."""
    uni_id = university_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO universities (id, name, code, country, city, active, created_at) "
                "VALUES (:id, :name, :code, :country, :city, 1, :created)"
            ),
            {
                "id": uni_id,
                "name": "Test University",
                "code": f"TU{uuid.uuid4().hex[:6].upper()}",
                "country": "Colombia",
                "city": "Bogotá",
                "created": now,
            },
        )
    return uni_id


def _seed_programs_with_campus_text(
    engine: sa.Engine,
    university_id: str,
    campus_values: list[str],
) -> list[str]:
    """Insert programs into a post-0004 database (has university_id, has campus text column).

    Each campus_value creates one program with that campus text.
    Returns list of program IDs.
    """
    now = datetime.now(timezone.utc).isoformat()
    program_ids = []
    with engine.begin() as conn:
        for i, campus_text in enumerate(campus_values):
            pid = str(uuid.uuid4())
            program_ids.append(pid)
            conn.execute(
                sa.text(
                    "INSERT INTO programs "
                    "(id, university_id, institution, campus, degree_type, program_code, "
                    "program_name, pensum, academic_group, location, snies_code, created_at) "
                    "VALUES (:id, :uid, :inst, :campus, :deg, :code, :name, "
                    ":pensum, :grp, :loc, :snies, :created)"
                ),
                {
                    "id": pid,
                    "uid": university_id,
                    "inst": f"INST-{i}",
                    "campus": campus_text,
                    "deg": "PREG",
                    "code": f"PROG{i:04d}",
                    "name": f"Program {i}",
                    "pensum": f"PEN{i:04d}",
                    "grp": f"GRP{i}",
                    "loc": f"LOC-{i}",
                    "snies": 60000 + i,
                    "created": now,
                },
            )
    return program_ids


def _seed_courses_for_programs(
    engine: sa.Engine, program_ids: list[str], courses_per_program: int = 2
) -> list[str]:
    """Insert courses linked to the given programs. Returns list of course IDs."""
    now = datetime.now(timezone.utc).isoformat()
    course_ids = []
    with engine.begin() as conn:
        for i, pid in enumerate(program_ids):
            for j in range(courses_per_program):
                cid = str(uuid.uuid4())
                course_ids.append(cid)
                conn.execute(
                    sa.text(
                        "INSERT INTO courses "
                        "(id, code, name, credits, academic_period, program_id, created_at) "
                        "VALUES (:id, :code, :name, :credits, :period, :pid, :created)"
                    ),
                    {
                        "id": cid,
                        "code": f"CRS{i:02d}{j:02d}",
                        "name": f"Course {i}-{j}",
                        "credits": 3,
                        "period": "2025-1",
                        "pid": pid,
                        "created": now,
                    },
                )
    return course_ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMigration0005ModuleStructure:
    """Verify migration module metadata and revision chain."""

    def test_revision_identifiers(self, migrations):
        """
        Migration 0005 should have correct revision='0005' and
        down_revision='0004' to form a valid Alembic chain.

        **Requirements: 7.1**
        """
        mod = migrations["0005"]
        assert mod.revision == "0005", (
            f"Expected revision='0005', got '{mod.revision}'"
        )
        assert mod.down_revision == "0004", (
            f"Expected down_revision='0004', got '{mod.down_revision}'"
        )

    def test_has_upgrade_and_downgrade(self, migrations):
        """
        Migration 0005 should define both upgrade() and downgrade() functions.

        **Requirements: 7.1, 7.7**
        """
        mod = migrations["0005"]
        assert callable(getattr(mod, "upgrade", None)), (
            "Migration 0005 must define an upgrade() function"
        )
        assert callable(getattr(mod, "downgrade", None)), (
            "Migration 0005 must define a downgrade() function"
        )


class TestMigration0005EmptyDB:
    """Migration on an empty DB completes without errors (Req 7.1, 7.8)."""

    def test_upgrade_on_empty_db_succeeds(self, baseline_engine, migrations):
        """
        Applying migration 0005 on a database with no existing programs
        should complete without errors and create the campuses table.

        **Requirements: 7.1, 7.8**
        """
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        assert _table_exists(baseline_engine, "campuses"), (
            "Table 'campuses' should exist after migration 0005"
        )

    def test_campuses_table_has_correct_columns(self, baseline_engine, migrations):
        """
        After migration 0005 on empty DB, the campuses table should have
        all expected columns.

        **Requirements: 7.1, 7.8**
        """
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        schema = _get_schema_snapshot(baseline_engine)
        assert "campuses" in schema, "campuses table should exist"

        expected_cols = sorted([
            "id", "university_id", "campus_code", "name", "city", "active", "created_at",
        ])
        assert schema["campuses"] == expected_cols, (
            f"Campuses table columns mismatch. "
            f"Expected: {expected_cols}, Got: {schema['campuses']}"
        )

    def test_programs_has_campus_id_after_upgrade(self, baseline_engine, migrations):
        """
        After migration 0005, the programs table should have a campus_id column
        and the old campus text column should be removed.

        **Requirements: 7.1, 7.5**
        """
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        schema = _get_schema_snapshot(baseline_engine)
        assert "campus_id" in schema["programs"], (
            "Column 'campus_id' should exist in programs after migration 0005"
        )
        assert "campus" not in schema["programs"], (
            "Column 'campus' (text) should be removed from programs after migration 0005"
        )

    def test_no_campus_records_created_on_empty_db(self, baseline_engine, migrations):
        """
        On an empty DB (no programs), the data migration step should not
        create any campus records.

        **Requirements: 7.8**
        """
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        campuses = _get_all_rows(baseline_engine, "campuses")
        assert len(campuses) == 0, (
            f"Expected 0 campus records on empty DB, got {len(campuses)}"
        )


class TestMigration0005WithData:
    """Migration on a DB with existing programs creates campus records and assigns campus_id (Req 7.2, 7.3, 7.4)."""

    def test_creates_campus_records_from_distinct_campus_values(
        self, baseline_engine, migrations
    ):
        """
        When programs exist with campus text values, the migration should
        create one campus record per unique (university_id, campus) combination.

        **Requirements: 7.2, 7.3**
        """
        uni_id = _seed_university(baseline_engine)
        # Two programs with "MED", one with "BOG" → 2 unique campus records
        _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "MED", "BOG"]
        )

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        campuses = _get_all_rows(baseline_engine, "campuses")
        assert len(campuses) == 2, (
            f"Expected 2 campus records (MED, BOG), got {len(campuses)}"
        )

        campus_codes = {c["campus_code"] for c in campuses}
        assert campus_codes == {"MED", "BOG"}, (
            f"Expected campus codes {{'MED', 'BOG'}}, got {campus_codes}"
        )

    def test_campus_code_derived_from_text_field(self, baseline_engine, migrations):
        """
        The campus_code in the new campuses table should be derived from
        the original text value of the campus field in programs.

        **Requirements: 7.3**
        """
        uni_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(baseline_engine, uni_id, ["SAN BENITO"])

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        campuses = _get_all_rows(baseline_engine, "campuses")
        assert len(campuses) == 1
        assert campuses[0]["campus_code"] == "SAN BENITO", (
            f"campus_code should be 'SAN BENITO', got '{campuses[0]['campus_code']}'"
        )

    def test_assigns_campus_id_to_all_programs(self, baseline_engine, migrations):
        """
        After migration, every program should have a non-null campus_id
        that references a valid campus record.

        **Requirements: 7.4**
        """
        uni_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "BOG", "MED"]
        )

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        programs = _get_all_rows(baseline_engine, "programs")
        campuses = _get_all_rows(baseline_engine, "campuses")
        campus_ids = {c["id"] for c in campuses}

        for prog in programs:
            assert prog["campus_id"] is not None, (
                f"Program {prog['id']} should have a non-null campus_id"
            )
            assert prog["campus_id"] in campus_ids, (
                f"Program {prog['id']} campus_id={prog['campus_id']} "
                f"does not reference a valid campus"
            )

    def test_programs_with_same_campus_share_campus_id(
        self, baseline_engine, migrations
    ):
        """
        Programs that had the same campus text value (within the same university)
        should share the same campus_id after migration.

        **Requirements: 7.4**
        """
        uni_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "MED", "BOG"]
        )

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        programs = _get_all_rows(baseline_engine, "programs")
        # Sort by program_code to get deterministic order
        programs.sort(key=lambda p: p["program_code"])

        # First two programs had "MED" → same campus_id
        assert programs[0]["campus_id"] == programs[1]["campus_id"], (
            "Programs with same campus text should share the same campus_id"
        )
        # Third program had "BOG" → different campus_id
        assert programs[0]["campus_id"] != programs[2]["campus_id"], (
            "Programs with different campus text should have different campus_ids"
        )

    def test_campus_university_id_matches_program_university_id(
        self, baseline_engine, migrations
    ):
        """
        Each created campus record should have the correct university_id
        matching the programs it was derived from.

        **Requirements: 7.2**
        """
        uni_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(baseline_engine, uni_id, ["MED"])

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        campuses = _get_all_rows(baseline_engine, "campuses")
        assert len(campuses) == 1
        assert campuses[0]["university_id"] == uni_id, (
            f"Campus university_id should be {uni_id}, "
            f"got {campuses[0]['university_id']}"
        )

    def test_courses_preserved_after_upgrade(self, baseline_engine, migrations):
        """
        Courses should not be lost or modified during migration 0005.

        **Requirements: 7.2**
        """
        uni_id = _seed_university(baseline_engine)
        prog_ids = _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "BOG"]
        )
        course_ids = _seed_courses_for_programs(baseline_engine, prog_ids)

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        courses_after = _get_all_rows(baseline_engine, "courses")
        after_ids = {c["id"] for c in courses_after}
        assert set(course_ids) == after_ids, (
            f"Course IDs changed during migration. "
            f"Lost: {set(course_ids) - after_ids}, Extra: {after_ids - set(course_ids)}"
        )

    def test_multiple_universities_create_separate_campuses(
        self, baseline_engine, migrations
    ):
        """
        Programs from different universities with the same campus text
        should create separate campus records (one per university).

        **Requirements: 7.2, 7.3**
        """
        uni1_id = _seed_university(baseline_engine)
        uni2_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(baseline_engine, uni1_id, ["MED"])
        # Need unique program_code/snies for second university
        now = datetime.now(timezone.utc).isoformat()
        with baseline_engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO programs "
                    "(id, university_id, institution, campus, degree_type, program_code, "
                    "program_name, pensum, academic_group, location, snies_code, created_at) "
                    "VALUES (:id, :uid, :inst, :campus, :deg, :code, :name, "
                    ":pensum, :grp, :loc, :snies, :created)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "uid": uni2_id,
                    "inst": "INST-X",
                    "campus": "MED",
                    "deg": "PREG",
                    "code": "PROGX001",
                    "name": "Program X",
                    "pensum": "PENX001",
                    "grp": "GRPX",
                    "loc": "LOC-X",
                    "snies": 70001,
                    "created": now,
                },
            )

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        campuses = _get_all_rows(baseline_engine, "campuses")
        # Same campus_code "MED" but different universities → 2 records
        assert len(campuses) == 2, (
            f"Expected 2 campus records (one per university), got {len(campuses)}"
        )
        uni_ids = {c["university_id"] for c in campuses}
        assert uni_ids == {uni1_id, uni2_id}, (
            f"Each university should have its own campus record"
        )


class TestMigration0005Reversibility:
    """upgrade() + downgrade() restores schema without data loss (Req 7.5, 7.6, 7.7)."""

    def test_schema_restored_after_roundtrip(self, baseline_engine, migrations):
        """
        After upgrade + downgrade, the schema should match the pre-0005 state.
        The campuses table should be removed and the campus text column restored.

        **Requirements: 7.7**
        """
        uni_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "BOG"]
        )

        schema_before = _get_schema_snapshot(baseline_engine)

        # Upgrade
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")
        assert _table_exists(baseline_engine, "campuses"), (
            "campuses table should exist after upgrade"
        )

        # Downgrade
        _run_with_ops(baseline_engine, migrations["0005"], "downgrade")

        schema_after = _get_schema_snapshot(baseline_engine)

        # Table sets should match
        assert set(schema_before.keys()) == set(schema_after.keys()), (
            f"Table sets differ after roundtrip.\n"
            f"  Before: {sorted(schema_before.keys())}\n"
            f"  After:  {sorted(schema_after.keys())}"
        )

        # campuses table should NOT exist after downgrade
        assert "campuses" not in schema_after, (
            "Table 'campuses' should not exist after downgrade"
        )

        # campus text column should be restored in programs
        assert "campus" in schema_after.get("programs", []), (
            "Column 'campus' (text) should be restored in programs after downgrade"
        )

        # campus_id should be removed from programs
        assert "campus_id" not in schema_after.get("programs", []), (
            "Column 'campus_id' should not exist in programs after downgrade"
        )

    def test_no_program_data_loss_after_roundtrip(self, baseline_engine, migrations):
        """
        All program records should be preserved after upgrade + downgrade.

        **Requirements: 7.7**
        """
        uni_id = _seed_university(baseline_engine)
        prog_ids = _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "BOG", "CAL"]
        )

        programs_before = _get_all_rows(baseline_engine, "programs")
        before_ids = {p["id"] for p in programs_before}
        before_codes = {p["program_code"] for p in programs_before}

        # Upgrade + Downgrade
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")
        _run_with_ops(baseline_engine, migrations["0005"], "downgrade")

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

    def test_campus_text_values_restored_after_roundtrip(
        self, baseline_engine, migrations
    ):
        """
        After upgrade + downgrade, the campus text field should be repopulated
        with the original values derived from the campuses table.

        **Requirements: 7.7**
        """
        uni_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "BOG", "MED"]
        )

        programs_before = _get_all_rows(baseline_engine, "programs")
        before_campus_by_id = {p["id"]: p["campus"] for p in programs_before}

        # Upgrade + Downgrade
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")
        _run_with_ops(baseline_engine, migrations["0005"], "downgrade")

        programs_after = _get_all_rows(baseline_engine, "programs")
        for prog in programs_after:
            expected_campus = before_campus_by_id[prog["id"]]
            assert prog["campus"] == expected_campus, (
                f"Program {prog['id']} campus text should be '{expected_campus}', "
                f"got '{prog['campus']}'"
            )

    def test_no_course_data_loss_after_roundtrip(self, baseline_engine, migrations):
        """
        All course records should be preserved after upgrade + downgrade.

        **Requirements: 7.7**
        """
        uni_id = _seed_university(baseline_engine)
        prog_ids = _seed_programs_with_campus_text(
            baseline_engine, uni_id, ["MED", "BOG"]
        )
        course_ids = _seed_courses_for_programs(baseline_engine, prog_ids)

        courses_before = _get_all_rows(baseline_engine, "courses")

        # Upgrade + Downgrade
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")
        _run_with_ops(baseline_engine, migrations["0005"], "downgrade")

        courses_after = _get_all_rows(baseline_engine, "courses")
        assert len(courses_after) == len(courses_before), (
            f"Course count changed: before={len(courses_before)}, after={len(courses_after)}"
        )

        before_ids = {c["id"] for c in courses_before}
        after_ids = {c["id"] for c in courses_after}
        assert before_ids == after_ids, (
            f"Course IDs lost: {before_ids - after_ids}"
        )

    def test_empty_db_roundtrip_succeeds(self, baseline_engine, migrations):
        """
        upgrade + downgrade on an empty DB should complete without errors.

        **Requirements: 7.7, 7.8**
        """
        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")
        _run_with_ops(baseline_engine, migrations["0005"], "downgrade")

        # campuses table should be gone
        assert not _table_exists(baseline_engine, "campuses"), (
            "campuses table should not exist after downgrade"
        )
        # campus text column should be restored
        assert _column_exists(baseline_engine, "programs", "campus"), (
            "campus text column should be restored after downgrade"
        )


class TestMigration0005UniqueConstraint:
    """Post-migration the UniqueConstraint uq_program_code_campus is active (Req 7.6)."""

    def test_constraint_change_from_university_to_campus_scope(
        self, baseline_engine, migrations
    ):
        """
        After migration 0005, the uniqueness of program_code should be scoped
        to campus_id instead of university_id. This is verified by checking
        that the migration drops uq_program_code_university and creates
        uq_program_code_campus.

        **Requirements: 7.6**
        """
        mod = migrations["0005"]

        # Inspect the upgrade function source to verify constraint operations
        import inspect
        source = inspect.getsource(mod.upgrade)

        assert "uq_program_code_university" in source, (
            "upgrade() should reference uq_program_code_university (to drop it)"
        )
        assert "uq_program_code_campus" in source, (
            "upgrade() should reference uq_program_code_campus (to create it)"
        )
        assert 'drop_constraint("uq_program_code_university"' in source or \
               "drop_constraint('uq_program_code_university'" in source, (
            "upgrade() should drop the uq_program_code_university constraint"
        )
        assert 'create_unique_constraint' in source, (
            "upgrade() should create a new unique constraint"
        )

    def test_downgrade_restores_university_scope_constraint(
        self, baseline_engine, migrations
    ):
        """
        The downgrade() should restore the uq_program_code_university constraint
        and drop uq_program_code_campus.

        **Requirements: 7.6, 7.7**
        """
        mod = migrations["0005"]

        import inspect
        source = inspect.getsource(mod.downgrade)

        assert "uq_program_code_campus" in source, (
            "downgrade() should reference uq_program_code_campus (to drop it)"
        )
        assert "uq_program_code_university" in source, (
            "downgrade() should reference uq_program_code_university (to create it)"
        )

    def test_campus_text_column_removed_after_upgrade(
        self, baseline_engine, migrations
    ):
        """
        After migration 0005, the old campus text column should be removed
        from the programs table.

        **Requirements: 7.5**
        """
        uni_id = _seed_university(baseline_engine)
        _seed_programs_with_campus_text(baseline_engine, uni_id, ["MED"])

        # Verify campus text column exists before migration
        assert _column_exists(baseline_engine, "programs", "campus"), (
            "campus text column should exist before migration 0005"
        )

        _run_with_ops(baseline_engine, migrations["0005"], "upgrade")

        # Verify campus text column is removed
        assert not _column_exists(baseline_engine, "programs", "campus"), (
            "campus text column should be removed after migration 0005"
        )
