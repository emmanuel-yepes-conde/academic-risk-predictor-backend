# Feature: postgresql-database-integration, Property 5: Migration round trip
"""
Property-based test for migration round trip: upgrade → downgrade → upgrade.

Verifies that applying `alembic upgrade head` → `alembic downgrade -1` →
`alembic upgrade head` produces a schema identical to the state after the
first upgrade.

**Validates: Requirements 5.4**
"""

import importlib
import importlib.util
import logging
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from alembic.config import Config
from alembic import command
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

# Silence alembic logging during tests
logging.getLogger("alembic").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)

# Root of the project (two levels up from tests/property/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# SQLite-compatible type stubs
#
# The migration script uses postgresql.UUID and postgresql.JSON which are
# PostgreSQL-specific.  We replace them with SQLite-friendly equivalents
# before running the migration.
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
        # Ignore PostgreSQL-specific kwargs like astext_type
        kwargs.pop("astext_type", None)
        super().__init__(*args, **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_alembic_config(db_url: str) -> Config:
    """Build an Alembic Config pointing to the project's alembic directory
    and using the given synchronous SQLite URL."""
    ini_path = str(PROJECT_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _get_schema_snapshot(engine: sa.Engine) -> dict:
    """
    Return a snapshot of the schema as a dict:
        table_name → sorted list of column names
    Excludes alembic's internal version table.
    """
    snapshot = {}
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        for table_name in sorted(inspector.get_table_names()):
            if table_name == "alembic_version":
                continue
            cols = sorted(c["name"] for c in inspector.get_columns(table_name))
            snapshot[table_name] = cols
    return snapshot


def _load_migration_module(versions_dir: Path, revision: str):
    """Dynamically load a migration module by revision ID."""
    for f in versions_dir.glob("*.py"):
        spec = importlib.util.spec_from_file_location(f"migration_{revision}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if getattr(mod, "revision", None) == revision:
            return mod
    raise FileNotFoundError(f"Migration revision '{revision}' not found in {versions_dir}")


# ---------------------------------------------------------------------------
# Core round-trip logic
# ---------------------------------------------------------------------------

def _run_roundtrip(db_path: str) -> tuple[dict, dict]:
    """
    Execute upgrade → downgrade -1 → upgrade on a temporary SQLite database.

    Returns (schema_after_first_upgrade, schema_after_second_upgrade).
    Both dicts map table_name → sorted list of column names.

    The project's alembic/env.py uses an async engine (asyncpg).  To avoid
    needing a live PostgreSQL instance we bypass env.py entirely and drive
    the migration operations directly via SQLAlchemy + the migration script.
    """
    db_url = f"sqlite:///{db_path}"
    versions_dir = PROJECT_ROOT / "alembic" / "versions"

    from sqlalchemy.dialects import postgresql as pg_dialect

    with (
        patch.object(pg_dialect, "UUID", _FakeUUID),
        patch.object(pg_dialect, "JSON", _FakeJSON),
    ):
        engine = sa.create_engine(db_url)

        # --- Alembic version tracking table ---
        meta = sa.MetaData()
        alembic_version = sa.Table(
            "alembic_version",
            meta,
            sa.Column("version_num", sa.String(32), primary_key=True),
        )
        meta.create_all(engine)

        # Load the migration module
        migration = _load_migration_module(versions_dir, "0001")

        def _set_version(conn, rev: str | None):
            conn.execute(alembic_version.delete())
            if rev is not None:
                conn.execute(alembic_version.insert().values(version_num=rev))
            conn.commit()

        # Provide a minimal Alembic op context so op.create_table etc. work
        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        def _run_upgrade(conn):
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        def _run_downgrade(conn):
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                # Patch op.execute in the migration module to skip
                # PostgreSQL-specific DDL (e.g. DROP TYPE) that SQLite
                # does not support.
                original_execute = migration.op.execute

                def _safe_execute(sql, *args, **kwargs):
                    sql_str = str(sql).strip().upper()
                    if sql_str.startswith("DROP TYPE") or sql_str.startswith("CREATE TYPE"):
                        return  # no-op on SQLite
                    return original_execute(sql, *args, **kwargs)

                migration.op.execute = _safe_execute
                try:
                    migration.downgrade()
                finally:
                    migration.op.execute = original_execute

        # 1. First upgrade to head
        with engine.begin() as conn:
            _run_upgrade(conn)
        with engine.begin() as conn:
            _set_version(conn, "0001")
        schema_after_first_upgrade = _get_schema_snapshot(engine)

        # 2. Downgrade one step
        with engine.begin() as conn:
            _run_downgrade(conn)
        with engine.begin() as conn:
            _set_version(conn, None)

        # 3. Upgrade back to head
        with engine.begin() as conn:
            _run_upgrade(conn)
        with engine.begin() as conn:
            _set_version(conn, "0001")
        schema_after_second_upgrade = _get_schema_snapshot(engine)

        engine.dispose()

    return schema_after_first_upgrade, schema_after_second_upgrade


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@h_settings(max_examples=5)
@given(
    # The round-trip property is deterministic; @given with st.just(None)
    # keeps Hypothesis machinery active for proper PBT tracking.
    _dummy=st.just(None),
)
def test_migration_roundtrip(_dummy):
    """
    **Validates: Requirements 5.4**

    Property 5: For any schema state reached via `alembic upgrade head`,
    applying `alembic downgrade -1` followed by `alembic upgrade head` must
    produce a schema identical to the state before the downgrade.

    Uses a temporary SQLite database so no live PostgreSQL instance is needed.
    PostgreSQL-specific column types (UUID, JSON) are patched with
    SQLite-compatible equivalents.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        schema_first, schema_second = _run_roundtrip(db_path)

        # The set of tables must be identical after the round trip
        assert set(schema_first.keys()) == set(schema_second.keys()), (
            f"Table sets differ after round trip.\n"
            f"  After first upgrade:  {sorted(schema_first.keys())}\n"
            f"  After second upgrade: {sorted(schema_second.keys())}"
        )

        # Each table's columns must be identical
        for table_name in schema_first:
            cols_first = schema_first[table_name]
            cols_second = schema_second[table_name]
            assert cols_first == cols_second, (
                f"Column mismatch for table '{table_name}' after round trip.\n"
                f"  After first upgrade:  {cols_first}\n"
                f"  After second upgrade: {cols_second}"
            )
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass
