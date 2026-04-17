# Feature: jwt-role-authentication, Property 4: Invalid Tokens Are Always Rejected
"""
Property-based tests for invalid token rejection.

**Property 4 — Invalid Tokens Are Always Rejected (Validates: Requirements 3.4, 3.6):**
For any string that is not a valid JWT signed with the configured
``JWT_SECRET_KEY`` (including random strings, tokens signed with a different
key, and structurally malformed tokens), ``TokenService.decode_token`` SHALL
raise an ``InvalidTokenError``.
"""

import uuid

import jwt as pyjwt
import pytest
from hypothesis import given, assume
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.application.services.token_service import TokenService
from app.domain.enums import RoleEnum
from app.domain.exceptions import InvalidTokenError

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

user_id_strategy = st.uuids()
role_strategy = st.sampled_from(list(RoleEnum))

# Random strings that are unlikely to be valid JWTs
random_string_strategy = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N", "P", "S", "Z")),
    min_size=0,
    max_size=500,
)

# Secret keys that differ from the test secret
different_secret_strategy = st.text(
    alphabet=st.characters(codec="utf-8", categories=("L", "N")),
    min_size=1,
    max_size=100,
).filter(lambda s: s != "test-secret-key-for-property-tests")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-secret-key-for-property-tests"


def _make_token_service() -> TokenService:
    """Return a TokenService configured with deterministic test settings."""
    return TokenService(
        secret_key=_TEST_SECRET,
        algorithm="HS256",
        access_expire_minutes=30,
        refresh_expire_days=7,
    )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@h_settings(max_examples=100)
@given(random_input=random_string_strategy)
def test_random_strings_are_rejected(random_input: str):
    """
    **Validates: Requirements 3.4**

    Property 4 (random strings): For any arbitrary string, decode_token
    SHALL raise InvalidTokenError. Random strings are not valid JWTs.
    """
    svc = _make_token_service()

    with pytest.raises(InvalidTokenError):
        svc.decode_token(random_input)


@h_settings(max_examples=100)
@given(
    user_id=user_id_strategy,
    role=role_strategy,
    wrong_secret=different_secret_strategy,
)
def test_tokens_signed_with_different_key_are_rejected(
    user_id: uuid.UUID,
    role: RoleEnum,
    wrong_secret: str,
):
    """
    **Validates: Requirements 3.6**

    Property 4 (wrong key): For any valid user (UUID, RoleEnum) and any
    secret key that differs from the configured ``JWT_SECRET_KEY``, a token
    signed with the wrong key SHALL be rejected with InvalidTokenError.
    """
    # Create a token service with the wrong secret
    wrong_svc = TokenService(
        secret_key=wrong_secret,
        algorithm="HS256",
        access_expire_minutes=30,
        refresh_expire_days=7,
    )
    token = wrong_svc.create_access_token(user_id, role)

    # The real service must reject it
    real_svc = _make_token_service()

    with pytest.raises(InvalidTokenError):
        real_svc.decode_token(token)


@h_settings(max_examples=100)
@given(
    user_id=user_id_strategy,
    role=role_strategy,
    wrong_secret=different_secret_strategy,
)
def test_refresh_tokens_signed_with_different_key_are_rejected(
    user_id: uuid.UUID,
    role: RoleEnum,
    wrong_secret: str,
):
    """
    **Validates: Requirements 3.6**

    Property 4 (wrong key, refresh): For any valid user and any different
    secret key, a refresh token signed with the wrong key SHALL be rejected
    with InvalidTokenError.
    """
    wrong_svc = TokenService(
        secret_key=wrong_secret,
        algorithm="HS256",
        access_expire_minutes=30,
        refresh_expire_days=7,
    )
    token = wrong_svc.create_refresh_token(user_id, role)

    real_svc = _make_token_service()

    with pytest.raises(InvalidTokenError):
        real_svc.decode_token(token)


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_tampered_token_payload_is_rejected(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 3.4**

    Property 4 (tampered payload): For any valid token, modifying the
    payload portion (middle segment) SHALL cause decode_token to raise
    InvalidTokenError because the signature no longer matches.
    """
    svc = _make_token_service()
    token = svc.create_access_token(user_id, role)

    parts = token.split(".")
    assume(len(parts) == 3)

    # Reverse the payload segment to tamper with it
    tampered_payload = parts[1][::-1] if parts[1] else "dGFtcGVyZWQ"
    # Only proceed if the tampered payload actually differs
    assume(tampered_payload != parts[1])

    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

    with pytest.raises(InvalidTokenError):
        svc.decode_token(tampered_token)


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_token_with_missing_segment_is_rejected(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 3.4**

    Property 4 (malformed structure): For any valid token, removing one of
    the three JWT segments (header.payload.signature) SHALL cause
    decode_token to raise InvalidTokenError.
    """
    svc = _make_token_service()
    token = svc.create_access_token(user_id, role)

    parts = token.split(".")
    assume(len(parts) == 3)

    # Test with only header.payload (missing signature)
    no_signature = f"{parts[0]}.{parts[1]}"
    with pytest.raises(InvalidTokenError):
        svc.decode_token(no_signature)

    # Test with only header (missing payload and signature)
    header_only = parts[0]
    with pytest.raises(InvalidTokenError):
        svc.decode_token(header_only)


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_token_with_extra_segment_is_rejected(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 3.4**

    Property 4 (extra segment): For any valid token, adding an extra
    dot-separated segment SHALL cause decode_token to raise
    InvalidTokenError because the JWT structure is malformed.
    """
    svc = _make_token_service()
    token = svc.create_access_token(user_id, role)

    # Add a fourth segment — JWTs must have exactly 3 segments
    corrupted_token = token + ".extrasegment"

    with pytest.raises(InvalidTokenError):
        svc.decode_token(corrupted_token)


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_token_with_missing_claims_is_rejected(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 3.4**

    Property 4 (incomplete claims): For any user, a JWT that is properly
    signed but missing required claims (sub, role, type, exp, iat) SHALL
    be rejected with InvalidTokenError.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    # Token missing 'role' and 'type' claims
    incomplete_claims = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    token = pyjwt.encode(incomplete_claims, _TEST_SECRET, algorithm="HS256")

    svc = _make_token_service()

    with pytest.raises(InvalidTokenError):
        svc.decode_token(token)
