"""
Tests unitarios para la configuración JWT en app/core/config.py
Verifica valores por defecto, carga de variables de entorno y validación.
Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**kwargs) -> Settings:
    """Helper para crear Settings con valores controlados, sin leer .env."""
    base = dict(
        DB_USER="testuser",
        DB_PASSWORD="testpass",
        DB_HOST="testhost",
        DB_PORT=5432,
        DB_NAME="testdb",
        JWT_SECRET_KEY="test-secret-key-for-unit-tests",
    )
    base.update(kwargs)
    return Settings.model_validate(base)


class _SettingsNoEnv(Settings):
    """Settings subclass that ignores .env file, for testing missing-field validation."""

    model_config = {**Settings.model_config, "env_file": None}


class TestJWTDefaults:
    """Requisitos 7.2, 7.3, 7.4: valores por defecto de la configuración JWT."""

    def test_jwt_algorithm_default_is_hs256(self):
        """JWT_ALGORITHM tiene valor por defecto 'HS256'."""
        s = make_settings()
        assert s.JWT_ALGORITHM == "HS256"

    def test_access_token_expire_minutes_default_is_30(self):
        """ACCESS_TOKEN_EXPIRE_MINUTES tiene valor por defecto 30."""
        s = make_settings()
        assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 30

    def test_refresh_token_expire_days_default_is_7(self):
        """REFRESH_TOKEN_EXPIRE_DAYS tiene valor por defecto 7."""
        s = make_settings()
        assert s.REFRESH_TOKEN_EXPIRE_DAYS == 7


class TestJWTOverrides:
    """Requisitos 7.2, 7.3, 7.4: los valores se pueden sobreescribir."""

    def test_jwt_algorithm_override(self):
        s = make_settings(JWT_ALGORITHM="HS384")
        assert s.JWT_ALGORITHM == "HS384"

    def test_access_token_expire_minutes_override(self):
        s = make_settings(ACCESS_TOKEN_EXPIRE_MINUTES=60)
        assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 60

    def test_refresh_token_expire_days_override(self):
        s = make_settings(REFRESH_TOKEN_EXPIRE_DAYS=14)
        assert s.REFRESH_TOKEN_EXPIRE_DAYS == 14

    def test_jwt_secret_key_override(self):
        s = make_settings(JWT_SECRET_KEY="my-custom-secret")
        assert s.JWT_SECRET_KEY == "my-custom-secret"


class TestJWTSecretKeyRequired:
    """Requisito 7.1, 7.5: JWT_SECRET_KEY es obligatorio, sin valor por defecto."""

    def test_missing_jwt_secret_key_raises_validation_error(self, monkeypatch):
        """Si JWT_SECRET_KEY no está definido, Settings debe lanzar ValidationError."""
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            _SettingsNoEnv.model_validate(
                dict(
                    DB_USER="testuser",
                    DB_PASSWORD="testpass",
                    DB_HOST="testhost",
                    DB_PORT=5432,
                    DB_NAME="testdb",
                    # JWT_SECRET_KEY omitido intencionalmente
                )
            )
        errors = exc_info.value.errors()
        field_names = [e["loc"][-1] for e in errors]
        assert "JWT_SECRET_KEY" in field_names

    def test_jwt_secret_key_error_is_missing_type(self, monkeypatch):
        """El error para JWT_SECRET_KEY faltante debe ser de tipo 'missing'."""
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            _SettingsNoEnv.model_validate(
                dict(
                    DB_USER="testuser",
                    DB_PASSWORD="testpass",
                    DB_HOST="testhost",
                    DB_PORT=5432,
                    DB_NAME="testdb",
                )
            )
        errors = exc_info.value.errors()
        jwt_errors = [e for e in errors if "JWT_SECRET_KEY" in e["loc"]]
        assert len(jwt_errors) == 1
        assert jwt_errors[0]["type"] == "missing"
