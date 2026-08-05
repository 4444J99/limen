#!/usr/bin/env python3
"""The ONE resolver for "is this reference alive?" — imported, never re-implemented.

Sibling of `scripts/corpus_resolve.py`, and founded on the same measured defect one axis
over. Three predicates each carried their own copy of this logic and each was wrong in a
different direction the moment the 2026-07-27 evacuation moved 34 roots off the host:

    check-corpora.py      an absent store root degraded to an ADVISORY, so a store archived
                          with two verified copies and a store someone deleted read
                          IDENTICALLY and the check stayed green. Green through absence.
    check-convergence.py  `_owner_reachable` calls a `~/…` owner 'missing' whenever
                          ~/Workspace exists — an ARCHIVED repo reads as a DELETED one.
    check-atom-homing.py  a third copy, in `_home_reachable`.

STATES

    ok                 present on this host right now
    archived           absent here, and the custody receipts PROVE it survives elsewhere
                       (restoration verified, >= 2 copies, independent physical devices)
    unaccounted        absent here, absence is provable here, and NOTHING accounts for it.
                       This is the state that used to be indistinguishable from `archived`,
                       and it is the one that should stop a build.
    unverifiable-here  the evidence to decide is not on this machine (a CI runner has no
                       ~/Workspace). The check-corpora/check-convergence rule, kept: absence
                       of evidence is a host fact, never drift.

The `archive` vs `remote` distinction is load-bearing and comes from the registry, not from
guesswork: a `remote: none` store (what makes it safe to hold unredacted content) has ONLY
its receipts, so failing receipts there is real data loss; a root with a git remote is
recoverable by cloning and its local absence is ordinary.

Import it; do not copy it:

    from reference_state import ReferenceResolver
    r = ReferenceResolver()
    r.resolve("~/Workspace/_conversations-private").state   # -> 'archived'
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "custody.yaml"

OK = "ok"
ARCHIVED = "archived"
UNACCOUNTED = "unaccounted"
UNVERIFIABLE = "unverifiable-here"

# Receipt schemas that assert custody. The ledger mixes these with reclaim/processing
# events that never claimed any; only these carry restoration_passed/copy_count.
CUSTODY_SCHEMA = "custody"


@dataclass(frozen=True)
class Reference:
    ref: str
    state: str
    detail: str
    row: str | None = None

    @property
    def alive(self) -> bool:
        """True when the reference is accounted for — present OR provably custodied."""
        return self.state in (OK, ARCHIVED, UNVERIFIABLE)


class ReferenceResolver:
    """Resolves references against disk + the committed custody receipts."""

    def __init__(self, registry: Path | None = None) -> None:
        self.registry_path = registry or REGISTRY
        self.doc: dict = {}
        self.receipts: list[dict] = []
        self.load_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.registry_path.is_file():
            self.load_error = f"custody registry missing at {self.registry_path}"
            return
        self.doc = yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or {}
        ledger = ROOT / str(self.doc.get("receipts_ledger") or "")
        if not ledger.is_file():
            self.load_error = f"receipts ledger missing at {ledger}"
            return
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                self.receipts.append(json.loads(line))
            except json.JSONDecodeError as exc:
                self.load_error = f"receipts ledger has unparseable JSON: {exc}"
                return

    # ── receipts ────────────────────────────────────────────────────────────────────

    def receipts_for(self, label: str) -> list[dict]:
        """Only CUSTODY-schema receipts participate in a custody verdict.

        The ledger also carries reclaim/processing events for regenerable caches (tool
        caches, runtime bundles, the Backblaze package) which legitimately carry no
        restoration/copy fields because nothing was custodied — they were deleted as
        reproducible. Counting those would make a missing `copy_count` read as 0 and fail
        a root whose real custody receipts are fine.
        """
        return [r for r in self.receipts if r.get("label") == label and CUSTODY_SCHEMA in str(r.get("schema", ""))]

    def custody_holds(self, label: str) -> tuple[bool, str]:
        """Does `label` satisfy the registry's declared custody predicate?"""
        pred = self.doc.get("custody_predicate") or {}
        rows = self.receipts_for(label)
        if not rows:
            return False, f"no receipt carries label {label!r}"
        min_copies = int(pred.get("min_copy_count", 2))
        for r in rows:
            if pred.get("restoration_passed") and not r.get("restoration_passed"):
                return False, f"{label}: a receipt reports restoration_passed=false"
            if int(r.get("copy_count") or 0) < min_copies:
                return False, f"{label}: copy_count {r.get('copy_count')} < {min_copies}"
            if pred.get("independent_physical_devices") and not r.get("independent_physical_devices"):
                return False, f"{label}: copies are not on independent physical devices"
        n = len(rows)
        sample = rows[0]
        return True, (
            f"{n} receipt(s); restoration verified, {sample.get('copy_count')} copies on "
            f"independent devices ({sample.get('file_count')} files)"
        )

    # ── resolution ──────────────────────────────────────────────────────────────────

    def _rows(self) -> dict[str, dict]:
        return self.doc.get("roots") or {}

    def _row_for(self, ref: str) -> tuple[str | None, dict | None]:
        for name, row in self._rows().items():
            if str(row.get("ref", "")).strip() == ref.strip():
                return name, row
        return None, None

    def absence_is_provable(self) -> bool:
        """Only a host that HAS a Workspace can prove a ~/Workspace path is absent.

        The same rule check-corpora and check-convergence already used, stated once.
        """
        return (Path.home() / "Workspace").is_dir()

    def resolve(self, ref: str) -> Reference:
        ref = ref.strip()
        if self.load_error:
            return Reference(ref, UNVERIFIABLE, self.load_error)

        path = Path(ref).expanduser() if ref.startswith("~") else (ROOT / ref)
        if path.exists():
            return Reference(ref, OK, f"present at {path}")

        name, row = self._row_for(ref)
        if row is None:
            if ref.startswith("~") and not self.absence_is_provable():
                return Reference(ref, UNVERIFIABLE, "no ~/Workspace on this host — absence is not provable here")
            return Reference(
                ref,
                UNACCOUNTED,
                "absent from this host and NO custody row accounts for it — "
                "archived and deleted are indistinguishable until one is declared",
            )

        label = row.get("custody_label")
        if not label:
            return Reference(ref, UNACCOUNTED, f"custody row {name!r} declares no custody_label", name)

        holds, why = self.custody_holds(str(label))
        if holds:
            return Reference(ref, ARCHIVED, why, name)

        # An archive-class root whose receipts do not hold is the real-data-loss shape;
        # a remote-class root is still recoverable by cloning, so say so precisely.
        if str(row.get("class")) == "remote" and row.get("remote"):
            return Reference(ref, ARCHIVED, f"receipts inconclusive ({why}) but recoverable from {row['remote']}", name)
        return Reference(ref, UNACCOUNTED, why, name)
