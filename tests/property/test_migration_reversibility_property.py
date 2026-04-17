# Feature: multi-university-support, Property 16: Reversibilidad de la migración
"""
Property-based test for migration 0004 reversibility.

Verifies that for any database state with data in `programs` and `courses`,
applying migration 0004 (upgrade) and then reverting it (downgrade) restores
the schema to the pre-0004 state without loss of records in `programs` or
`courses`.

The test uses a temporary SQLite database and patches PostgreSQL-specific
types (UUID, JSON) with SQLite-compatible equivalents. Each migration in the
chain (0001 → 0002 → 0003 → 0004) is loaded and executed directly via
Alembic Operations to avoid needing a live PostgreSQL instance.

SQLite does not support ALTER TABLE for constraints, so we patch several
Alembic operations (create_unique_constraint, drop_constraint,
create_foreign_key, drop_index on missing indexes) to be safe no-ops when
running on SQLite.

**Validates: Requirements 7.4**
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

import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

# Silence alembic/sqlalchemy logging during tests
logging.getLogger("alembic").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERSIONS_DIR = PROJECT_ROOT / "alembic" / "versions"


# ---------------------------------------------------------------------------
# SQLite-compatible type stubs (same approach as test_migration_roundtrip.py)
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
    Context manager that patches Alembic operations that are unsupported on
    SQLite (constraint ALTER, DROP TYPE, CREATE TYPE) to be safe no-ops.

    This allows running PostgreSQL-targeted migrations on SQLite for schema
    verification purposes.
    """
    original_create_unique = alembic_op.create_unique_constraint
    original_drop_constraint = alembic_op.drop_constraint
    original_create_fk = alembic_op.create_foreign_key
    original_drop_index = alembic_op.drop_index
    original_execute = alembic_op.execute
    original_alter_column = alembic_op.alter_column

    def _safe_create_unique(*args, **kwargs):
        """No-op: SQLite doesn't support adding constraints via ALTER."""
        pass

    def _safe_drop_constraint(*args, **kwargs):
        """No-op: SQLite doesn't support dropping constraints via ALTER."""
        pass

    def _safe_create_fk(*args, **kwargs):
        """No-op: SQLite doesn't support adding FK constraints via ALTER."""
        pass

    def _safe_drop_index(index_name, *args, **kwargs):
        """Try to drop the index; silently ignore if it doesn't exist."""
        try:
            original_drop_index(index_name, *args, **kwargs)
        except Exception:
            pass

    def _safe_execute(sql, *args, **kwargs):
        """Skip PostgreSQL-specific DDL (CREATE TYPE, DROP TYPE)."""
        sql_str = str(sql).strip().upper()
        if sql_str.startswith("DROP TYPE") or sql_str.startswith("CREATE TYPE"):
            return
        return original_execute(sql, *args, **kwargs)

    def _safe_alter_column(table_name, column_name, **kwargs):
        """
        SQLite doesn't support most ALTER COLUMN operations.
        We allow nullable changes by ignoring them (the column already exists).
        """
        # For SQLite, we just skip ALTER COLUMN — the column is already there
        # with the right type from create_table or add_column.
        pass

    alembic_op.create_unique_constraint = _safe_create_unique
    alembic_op.drop_constraint = _safe_drop_constraint
    alembic_op.create_foreign_key = _safe_create_fk
    alembic_op.drop_index = _safe_drop_index
    alembic_op.execute = _safe_execute
    alembic_op.alter_column = _safe_alter_column

    try:
        yield
    finally:
        alembic_op.create_unique_constraint = original_create_unique
        alembic_op.drop_constraint = original_drop_constraint
        alembic_op.create_foreign_key = original_create_fk
        alembic_op.drop_index = original_drop_index
        alembic_op.execute = original_execute
        alembic_op.alter_column = original_alter_column


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
    """
    Return a snapshot of the schema: table_name → sorted list of column names.
    Excludes alembic's internal version table.
    """
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


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Number of programs to seed (1–5)
num_programs_st = st.integers(min_value=1, max_value=5)

# Number of courses to seed (1–8)
num_courses_st = st.integers(min_value=1, max_value=8)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@h_settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
@given(
    num_programs=num_programs_st,
    num_courses=num_courses_st,
)
def test_migration_0004_reversibility(num_programs: int, num_courses: int):
    """
    Property 16: Reversibilidad de la migración.

    For any database state with programs and courses, applying migration 0004
    (upgrade) and then reverting it (downgrade) must restore the schema to the
    pre-0004 state without loss of records in `programs` or `courses`.

    Steps:
    1. Apply migrations 0001 → 0002 → 0003 to establish baseline schema.
    2. Seed programs and courses with test data.
    3. Snapshot the schema and record counts (pre-0004 state).
    4. Apply migration 0004 (upgrade).
    5. Verify the schema has the expected new structures (universities table,
       university_id column on programs).
    6. Apply migration 0004 (downgrade).
    7. Verify the schema matches the pre-0004 snapshot.
    8. Verify no records were lost in programs or courses.

    **Validates: Requirements 7.4**
    """
    from sqlalchemy.dialects import postgresql as pg_dialect

    with (
        patch.object(pg_dialect, "UUID", _FakeUUID),
        patch.object(pg_dialect, "JSON", _FakeJSON),
    ):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            db_url = f"sqlite:///{db_path}"
            engine = sa.create_engine(db_url)

            # Disable FK enforcement for SQLite (mirrors integration conftest)
            with engine.connect() as conn:
                conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
                conn.commit()

            # Load all migration modules
            m0001 = _load_migration("0001")
            m0002 = _load_migration("0002")
            m0003 = _load_migration("0003")
            m0004 = _load_migration("0004")

            # ---------------------------------------------------------------
            # Step 1: Apply migrations 0001 → 0002 → 0003
            # ---------------------------------------------------------------
            _run_with_ops(engine, m0001, "upgrade")
            _run_with_ops(engine, m0002, "upgrade")
            _run_with_ops(engine, m0003, "upgrade")

            # ---------------------------------------------------------------
            # Step 2: Seed programs and courses
            # ---------------------------------------------------------------
            now = datetime.now(timezone.utc).isoformat()
            default_uni_id = str(uuid.uuid4())

            program_ids = []
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
                            "code": f"PROG{i:04d}",
                            "name": f"Program {i}",
                            "pensum": f"PEN{i:04d}",
                            "grp": f"GRP{i}",
                            "loc": f"LOC-{i}",
                            "snies": 10000 + i,
                            "created": now,
                        },
                    )

                for j in range(num_courses):
                    cid = str(uuid.uuid4())
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
                            "code": f"CRS{j:04d}",
                            "name": f"Course {j}",
                            "credits": 3,
                            "period": "2025-1",
                            "program_id": target_program,
                            "created": now,
                        },
                    )

            # ---------------------------------------------------------------
            # Step 3: Snapshot pre-0004 state
            # ---------------------------------------------------------------
            schema_before_0004 = _get_schema_snapshot(engine)
            programs_before = _get_all_rows(engine, "programs")
            courses_before = _get_all_rows(engine, "courses")
            program_count_before = len(programs_before)
            course_count_before = len(courses_before)

            assert program_count_before == num_programs
            assert course_count_before == num_courses

            # ---------------------------------------------------------------
            # Step 4: Apply migration 0004 (upgrade)
            # ---------------------------------------------------------------
            # 0004 reads DEFAULT_UNIVERSITY_ID from env for data migration.
            # We also need the default university row to exist AFTER the
            # universities table is created by the migration. The migration
            # itself inserts the university_id into programs via UPDATE, so
            # we need to insert the university row between table creation
            # and the UPDATE. We achieve this by patching os.environ and
            # letting the migration's own logic handle the UPDATE.
            #
            # However, the migration creates the universities table and then
            # immediately does the UPDATE. We need the university row to
            # exist for the FK (but we have FKs disabled on SQLite), so the
            # UPDATE will work fine without the row existing.
            with patch.dict(
                os.environ, {"DEFAULT_UNIVERSITY_ID": default_uni_id}
            ):
                _run_with_ops(engine, m0004, "upgrade")

            # ---------------------------------------------------------------
            # Step 5: Verify post-upgrade schema
            # ---------------------------------------------------------------
            schema_after_upgrade = _get_schema_snapshot(engine)

            # universities table must exist after upgrade
            assert "universities" in schema_after_upgrade, (
                "Table 'universities' not found after migration 0004 upgrade"
            )

            # programs must have university_id column
            assert "university_id" in schema_after_upgrade["programs"], (
                "Column 'university_id' not found in programs after upgrade"
            )

            # All programs should have been assigned the default university
            programs_after_upgrade = _get_all_rows(engine, "programs")
            for prog in programs_after_upgrade:
                assert prog["university_id"] == default_uni_id, (
                    f"Program {prog['id']} was not assigned default university. "
                    f"Got university_id={prog['university_id']}"
                )

            # No programs or courses should be lost during upgrade
            assert len(programs_after_upgrade) == program_count_before, (
                f"Program count changed during upgrade: "
                f"before={program_count_before}, "
                f"after={len(programs_after_upgrade)}"
            )
            courses_after_upgrade = _get_all_rows(engine, "courses")
            assert len(courses_after_upgrade) == course_count_before, (
                f"Course count changed during upgrade: "
                f"before={course_count_before}, "
                f"after={len(courses_after_upgrade)}"
            )

            # ---------------------------------------------------------------
            # Step 6: Apply migration 0004 (downgrade)
            # ---------------------------------------------------------------
            _run_with_ops(engine, m0004, "downgrade")

            # ---------------------------------------------------------------
            # Step 7: Verify schema matches pre-0004 state
            # ---------------------------------------------------------------
            schema_after_downgrade = _get_schema_snapshot(engine)

            assert set(schema_before_0004.keys()) == set(
                schema_after_downgrade.keys()
            ), (
                f"Table sets differ after 0004 round trip.\n"
                f"  Before 0004: {sorted(schema_before_0004.keys())}\n"
                f"  After downgrade: {sorted(schema_after_downgrade.keys())}"
            )

            for table_name in schema_before_0004:
                cols_before = schema_before_0004[table_name]
                cols_after = schema_after_downgrade[table_name]
                assert cols_before == cols_after, (
                    f"Column mismatch for table '{table_name}' after 0004 "
                    f"round trip.\n"
                    f"  Before 0004: {cols_before}\n"
                    f"  After downgrade: {cols_after}"
                )

            # universities table must NOT exist after downgrade
            assert "universities" not in schema_after_downgrade, (
                "Table 'universities' still exists after migration 0004 "
                "downgrade"
            )

            # ---------------------------------------------------------------
            # Step 8: Verify no data loss in programs and courses
            # ---------------------------------------------------------------
            programs_after_downgrade = _get_all_rows(engine, "programs")
            courses_after_downgrade = _get_all_rows(engine, "courses")

            assert len(programs_after_downgrade) == program_count_before, (
                f"Program records lost during 0004 round trip: "
                f"before={program_count_before}, "
                f"after={len(programs_after_downgrade)}"
            )
            assert len(courses_after_downgrade) == course_count_before, (
                f"Course records lost during 0004 round trip: "
                f"before={course_count_before}, "
                f"after={len(courses_after_downgrade)}"
            )

            # Verify program data integrity (all original program IDs present)
            original_program_ids = {p["id"] for p in programs_before}
            restored_program_ids = {p["id"] for p in programs_after_downgrade}
            assert original_program_ids == restored_program_ids, (
                f"Program IDs differ after round trip.\n"
                f"  Lost: {original_program_ids - restored_program_ids}\n"
                f"  Extra: {restored_program_ids - original_program_ids}"
            )

            # Verify course data integrity (all original course IDs present)
            original_course_ids = {c["id"] for c in courses_before}
            restored_course_ids = {c["id"] for c in courses_after_downgrade}
            assert original_course_ids == restored_course_ids, (
                f"Course IDs differ after round trip.\n"
                f"  Lost: {original_course_ids - restored_course_ids}\n"
                f"  Extra: {restored_course_ids - original_course_ids}"
            )

            # Verify that program_code values are preserved
            original_codes = {p["program_code"] for p in programs_before}
            restored_codes = {
                p["program_code"] for p in programs_after_downgrade
            }
            assert original_codes == restored_codes, (
                f"Program codes differ after round trip.\n"
                f"  Lost: {original_codes - restored_codes}\n"
                f"  Extra: {restored_codes - original_codes}"
            )

            # Verify that course codes are preserved
            original_course_codes = {c["code"] for c in courses_before}
            restored_course_codes = {
                c["code"] for c in courses_after_downgrade
            }
            assert original_course_codes == restored_course_codes, (
                f"Course codes differ after round trip.\n"
                f"  Lost: {original_course_codes - restored_course_codes}\n"
                f"  Extra: {restored_course_codes - original_course_codes}"
            )

            # Verify university_id column is removed from programs after
            # downgrade (it should not be in the pre-0004 schema)
            assert "university_id" not in schema_after_downgrade.get(
                "programs", []
            ), (
                "Column 'university_id' still present in programs after "
                "migration 0004 downgrade"
            )

            engine.dispose()

        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass
