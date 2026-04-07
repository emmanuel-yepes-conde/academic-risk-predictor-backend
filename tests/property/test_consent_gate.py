# Feature: postgresql-database-integration, Property 9: ML consent gate
"""
Property-based tests for the ML consent gate (Req 8.2, 8.3).

Verifies that:
- When Consent.accepted == False or no Consent record exists, the ML service
  raises HTTP 403 without executing the prediction.
- When Consent.accepted == True, the prediction is executed normally.

**Validates: Requirements 8.2, 8.3**
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.application.services.consent_service import ConsentService
from app.application.services.ml_service import MLApplicationService
from app.infrastructure.models.consent import Consent

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

student_id_strategy = st.uuids()
feature_strategy = st.lists(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    min_size=5,
    max_size=5,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_consent_repo_mock(consent_record: Consent | None) -> AsyncMock:
    """Return a mock IConsentRepository that returns the given consent record."""
    mock_repo = AsyncMock()
    mock_repo.get_consent = AsyncMock(return_value=consent_record)
    return mock_repo


def _make_ml_service_mock() -> MagicMock:
    """Return a mock AcademicRiskService whose predict() returns a dummy result."""
    mock_ml = MagicMock()
    mock_ml.predict.return_value = {
        "probability": 0.5,
        "risk_level": "MEDIO",
        "scaled_features": [0.0, 0.0, 0.0, 0.0, 0.0],
    }
    return mock_ml


def _make_consent(student_id: uuid.UUID, accepted: bool) -> Consent:
    consent = Consent(
        student_id=student_id,
        accepted=accepted,
        terms_version="v1.0",
    )
    return consent


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=student_id_strategy, features=feature_strategy)
async def test_no_consent_record_raises_403(
    student_id: uuid.UUID, features: list
):
    """
    **Validates: Requirements 8.2, 8.3**

    Property 9 (no record): When no Consent record exists for the student,
    the ML service must raise HTTP 403 without calling predict().
    """
    consent_repo = _make_consent_repo_mock(consent_record=None)
    consent_service = ConsentService(consent_repo)
    ml_mock = _make_ml_service_mock()
    ml_app_service = MLApplicationService(ml_mock, consent_service)

    with pytest.raises(HTTPException) as exc_info:
        await ml_app_service.predict_with_consent_check(student_id, features)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "El estudiante no ha otorgado consentimiento para el procesamiento de datos ML"
    )
    ml_mock.predict.assert_not_called()


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=student_id_strategy, features=feature_strategy)
async def test_consent_accepted_false_raises_403(
    student_id: uuid.UUID, features: list
):
    """
    **Validates: Requirements 8.2, 8.3**

    Property 9 (accepted=False): When Consent.accepted == False, the ML
    service must raise HTTP 403 without calling predict().
    """
    consent = _make_consent(student_id, accepted=False)
    consent_repo = _make_consent_repo_mock(consent_record=consent)
    consent_service = ConsentService(consent_repo)
    ml_mock = _make_ml_service_mock()
    ml_app_service = MLApplicationService(ml_mock, consent_service)

    with pytest.raises(HTTPException) as exc_info:
        await ml_app_service.predict_with_consent_check(student_id, features)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "El estudiante no ha otorgado consentimiento para el procesamiento de datos ML"
    )
    ml_mock.predict.assert_not_called()


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=student_id_strategy, features=feature_strategy)
async def test_consent_accepted_true_allows_prediction(
    student_id: uuid.UUID, features: list
):
    """
    **Validates: Requirements 8.2, 8.3**

    Property 9 (accepted=True): When Consent.accepted == True, the ML
    service must execute the prediction and return its result without raising.
    """
    consent = _make_consent(student_id, accepted=True)
    consent_repo = _make_consent_repo_mock(consent_record=consent)
    consent_service = ConsentService(consent_repo)
    ml_mock = _make_ml_service_mock()
    ml_app_service = MLApplicationService(ml_mock, consent_service)

    result = await ml_app_service.predict_with_consent_check(student_id, features)

    ml_mock.predict.assert_called_once_with(features)
    assert "probability" in result
    assert "risk_level" in result


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    student_id=student_id_strategy,
    features=feature_strategy,
    accepted=st.booleans(),
)
async def test_consent_gate_accepted_determines_outcome(
    student_id: uuid.UUID, features: list, accepted: bool
):
    """
    **Validates: Requirements 8.2, 8.3**

    Property 9 (general): For any value of Consent.accepted, the outcome
    must be deterministic — accepted=True allows prediction, accepted=False
    raises HTTP 403.
    """
    consent = _make_consent(student_id, accepted=accepted)
    consent_repo = _make_consent_repo_mock(consent_record=consent)
    consent_service = ConsentService(consent_repo)
    ml_mock = _make_ml_service_mock()
    ml_app_service = MLApplicationService(ml_mock, consent_service)

    if accepted:
        result = await ml_app_service.predict_with_consent_check(student_id, features)
        ml_mock.predict.assert_called_once_with(features)
        assert result is not None
    else:
        with pytest.raises(HTTPException) as exc_info:
            await ml_app_service.predict_with_consent_check(student_id, features)
        assert exc_info.value.status_code == 403
        ml_mock.predict.assert_not_called()
