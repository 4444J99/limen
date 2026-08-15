"""Contracts for the summing-denominator resolver.

Every test here asserts a FAILURE mode. A partition library whose tests only prove
that correct input passes would itself be the defect it exists to catch — the
167-vs-54 report was internally consistent too.
"""

from __future__ import annotations

import pytest

from limen.bucket_partition import UNACCOUNTED, PartitionError, partition


def test_a_short_sum_fails_even_though_every_candidate_was_classified():
    """The 167-vs-54 shape: every enumerated item got a bucket, but 3 were never seen.

    Deriving the denominator from what you enumerated makes the arithmetic true by
    construction and the check can then never fail.
    """
    p = partition(declared_total=10, assignments={"a": "merged", "b": "merged", "c": "conflicted"})

    assert p.assigned == 3
    assert p.unenumerated == 7
    # It DOES reconcile — 3 assigned + 7 residual == 10 declared — and that is the
    # whole design: the arithmetic only closes because the 7 unseen members are
    # carried as residual rather than dropped. Had the denominator been derived from
    # the 3 enumerated candidates, this would have "summed" 3 == 3 by construction and
    # the check could never have failed. Completeness, not summation, is the verdict.
    assert p.sums
    assert not p.complete
    assert any("sample was analyzed and a corpus was described" in f for f in p.failures())


def test_enumerating_more_than_was_declared_fails_the_sum():
    """The understated-denominator shape — 167 enumerated against 54 declared.

    This is the case `sums` exists for: under-enumeration is absorbed as residual,
    but a population larger than the one claimed cannot be reconciled at all.
    """
    p = partition(
        declared_total=2,
        assignments={"a": "merged", "b": "merged", "c": "merged"},
    )

    assert p.assigned == 3
    assert not p.sums
    assert not p.complete
    assert any("do not sum" in f for f in p.failures())


def test_an_unclassified_candidate_is_fatal_not_advisory():
    """'We could not tell' must not report the same value as 'nothing is wrong'."""
    p = partition(
        declared_total=3,
        candidates=["a", "b", "c"],
        assignments={"a": "merged", "b": "merged"},  # c enumerated, never classified
    )

    assert p.unaccounted == ("c",)
    assert p.sums, "it still reconciles arithmetically — which is exactly why sum alone is insufficient"
    assert not p.complete
    assert any("landed in no bucket" in f for f in p.failures())


def test_a_bounded_bucket_without_measured_evidence_is_a_label_not_an_outcome():
    """`exceeds_bound` was the specific hole: 138 candidates labelled, none measured."""
    p = partition(
        declared_total=2,
        assignments={"a": "exceeds_bound", "b": "exceeds_bound"},
        bounded_buckets=["exceeds_bound"],
        evidence={"a": {"elapsed_seconds": 1200}},  # b claims the bound with no measurement
    )

    assert p.evidence_gaps == ("b",)
    assert not p.complete
    assert any("no measured" in f for f in p.failures())


def test_a_measured_bound_is_accepted():
    p = partition(
        declared_total=1,
        assignments={"a": "exceeds_bound"},
        bounded_buckets=["exceeds_bound"],
        evidence={"a": {"elapsed_seconds": 0}},  # zero is a measurement; absence is not
    )

    assert p.complete


def test_a_boolean_does_not_satisfy_a_measurement():
    """`True` is an int in Python — an easy way to smuggle a label past a type check."""
    p = partition(
        declared_total=1,
        assignments={"a": "exceeds_bound"},
        bounded_buckets=["exceeds_bound"],
        evidence={"a": {"elapsed_seconds": True}},
    )

    assert p.evidence_gaps == ("a",)


def test_double_assignment_is_reported_rather_than_last_write_wins():
    p = partition(declared_total=1, assignments={"a": ["merged", "closed"]})

    assert p.duplicated == {"a": ("merged", "closed")}
    assert not p.complete
    assert any("disjoint" in f for f in p.failures())


def test_the_residual_bucket_cannot_be_declared_by_a_caller():
    """Letting a caller assign `unaccounted` would restore the advisory behavior."""
    with pytest.raises(PartitionError, match="reserved"):
        partition(declared_total=1, assignments={"a": UNACCOUNTED})


def test_a_negative_denominator_is_refused():
    with pytest.raises(PartitionError, match="declared_total"):
        partition(declared_total=-1, assignments={})


def test_a_complete_accounting_passes_and_states_its_denominator():
    p = partition(
        declared_total=3,
        assignments={"a": "merged", "b": "merged", "c": "conflicted"},
    )

    assert p.complete
    assert p.failures() == ()
    assert "3 declared" in p.report()
    assert "OK" in p.report()


def test_report_never_prints_a_bucket_table_that_reads_as_full_coverage():
    p = partition(declared_total=4, candidates=["a", "b"], assignments={"a": "merged"})
    report = p.report()

    assert UNACCOUNTED in report, "the residual must appear in the table, not just the failures"
    assert "never-enumerated" in report
    assert "OK" not in report
