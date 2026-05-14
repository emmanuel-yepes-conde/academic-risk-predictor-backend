# Feature: jwt-role-authentication, Property 1: JWT Encode-Decode Round Trip
# Feature: jwt-role-authentication, Property 2: Token Claims Completeness
"""
Property-based tests for the JWT encode-decode round trip and token claims
completeness.

**Property 1 — Round Trip (Validates: Requirements 2.6):**
Verifies that for any valid TokenPayload (with any valid UUID as ``sub``,
any RoleEnum value as ``role``, and token type "access" or "refresh"),
encoding the payload into a JWT string and then decoding it back produces
an equivalent TokenPayload with the same ``sub``, ``role``, and ``type``
values.

**Property 2 — Claims Completeness (Validates: Requirements 2.1, 2.5):**
Verifies that for any user (UUID, RoleEnum), created access tokens contain
exactly the claims ``sub``, ``role``, ``type`` (= "access"), ``exp``, and
``iat``; refresh tokens contain the same set with ``type`` = "refresh".
No extra claims are present.
"""

import uuid

import jwt as pyjwt
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.application.services.token_service import TokenService
from app.domain.enums import RoleEnum

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

user_id_strategy = st.uuids()
role_strategy = st.sampled_from(list(RoleEnum))
token_type_strategy = st.sampled_from(["access", "refresh"])

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
@given(user_id=user_id_strategy, role=role_strategy)
def test_access_token_roundtrip_preserves_claims(
    user_id: uuid.UUID, role: RoleEnum
):
    """
    **Validates: Requirements 2.6**

    Property 1 (access): For any valid UUID and RoleEnum, encoding an access
    token and then decoding it must produce a TokenPayload whose ``sub``
    matches the original UUID, ``role`` matches the original role, and
    ``type`` equals "access".
    """
    svc = _make_token_service()

    token = svc.create_access_token(user_id, role)
    payload = svc.decode_token(token)

    assert payload.sub == str(user_id)
    assert payload.role == role
    assert payload.type == "access"
    assert payload.exp is not None
    assert payload.iat is not None
    assert payload.exp > payload.iat


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_refresh_token_roundtrip_preserves_claims(
    user_id: uuid.UUID, role: RoleEnum
):
    """
    **Validates: Requirements 2.6**

    Property 1 (refresh): For any valid UUID and RoleEnum, encoding a refresh
    token and then decoding it must produce a TokenPayload whose ``sub``
    matches the original UUID, ``role`` matches the original role, and
    ``type`` equals "refresh".
    """
    svc = _make_token_service()

    token = svc.create_refresh_token(user_id, role)
    payload = svc.decode_token(token)

    assert payload.sub == str(user_id)
    assert payload.role == role
    assert payload.type == "refresh"
    assert payload.exp is not None
    assert payload.iat is not None
    assert payload.exp > payload.iat


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy, token_type=token_type_strategy)
def test_roundtrip_preserves_claims_for_any_token_type(
    user_id: uuid.UUID, role: RoleEnum, token_type: str
):
    """
    **Validates: Requirements 2.6**

    Property 1 (general): For any valid UUID, RoleEnum, and token type
    ("access" or "refresh"), the encode-then-decode round trip must preserve
    ``sub``, ``role``, and ``type`` exactly.
    """
    svc = _make_token_service()

    if token_type == "access":
        token = svc.create_access_token(user_id, role)
    else:
        token = svc.create_refresh_token(user_id, role)

    payload = svc.decode_token(token)

    assert payload.sub == str(user_id)
    assert payload.role == role
    assert payload.type == token_type


# ---------------------------------------------------------------------------
# Property 2: Token Claims Completeness
# ---------------------------------------------------------------------------

_EXPECTED_CLAIMS = {"sub", "role", "type", "exp", "iat"}


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_access_token_contains_exactly_required_claims(
    user_id: uuid.UUID, role: RoleEnum
):
    """
    **Validates: Requirements 2.1, 2.5**

    Property 2 (access): For any valid UUID and RoleEnum, an access token
    SHALL contain exactly the claims ``sub``, ``role``, ``type``, ``exp``,
    and ``iat`` — no more, no less. The ``type`` claim SHALL equal "access",
    ``sub`` SHALL match the user UUID, and ``role`` SHALL match the user's
    role.
    """
    svc = _make_token_service()
    token = svc.create_access_token(user_id, role)

    # Decode raw JWT without validation to inspect the exact claim set
    raw_claims = pyjwt.decode(
        token, _TEST_SECRET, algorithms=["HS256"]
    )

    # Exactly the expected claims — no extra, no missing
    assert set(raw_claims.keys()) == _EXPECTED_CLAIMS

    # Verify claim values
    assert raw_claims["sub"] == str(user_id)
    assert raw_claims["role"] == role.value
    assert raw_claims["type"] == "access"
    assert isinstance(raw_claims["exp"], int)
    assert isinstance(raw_claims["iat"], int)


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_refresh_token_contains_exactly_required_claims(
    user_id: uuid.UUID, role: RoleEnum
):
    """
    **Validates: Requirements 2.1, 2.5**

    Property 2 (refresh): For any valid UUID and RoleEnum, a refresh token
    SHALL contain exactly the claims ``sub``, ``role``, ``type``, ``exp``,
    and ``iat`` — no more, no less. The ``type`` claim SHALL equal "refresh".
    """
    svc = _make_token_service()
    token = svc.create_refresh_token(user_id, role)

    raw_claims = pyjwt.decode(
        token, _TEST_SECRET, algorithms=["HS256"]
    )

    assert set(raw_claims.keys()) == _EXPECTED_CLAIMS

    assert raw_claims["sub"] == str(user_id)
    assert raw_claims["role"] == role.value
    assert raw_claims["type"] == "refresh"
    assert isinstance(raw_claims["exp"], int)
    assert isinstance(raw_claims["iat"], int)


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, role=role_strategy)
def test_token_type_is_only_access_or_refresh(
    user_id: uuid.UUID, role: RoleEnum
):
    """
    **Validates: Requirements 2.5**

    Property 2 (type exclusivity): The TokenService only produces tokens
    with ``type`` equal to "access" or "refresh". No other token types
    SHALL be produced.
    """
    svc = _make_token_service()

    access_claims = pyjwt.decode(
        svc.create_access_token(user_id, role),
        _TEST_SECRET,
        algorithms=["HS256"],
    )
    refresh_claims = pyjwt.decode(
        svc.create_refresh_token(user_id, role),
        _TEST_SECRET,
        algorithms=["HS256"],
    )

    assert access_claims["type"] == "access"
    assert refresh_claims["type"] == "refresh"
    assert access_claims["type"] in ("access", "refresh")
    assert refresh_claims["type"] in ("access", "refresh")
