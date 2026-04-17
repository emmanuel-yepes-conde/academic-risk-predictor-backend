"""
Tests unitarios para app/core/config.py
Verifica la construcción automática de DATABASE_URL y el uso directo cuando está definida.
Requisitos: 2.1, 2.4
"""

import os

import pytest
from app.core.config import Settings


def make_settings(**kwargs) -> Settings:
    """Helper para crear Settings con valores controlados, sin leer .env."""
    base = dict(
        DB_USER="testuser",
        DB_PASSWORD="testpass",
        DB_HOST="testhost",
        DB_PORT=5432,
        DB_NAME="testdb",
    )
    base.update(kwargs)
    return Settings.model_validate(base)


class TestDatabaseURLConstruction:
    """Propiedad 1 (unitaria): DATABASE_URL se construye a partir de campos individuales."""

    @pytest.fixture(autouse=True)
    def _clear_database_url_env(self, monkeypatch):
        """Elimina DATABASE_URL del entorno para que no interfiera con la construcción dinámica."""
        monkeypatch.delenv("DATABASE_URL", raising=False)

    def test_url_format(self):
        """La URL construida tiene el prefijo postgresql+asyncpg://."""
        s = make_settings()
        assert s.DATABASE_URL.startswith("postgresql+asyncpg://")

    def test_url_contains_user(self):
        s = make_settings(DB_USER="alice")
        assert "alice:" in s.DATABASE_URL

    def test_url_contains_password(self):
        s = make_settings(DB_PASSWORD="s3cr3t")
        assert "s3cr3t@" in s.DATABASE_URL

    def test_url_contains_host(self):
        s = make_settings(DB_HOST="db.example.com")
        assert "@db.example.com:" in s.DATABASE_URL

    def test_url_contains_port(self):
        s = make_settings(DB_PORT=5433)
        assert ":5433/" in s.DATABASE_URL

    def test_url_contains_dbname(self):
        s = make_settings(DB_NAME="mydb")
        assert s.DATABASE_URL.endswith("/mydb")

    def test_full_url_format(self):
        """La URL completa sigue el formato esperado."""
        s = make_settings(
            DB_USER="u",
            DB_PASSWORD="p",
            DB_HOST="h",
            DB_PORT=1234,
            DB_NAME="d",
        )
        assert s.DATABASE_URL == "postgresql+asyncpg://u:p@h:1234/d"


class TestDatabaseURLPassthrough:
    """Requisito 2.4: si DATABASE_URL está definida en el entorno, se usa directamente."""

    def test_explicit_url_is_used_as_is(self):
        explicit = "postgresql+asyncpg://custom_user:custom_pass@custom_host:9999/custom_db"
        s = make_settings(DATABASE_URL=explicit)
        assert s.DATABASE_URL == explicit

    def test_explicit_url_not_overwritten_by_individual_fields(self):
        """Los campos individuales no deben sobreescribir una DATABASE_URL ya definida."""
        explicit = "postgresql+asyncpg://a:b@c:1111/d"
        s = make_settings(
            DATABASE_URL=explicit,
            DB_USER="other_user",
            DB_HOST="other_host",
        )
        assert s.DATABASE_URL == explicit

    def test_explicit_url_different_scheme_preserved(self):
        """Una URL con esquema diferente se preserva sin modificación."""
        explicit = "postgresql://sync_user:pass@host:5432/db"
        s = make_settings(DATABASE_URL=explicit)
        assert s.DATABASE_URL == explicit
