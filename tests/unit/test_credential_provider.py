"""Unit tests for CredentialAuthProvider.

Tests cover:
- Valid credentials return the user (Req 1.1)
- Non-existent email raises AuthenticationError (Req 1.2)
- Wrong password raises AuthenticationError (Req 1.3)
- SSO-only user (no password_hash) raises AuthenticationError (Req 1.5)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.enums import RoleEnum, UserStatusEnum
from app.domain.exceptions import AuthenticationError
from app.infrastructure.auth.credential_provider import CredentialAuthProvider


def _make_user(
    *,
    email: str = "user@university.edu",
    password_hash: str | None = "$2b$12$hashedpasswordvalue",
    role: RoleEnum = RoleEnum.STUDENT,
    status: UserStatusEnum = UserStatusEnum.ACTIVE,
) -> MagicMock:
    """Create a mock User with the given attributes."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    user.password_hash = password_hash
    user.role = role
    user.status = status
    return user


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Return a mock IUserRepository."""
    return AsyncMock()


@pytest.fixture
def provider(mock_repo: AsyncMock) -> CredentialAuthProvider:
    """Return a CredentialAuthProvider wired to the mock repo."""
    return CredentialAuthProvider(mock_repo)


# ── Req 1.1: Valid credentials return user ──────────────────────────────


@pytest.mark.anyio
@patch("app.infrastructure.auth.credential_provider.verify_password", return_value=True)
async def test_valid_credentials_return_user(
    mock_verify: MagicMock,
    provider: CredentialAuthProvider,
    mock_repo: AsyncMock,
) -> None:
    user = _make_user()
    mock_repo.get_by_email.return_value = user

    result = await provider.authenticate(email="user@university.edu", password="correct")

    assert result is user
    mock_repo.get_by_email.assert_awaited_once_with("user@university.edu")
    mock_verify.assert_called_once_with("correct", user.password_hash)


# ── Req 1.2: Non-existent email raises AuthenticationError ──────────────


@pytest.mark.anyio
async def test_nonexistent_email_raises_authentication_error(
    provider: CredentialAuthProvider,
    mock_repo: AsyncMock,
) -> None:
    mock_repo.get_by_email.return_value = None

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.authenticate(email="unknown@university.edu", password="any")

    assert exc_info.value.message == "Credenciales inválidas"
    assert exc_info.value.status_code == 401


# ── Req 1.3: Wrong password raises AuthenticationError ──────────────────


@pytest.mark.anyio
@patch("app.infrastructure.auth.credential_provider.verify_password", return_value=False)
async def test_wrong_password_raises_authentication_error(
    mock_verify: MagicMock,
    provider: CredentialAuthProvider,
    mock_repo: AsyncMock,
) -> None:
    user = _make_user()
    mock_repo.get_by_email.return_value = user

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.authenticate(email="user@university.edu", password="wrong")

    assert exc_info.value.message == "Credenciales inválidas"
    assert exc_info.value.status_code == 401
    mock_verify.assert_called_once_with("wrong", user.password_hash)


# ── Req 1.5: SSO-only user (no password_hash) raises AuthenticationError


@pytest.mark.anyio
async def test_sso_only_user_raises_authentication_error(
    provider: CredentialAuthProvider,
    mock_repo: AsyncMock,
) -> None:
    user = _make_user(password_hash=None)
    mock_repo.get_by_email.return_value = user

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.authenticate(email="sso@university.edu", password="any")

    assert exc_info.value.message == "Credenciales inválidas"
    assert exc_info.value.status_code == 401


# ── Edge: empty password_hash string treated as missing ─────────────────


@pytest.mark.anyio
async def test_empty_password_hash_raises_authentication_error(
    provider: CredentialAuthProvider,
    mock_repo: AsyncMock,
) -> None:
    user = _make_user(password_hash="")
    mock_repo.get_by_email.return_value = user

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.authenticate(email="user@university.edu", password="any")

    assert exc_info.value.message == "Credenciales inválidas"
    assert exc_info.value.status_code == 401


# ── Edge: missing email or password kwargs ──────────────────────────────


@pytest.mark.anyio
async def test_missing_email_raises_authentication_error(
    provider: CredentialAuthProvider,
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        await provider.authenticate(password="secret")

    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_missing_password_raises_authentication_error(
    provider: CredentialAuthProvider,
) -> None:
    with pytest.raises(AuthenticationError) as exc_info:
        await provider.authenticate(email="user@university.edu")

    assert exc_info.value.status_code == 401
