from limen.delegation_policy import select_delegation


def test_phase_transition_without_a_validated_plan_is_denied():
    result = select_delegation({"phase": "plan-to-build"}, now=1000)
    assert result["decision"] == "deny"
    assert result["selection_reason"] == "validated-plan-required"


def test_retry_requires_actual_transient_outcome_evidence():
    result = select_delegation({"attempt": 1}, now=1000)
    assert result["selection_reason"] == "retry-evidence-required"
    result = select_delegation({"attempt": 1, "previous_terminal_class": "auth_failure"}, now=1000)
    assert result["selection_reason"] == "retry-evidence-required"


def test_malformed_parent_packet_cannot_grant_authority():
    result = select_delegation({"work_packet": {"spend": {"limit": 100}}}, now=1000)
    assert result["selection_reason"] == "invalid-work-packet"
