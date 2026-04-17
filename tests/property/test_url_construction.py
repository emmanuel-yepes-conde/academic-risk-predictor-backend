# Feature: postgresql-database-integration, Property 1: DATABASE_URL construction
"""
Property-based tests for automatic DATABASE_URL construction in Settings.

Validates: Requirements 2.1, 2.4
"""

import os
from unittest.mock import patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.core.config import Settings

# Safe alphabet: alphanumeric only to avoid URL encoding issues
SAFE_ALPHABET = st.characters(whitelist_categories=("Lu", "Ll", "Nd"))

safe_text = st.text(
    alphabet=SAFE_ALPHABET,
    min_size=1,
    max_size=30,
)


@h_settings(max_examples=100)
@given(
    user=safe_text,
    password=safe_text,
    host=safe_text,
    port=st.integers(min_value=1024, max_value=65535),
    dbname=safe_text,
)
def test_database_url_construction(user: str, password: str, host: str, port: int, dbname: str):
    """
    **Validates: Requirements 2.1, 2.4**

    For any valid combination of DB_USER, DB_PASSWORD, DB_HOST, DB_PORT and DB_NAME,
    the DATABASE_URL built automatically by Settings must:
    - Start with 'postgresql+asyncpg://'
    - Contain exactly the provided user, password, host, port and dbname values
    """
    env_overrides = {
        "DB_USER": user,
        "DB_PASSWORD": password,
        "DB_HOST": host,
        "DB_PORT": str(port),
        "DB_NAME": dbname,
        # Ensure DATABASE_URL is not set so auto-construction is triggered
        "DATABASE_URL": "",
    }

    with patch.dict(os.environ, env_overrides, clear=False):
        # Remove DATABASE_URL from env if present so the validator builds it
        env_without_url = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict(os.environ, env_without_url, clear=True):
            s = Settings(
                DB_USER=user,
                DB_PASSWORD=password,
                DB_HOST=host,
                DB_PORT=port,
                DB_NAME=dbname,
                DATABASE_URL=None,
            )

    url = s.DATABASE_URL
    assert url is not None, "DATABASE_URL should not be None"
    assert url.startswith("postgresql+asyncpg://"), (
        f"Expected URL to start with 'postgresql+asyncpg://', got: {url}"
    )
    assert user in url, f"Expected user '{user}' in URL: {url}"
    assert password in url, f"Expected password '{password}' in URL: {url}"
    assert host in url, f"Expected host '{host}' in URL: {url}"
    assert str(port) in url, f"Expected port '{port}' in URL: {url}"
    assert dbname in url, f"Expected dbname '{dbname}' in URL: {url}"
    # Verify exact format
    expected = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"
    assert url == expected, f"Expected URL '{expected}', got '{url}'"
