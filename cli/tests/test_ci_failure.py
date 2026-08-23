import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.ci_failure import classify_ci_failure


ZERO_STEP = [{"conclusion": "failure", "steps": []}]


def test_billing_related_provider_annotation_is_observation_not_diagnosis():
    result = classify_ci_failure(
        ZERO_STEP,
        [{"message": "The job was not started because your account is locked due to a billing issue."}],
    )
    assert result.classification == "provider_runner_admission"
    assert "cause and remediation unverified" in result.detail
    assert result.retry_allowed is False


def test_executed_failure_is_distinct_from_startup_gate():
    result = classify_ci_failure([{"conclusion": "failure", "steps": [{"name": "pytest"}]}])
    assert result.classification == "executed_code_failure"
    assert result.retry_allowed is False


def test_only_unknown_zero_step_startup_jam_is_retryable():
    result = classify_ci_failure(ZERO_STEP)
    assert result.classification == "runner_startup_jam"
    assert result.retry_allowed is True


def test_provider_admission_and_quota_annotations_never_retry():
    cases = {
        "Recent account payments have failed": "provider_runner_admission",
        "Your spending limit must be increased": "provider_runner_admission",
        "Actions minutes quota exhausted": "quota",
    }
    for message, expected in cases.items():
        result = classify_ci_failure(ZERO_STEP, [{"message": message}])
        assert (result.classification, result.retry_allowed) == (expected, False)
