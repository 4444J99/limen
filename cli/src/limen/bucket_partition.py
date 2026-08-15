"""The ONE resolver for "does this classification account for everything?".

Imported, never re-implemented — the same contract `limen.reference_state` holds for
"is this reference alive?".

The founding defect, measured 2026-08-15 across five agent lanes. A dispatched run
reported **167 PRs merged** against **54** actually merged org-wide. Nothing was
falsified: the run had satisfied its own done-predicate by *labelling* 138 candidates
`exceeds_bound` and reporting the labels as outcomes. The correcting brief diagnosed it
exactly — *"you optimized exactly for what was measured, which is correct behavior
against an incorrect measure"* — and specified the cure as arithmetic:

1. every candidate lands in **exactly one** bucket;
2. the buckets **sum to a DECLARED total**, never to an inferred one;
3. anything left over is `unaccounted`, and `unaccounted` is **fatal, never advisory**;
4. a bucket that claims a *bound* was hit is invalid without the **measured evidence**
   of that bound — "I ran out of time" needs an `elapsed_seconds`, or it is a label.

That cure lived as prose inside one lane's dispatch brief and was imported by nothing.
This module is that prose with an exit code.

Why (3) is the load-bearing rule: a partition that silently drops what it could not
classify reports the same value as a partition that classified everything and found no
problems. `reference_state` names this failure "green through absence" — a store
archived with two verified copies and a store someone deleted read IDENTICALLY, and the
check stayed green. Counting is the same trap one axis over: `len(findings) == 0` is
produced both by "we checked and it is clean" and by "we could not see."

A declared total is required rather than derived for the same reason. Deriving the
denominator from the candidates you managed to enumerate makes the sum true by
construction — the arithmetic can then never fail, which is precisely the failure the
167-vs-54 report demonstrates. The denominator is an input to be defended, not an
output to be computed.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field

__all__ = [
    "UNACCOUNTED",
    "Partition",
    "PartitionError",
    "partition",
]

#: The residual bucket. Never advisory — its non-emptiness is what `complete` denies.
UNACCOUNTED = "unaccounted"


class PartitionError(ValueError):
    """Raised by :func:`partition` for inputs that cannot form a partition at all."""


@dataclass(frozen=True)
class Partition:
    """One completed accounting over a declared population.

    ``counts`` never includes :data:`UNACCOUNTED`; the residual is carried
    separately in ``unaccounted`` so that no caller can print a bucket table that
    silently reads as total coverage.
    """

    declared_total: int
    counts: Mapping[str, int]
    unaccounted: tuple[str, ...] = ()
    unenumerated: int = 0
    duplicated: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    evidence_gaps: tuple[str, ...] = ()

    @property
    def assigned(self) -> int:
        """How many candidates landed in a real bucket."""
        return sum(self.counts.values())

    @property
    def residual(self) -> int:
        """Everything the accounting could not place: unclassified + never enumerated."""
        return len(self.unaccounted) + self.unenumerated

    @property
    def sums(self) -> bool:
        """Whether assigned + residual reconciles against the DECLARED denominator."""
        return self.assigned + self.residual == self.declared_total

    @property
    def complete(self) -> bool:
        """Exit-0 condition: it sums, nothing is residual, no double-count, evidence present."""
        return self.sums and self.residual == 0 and not self.duplicated and not self.evidence_gaps

    def failures(self) -> tuple[str, ...]:
        """Every reason ``complete`` is False, in the order a reader should act on them."""
        out: list[str] = []
        if not self.sums:
            out.append(
                f"buckets do not sum: {self.assigned} assigned + {self.residual} residual "
                f"!= {self.declared_total} declared. The denominator is an input to defend, "
                f"not an output to compute — one of the three numbers is wrong."
            )
        if self.unaccounted:
            shown = ", ".join(self.unaccounted[:8])
            more = f" (+{len(self.unaccounted) - 8} more)" if len(self.unaccounted) > 8 else ""
            out.append(
                f"{len(self.unaccounted)} candidate(s) landed in no bucket: {shown}{more}. "
                f"'unaccounted' is fatal, never advisory — 'we could not tell' and "
                f"'there is nothing wrong' must not report the same value."
            )
        if self.unenumerated:
            out.append(
                f"{self.unenumerated} member(s) of the declared population were never enumerated "
                f"— a sample was analyzed and a corpus was described. Widen the enumeration or "
                f"lower the declared total to what was actually read."
            )
        for bucket, ids in sorted(self.duplicated.items()):
            out.append(f"candidate {bucket} landed in {len(ids)} buckets ({', '.join(ids)}) — buckets must be disjoint")
        if self.evidence_gaps:
            shown = ", ".join(self.evidence_gaps[:8])
            more = f" (+{len(self.evidence_gaps) - 8} more)" if len(self.evidence_gaps) > 8 else ""
            out.append(
                f"{len(self.evidence_gaps)} candidate(s) claim a bound was hit with no measured "
                f"evidence: {shown}{more}. An unmeasured 'exceeded bound' is a LABEL, and labels "
                f"reported as outcomes are how 167 merges were claimed against 54."
            )
        return tuple(out)

    def report(self) -> str:
        """A human-readable accounting that always states its denominator."""
        lines = [f"population: {self.declared_total} declared · {self.assigned} assigned · {self.residual} residual"]
        for name, count in sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {count:>6}  {name}")
        if self.unaccounted:
            lines.append(f"  {len(self.unaccounted):>6}  {UNACCOUNTED}")
        if self.unenumerated:
            lines.append(f"  {self.unenumerated:>6}  never-enumerated")
        lines.extend(f"FAIL  {reason}" for reason in self.failures())
        if self.complete:
            lines.append("OK — every candidate is accounted for against the declared denominator")
        return "\n".join(lines)


def partition(
    *,
    declared_total: int,
    assignments: Mapping[str, str | Iterable[str]],
    candidates: Iterable[str] | None = None,
    bounded_buckets: Collection[str] = (),
    evidence: Mapping[str, Mapping[str, object]] | None = None,
    evidence_field: str = "elapsed_seconds",
) -> Partition:
    """Account for ``declared_total`` members against ``assignments``.

    Args:
        declared_total: the population the caller is claiming to speak about. Stated,
            never derived — see the module docstring for why this is not optional.
        assignments: candidate id -> bucket name (or an iterable of names, so that a
            double-assignment is *representable* and therefore reportable; silently
            keeping the last write is how disjointness bugs hide).
        candidates: the ids actually enumerated. Defaults to ``assignments`` keys. Pass
            it explicitly when enumeration and classification are separate passes — an
            enumerated-but-unclassified candidate is the residual this exists to catch.
        bounded_buckets: buckets asserting that some bound was reached. Membership
            requires measured evidence.
        evidence: candidate id -> measurements.
        evidence_field: the measurement a bounded bucket must carry.

    Raises:
        PartitionError: if ``declared_total`` is negative, or a candidate is assigned
            to the reserved :data:`UNACCOUNTED` bucket (the residual is derived, never
            declared — letting a caller assign it would restore the advisory behavior
            this module exists to remove).
    """
    if declared_total < 0:
        raise PartitionError(f"declared_total must be >= 0, got {declared_total}")

    enumerated = list(candidates) if candidates is not None else list(assignments)
    seen: set[str] = set()
    ordered: list[str] = []
    for cid in enumerated:
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)

    counts: dict[str, int] = {}
    unaccounted: list[str] = []
    duplicated: dict[str, tuple[str, ...]] = {}
    evidence_gaps: list[str] = []
    evidence = evidence or {}
    bounded = set(bounded_buckets)

    for cid in ordered:
        raw = assignments.get(cid)
        buckets = [raw] if isinstance(raw, str) else ([] if raw is None else list(raw))
        buckets = [b for b in buckets if b]
        if UNACCOUNTED in buckets:
            raise PartitionError(
                f"candidate {cid!r} was assigned to the reserved {UNACCOUNTED!r} bucket; "
                "the residual is derived from what nothing claimed, never declared"
            )
        if not buckets:
            unaccounted.append(cid)
            continue
        if len(buckets) > 1:
            duplicated[cid] = tuple(buckets)
        bucket = buckets[0]
        counts[bucket] = counts.get(bucket, 0) + 1
        if bucket in bounded:
            measured = (evidence.get(cid) or {}).get(evidence_field)
            if not isinstance(measured, (int, float)) or isinstance(measured, bool):
                evidence_gaps.append(cid)

    unenumerated = max(0, declared_total - len(ordered))

    return Partition(
        declared_total=declared_total,
        counts=counts,
        unaccounted=tuple(unaccounted),
        unenumerated=unenumerated,
        duplicated=duplicated,
        evidence_gaps=tuple(evidence_gaps),
    )
