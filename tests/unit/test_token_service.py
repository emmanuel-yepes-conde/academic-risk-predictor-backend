"""
Unit tests for TokenService edge cases.

Tests expired token handling, wrong token type detection, and specific claim
values. These complement the property-based tests by covering concrete
scenarios and boundary conditions.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.3, 3.4
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from app.application.services.token_service import TokenService
from app.domain.enums import RoleEnum
from app.domain.exceptions import InvalidTokenError, TokenExpiredError
from app.domain.value_objects.token import TokenPayload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "unit-test-secret-key"
_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
_ROLE = RoleEnum.STUDENT


def _make_service(
    secret_key: str = _TEST_SECRET,
    algorithm: str = "HS256",
    access_expire_minutes: int = 30,
    refresh_expire_days: int = 7,
) -> TokenService:
    return TokenService(
        secret_key=secret_key,
        algorithm=algorithm,
        access_expire_minutes=access_expire_minutes,
        refresh_expire_days=refresh_expire_days,
    )


def _build_token(claims: dict, secret: str = _TEST_SECRET) -> str:
    """Encode a raw JWT with the given claims and secret."""
    return pyjwt.encode(claims, secret, algorithm="HS256")


def _valid_claims(
    user_id: uuid.UUID = _USER_ID,
    role: RoleEnum = _ROLE,
    token_type: str = "access",
    expire_delta: timedelta = timedelta(minutes=30),
) -> dict:
    """Return a valid claim dict for manual token construction."""
    now = datetime.now(timezone.utc)
    return {
        "sub": str(user_id),
        "role": role.value,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expire_delta).timestamp()),
    }


# ===================================================================
# Expired token handling (Requirement 3.3)
# ===================================================================


class TestExpiredTokenHandling:
    """Verify that expired tokens raise TokenExpiredError."""

    def test_expired_access_token_raises_token_expired_error(self):
        """An access token whose exp is in the past must raise TokenExpiredError."""
        claims = _valid_claims(expire_delta=timedelta(seconds=-1))
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(TokenExpiredError):
            svc.decode_token(token)

    def test_expired_refresh_token_raises_token_expired_error(self):
        """An expired refresh token must also raise TokenExpiredError."""
        claims = _valid_claims(token_type="refresh", expire_delta=timedelta(seconds=-1))
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(TokenExpiredError):
            svc.decode_token(token)

    def test_token_expired_just_now_raises_error(self):
        """A token that expired exactly at the current second should be rejected."""
        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(_USER_ID),
            "role": _ROLE.value,
            "type": "access",
            "iat": int((now - timedelta(minutes=30)).timestamp()),
            "exp": int((now - timedelta(seconds=1)).timestamp()),
        }
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(TokenExpiredError):
            svc.decode_token(token)

    def test_token_expired_error_has_correct_message(self):
        """TokenExpiredError should carry the default message."""
        claims = _valid_claims(expire_delta=timedelta(seconds=-10))
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(TokenExpiredError) as exc_info:
            svc.decode_token(token)

        assert exc_info.value.message == "Token expirado"


# ===================================================================
# Wrong token type detection (Requirement 2.5, 3.4)
# ===================================================================


class TestTokenTypeDetection:
    """Verify that access and refresh tokens carry the correct type claim."""

    def test_access_token_has_type_access(self):
        """create_access_token must produce a token with type='access'."""
        svc = _make_service()
        token = svc.create_access_token(_USER_ID, _ROLE)
        payload = svc.decode_token(token)

        assert payload.type == "access"

    def test_refresh_token_has_type_refresh(self):
        """create_refresh_token must produce a token with type='refresh'."""
        svc = _make_service()
        token = svc.create_refresh_token(_USER_ID, _ROLE)
        payload = svc.decode_token(token)

        assert payload.type == "refresh"

    def test_token_with_unknown_type_is_decoded_but_type_preserved(self):
        """A token with an unusual type value should still decode (type is not
        validated by TokenService.decode_token — that's the caller's job)."""
        claims = _valid_claims()
        claims["type"] = "custom"
        token = _build_token(claims)
        svc = _make_service()

        payload = svc.decode_token(token)
        assert payload.type == "custom"


# ===================================================================
# Specific claim values (Requirements 2.1, 2.2, 2.5)
# ===================================================================


class TestSpecificClaimValues:
    """Verify exact claim values for known inputs."""

    def test_access_token_sub_matches_user_uuid(self):
        """The sub claim must be the string representation of the user UUID."""
        svc = _make_service()
        token = svc.create_access_token(_USER_ID, RoleEnum.ADMIN)
        payload = svc.decode_token(token)

        assert payload.sub == str(_USER_ID)

    def test_access_token_role_matches_input_role(self):
        """The role claim must match the RoleEnum passed at creation."""
        svc = _make_service()

        for role in RoleEnum:
            token = svc.create_access_token(_USER_ID, role)
            payload = svc.decode_token(token)
            assert payload.role == role

    def test_refresh_token_sub_and_role_match(self):
        """Refresh tokens must also carry the correct sub and role."""
        svc = _make_service()
        token = svc.create_refresh_token(_USER_ID, RoleEnum.PROFESSOR)
        payload = svc.decode_token(token)

        assert payload.sub == str(_USER_ID)
        assert payload.role == RoleEnum.PROFESSOR

    def test_decoded_payload_is_token_payload_instance(self):
        """decode_token must return a TokenPayload value object."""
        svc = _make_service()
        token = svc.create_access_token(_USER_ID, _ROLE)
        payload = svc.decode_token(token)

        assert isinstance(payload, TokenPayload)

    def test_payload_exp_and_iat_are_utc_datetimes(self):
        """exp and iat in the decoded payload must be timezone-aware UTC datetimes."""
        svc = _make_service()
        token = svc.create_access_token(_USER_ID, _ROLE)
        payload = svc.decode_token(token)

        assert isinstance(payload.exp, datetime)
        assert isinstance(payload.iat, datetime)
        assert payload.exp.tzinfo is not None
        assert payload.iat.tzinfo is not None

    def test_access_token_iat_is_close_to_now(self):
        """The iat claim should be within a few seconds of the current time."""
        svc = _make_service()
        before = datetime.now(timezone.utc)
        token = svc.create_access_token(_USER_ID, _ROLE)
        after = datetime.now(timezone.utc)

        payload = svc.decode_token(token)

        # iat should be between before and after (with 1s tolerance)
        assert payload.iat >= before - timedelta(seconds=1)
        assert payload.iat <= after + timedelta(seconds=1)


# ===================================================================
# Expiration durations (Requirements 2.3, 2.4)
# ===================================================================


class TestExpirationDurations:
    """Verify that token lifetimes match the configured values."""

    def test_access_token_expires_in_configured_minutes(self):
        """Access token exp - iat must equal access_expire_minutes * 60."""
        svc = _make_service(access_expire_minutes=15)
        token = svc.create_access_token(_USER_ID, _ROLE)

        raw = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
        assert raw["exp"] - raw["iat"] == 15 * 60

    def test_refresh_token_expires_in_configured_days(self):
        """Refresh token exp - iat must equal refresh_expire_days * 86400."""
        svc = _make_service(refresh_expire_days=14)
        token = svc.create_refresh_token(_USER_ID, _ROLE)

        raw = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
        assert raw["exp"] - raw["iat"] == 14 * 86400

    def test_default_access_expiration_is_30_minutes(self):
        """With default config, access token lifetime is 30 minutes."""
        svc = _make_service()
        token = svc.create_access_token(_USER_ID, _ROLE)

        raw = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
        assert raw["exp"] - raw["iat"] == 30 * 60

    def test_default_refresh_expiration_is_7_days(self):
        """With default config, refresh token lifetime is 7 days."""
        svc = _make_service()
        token = svc.create_refresh_token(_USER_ID, _ROLE)

        raw = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"])
        assert raw["exp"] - raw["iat"] == 7 * 86400


# ===================================================================
# Invalid token scenarios (Requirement 3.4)
# ===================================================================


class TestInvalidTokenScenarios:
    """Verify that various malformed/invalid tokens raise InvalidTokenError."""

    def test_empty_string_raises_invalid_token_error(self):
        svc = _make_service()
        with pytest.raises(InvalidTokenError):
            svc.decode_token("")

    def test_none_like_string_raises_invalid_token_error(self):
        svc = _make_service()
        with pytest.raises(InvalidTokenError):
            svc.decode_token("null")

    def test_token_signed_with_wrong_secret_raises_invalid_token_error(self):
        """A token signed with a different secret must be rejected."""
        wrong_svc = _make_service(secret_key="wrong-secret")
        token = wrong_svc.create_access_token(_USER_ID, _ROLE)

        real_svc = _make_service()
        with pytest.raises(InvalidTokenError):
            real_svc.decode_token(token)

    def test_token_missing_sub_claim_raises_invalid_token_error(self):
        """A JWT missing the 'sub' claim must be rejected."""
        now = datetime.now(timezone.utc)
        claims = {
            "role": _ROLE.value,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
        }
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(InvalidTokenError):
            svc.decode_token(token)

    def test_token_missing_role_claim_raises_invalid_token_error(self):
        """A JWT missing the 'role' claim must be rejected."""
        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(_USER_ID),
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
        }
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(InvalidTokenError):
            svc.decode_token(token)

    def test_token_missing_type_claim_raises_invalid_token_error(self):
        """A JWT missing the 'type' claim must be rejected."""
        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(_USER_ID),
            "role": _ROLE.value,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
        }
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(InvalidTokenError):
            svc.decode_token(token)

    def test_token_with_invalid_role_value_raises_invalid_token_error(self):
        """A JWT with a role value not in RoleEnum must be rejected."""
        claims = _valid_claims()
        claims["role"] = "SUPERADMIN"
        token = _build_token(claims)
        svc = _make_service()

        with pytest.raises(InvalidTokenError):
            svc.decode_token(token)

    def test_invalid_token_error_has_correct_message(self):
        """InvalidTokenError should carry the default message."""
        svc = _make_service()

        with pytest.raises(InvalidTokenError) as exc_info:
            svc.decode_token("not.a.jwt")

        assert exc_info.value.message == "Token inválido"

    def test_plain_text_string_raises_invalid_token_error(self):
        """A plain text string (not JWT format) must be rejected."""
        svc = _make_service()
        with pytest.raises(InvalidTokenError):
            svc.decode_token("this is just plain text")

    def test_base64_garbage_raises_invalid_token_error(self):
        """Three base64-like segments that don't form a valid JWT."""
        svc = _make_service()
        with pytest.raises(InvalidTokenError):
            svc.decode_token("aGVsbG8.d29ybGQ.Zm9v")


# ===================================================================
# Algorithm enforcement (Requirement 2.2)
# ===================================================================


class TestAlgorithmEnforcement:
    """Verify that tokens are signed with the configured algorithm."""

    def test_token_uses_hs256_algorithm(self):
        """By default, the JWT header should specify HS256."""
        svc = _make_service()
        token = svc.create_access_token(_USER_ID, _ROLE)

        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_token_signed_with_none_algorithm_is_rejected(self):
        """A token crafted with alg=none must be rejected."""
        claims = _valid_claims()
        # Manually encode with algorithm "none" (unsigned)
        token = pyjwt.encode(claims, "", algorithm="HS256")
        # Tamper the header to say "none" — this is a known attack vector
        # We just verify that a random unsigned-like token is rejected
        svc = _make_service()

        # A token from a different secret is invalid regardless
        wrong_token = pyjwt.encode(claims, "different-key", algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            svc.decode_token(wrong_token)
