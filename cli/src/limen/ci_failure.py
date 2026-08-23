"""One truthful classifier for GitHub Actions failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class CIFailure:
    classification: str
    detail: str
    retry_allowed: bool

    def __iter__(self):
        yield self.classification
        yield self.detail


def classify_ci_failure(
    jobs: Iterable[dict[str, Any]],
    annotations: Iterable[dict[str, Any]] = (),
    *,
    visibility_drift: bool = False,
) -> CIFailure:
    failed = [job for job in jobs if str(job.get("conclusion") or "") in {"failure", "startup_failure"}]
    if not failed:
        return CIFailure("unknown", "no failed jobs were available", False)
    if any(job.get("steps") for job in failed):
        return CIFailure("executed_code_failure", "one or more failed jobs executed steps", False)
    text = " ".join(str(row.get("message") or "") for row in annotations).lower()
    if any(
        phrase in text
        for phrase in (
            "account is locked due to a billing issue",
            "account locked due to a billing issue",
            "payments have failed",
            "payment has failed",
            "spending limit",
        )
    ):
        return CIFailure(
            "provider_runner_admission",
            "provider billing-related runner-admission annotation observed; account cause and remediation unverified",
            False,
        )
    if "quota" in text or "included minutes" in text or "actions minutes" in text:
        return CIFailure("quota", "GitHub reports an Actions quota gate", False)
    if visibility_drift:
        return CIFailure("visibility_drift", "observed visibility differs from the estate registry", False)
    if text:
        return CIFailure("unknown", "unrecognized GitHub startup annotation", False)
    return CIFailure("runner_startup_jam", "failed jobs have zero steps and no classified gate", True)
