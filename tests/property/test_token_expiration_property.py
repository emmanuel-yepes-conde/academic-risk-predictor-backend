# Feature: jwt-role-authentication, Property 3: Token Expiration Matches Configuration
"""
Property-based test for token expiration matching configuration.

**Property 3 — Token Expiration Matches Configuration (Validates: Requirements 2.3, 2.4):**
For any positive integer value of ``access_expire_minutes`` and any positive
integer value of ``refresh_expire_days``, when the TokenService creates an
access token the difference between ``exp`` and ``iat`` SHALL equal
``access_expire_minutes * 60`` seconds. When creating a refresh token, the
difference SHALL equal ``refresh_expire_days * 86400`` seconds.
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

# Positive integers for expiration configuration.
# Upper bounds are generous but realistic to avoid overflow issues.
access_expire_minutes_strategy = st.integers(min_value=1, max_value=1440)  # up to 1 day
refresh_expire_days_strategy = st.integers(min_value=1, max_value=365)     # up to 1 year

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-secret-key-for-property-tests"


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@h_settings(max_examples=100)
@given(
    user_id=user_id_strategy,
    role=role_strategy,
    access_expire_minutes=access_expire_minutes_strategy,
)
def test_access_token_expiration_matches_configured_minutes(
    user_id: uuid.UUID,
    role: RoleEnum,
    access_expire_minutes: int,
):
    """
    **Validates: Requirements 2.3**

    Property 3 (access): For any positive integer ``access_expire_minutes``,
    the difference between ``exp`` and ``iat`` in a created access token
    SHALL equal ``access_expire_minutes * 60`` seconds.
    """
    svc = TokenService(
        secret_key=_TEST_SECRET,
        algorithm="HS256",
        access_expire_minutes=access_expire_minutes,
        refresh_expire_days=7,
    )

    token = svc.create_access_token(user_id, role)

    raw_claims = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"])

    exp = raw_claims["exp"]
    iat = raw_claims["iat"]
    expected_delta_seconds = access_expire_minutes * 60

    assert exp - iat == expected_delta_seconds, (
        f"Access token exp-iat={exp - iat}s, "
        f"expected {expected_delta_seconds}s "
        f"(access_expire_minutes={access_expire_minutes})"
    )


@h_settings(max_examples=100)
@given(
    user_id=user_id_strategy,
    role=role_strategy,
    refresh_expire_days=refresh_expire_days_strategy,
)
def test_refresh_token_expiration_matches_configured_days(
    user_id: uuid.UUID,
    role: RoleEnum,
    refresh_expire_days: int,
):
    """
    **Validates: Requirements 2.4**

    Property 3 (refresh): For any positive integer ``refresh_expire_days``,
    the difference between ``exp`` and ``iat`` in a created refresh token
    SHALL equal ``refresh_expire_days * 86400`` seconds.
    """
    svc = TokenService(
        secret_key=_TEST_SECRET,
        algorithm="HS256",
        access_expire_minutes=30,
        refresh_expire_days=refresh_expire_days,
    )

    token = svc.create_refresh_token(user_id, role)

    raw_claims = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"])

    exp = raw_claims["exp"]
    iat = raw_claims["iat"]
    expected_delta_seconds = refresh_expire_days * 86400

    assert exp - iat == expected_delta_seconds, (
        f"Refresh token exp-iat={exp - iat}s, "
        f"expected {expected_delta_seconds}s "
        f"(refresh_expire_days={refresh_expire_days})"
    )


@h_settings(max_examples=100)
@given(
    user_id=user_id_strategy,
    role=role_strategy,
    access_expire_minutes=access_expire_minutes_strategy,
    refresh_expire_days=refresh_expire_days_strategy,
)
def test_access_token_expires_before_refresh_token(
    user_id: uuid.UUID,
    role: RoleEnum,
    access_expire_minutes: int,
    refresh_expire_days: int,
):
    """
    **Validates: Requirements 2.3, 2.4**

    Corollary: For any configuration where ``refresh_expire_days >= 1`` and
    ``access_expire_minutes <= 1440``, the refresh token lifetime SHALL be
    greater than or equal to the access token lifetime.
    """
    svc = TokenService(
        secret_key=_TEST_SECRET,
        algorithm="HS256",
        access_expire_minutes=access_expire_minutes,
        refresh_expire_days=refresh_expire_days,
    )

    access_token = svc.create_access_token(user_id, role)
    refresh_token = svc.create_refresh_token(user_id, role)

    access_claims = pyjwt.decode(access_token, _TEST_SECRET, algorithms=["HS256"])
    refresh_claims = pyjwt.decode(refresh_token, _TEST_SECRET, algorithms=["HS256"])

    access_lifetime = access_claims["exp"] - access_claims["iat"]
    refresh_lifetime = refresh_claims["exp"] - refresh_claims["iat"]

    assert refresh_lifetime >= access_lifetime, (
        f"Refresh lifetime ({refresh_lifetime}s) should be >= "
        f"access lifetime ({access_lifetime}s)"
    )
