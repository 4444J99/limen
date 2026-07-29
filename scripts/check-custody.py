#!/usr/bin/env python3
"""CUSTODY drift predicate — an absent reference is either CUSTODIED or UNACCOUNTED.

Exit 0 iff institutio/governance/custody.yaml is coherent against the committed evacuation
receipts:

  A  schema    — required top-level blocks; every root row carries ref/class/referenced_by,
                 class in {archive, remote}, and an archive row names a custody_label.
  B  ledger    — the declared receipts ledger and inventory exist, parse, and every receipt
                 carries the fields the custody predicate reads (a receipt missing
                 `copy_count` must not silently satisfy `>= 2`).
  C  labels    — every declared custody_label appears in the ledger. A row pointing at a
                 label nothing emits is a custody claim with no evidence.
  D  predicate — every ARCHIVE-class row satisfies the declared custody predicate
                 (restoration_passed, >= min copies, independent physical devices). This is
                 the hard one: an archive-class root has no remote, so failing receipts here
                 is the shape of real data loss, not a warning.
  E  coverage  — every store root declared in corpora.yaml either exists on disk or has a
                 custody row. This is what ends green-through-absence: an undeclared missing
                 store now FAILS instead of degrading to an advisory.
  F  vault     — a declared vault's restore rail actually exists in-tree (the script and the
                 verb), so "recoverable from the vault" is a checked claim, not a memory.

Run directly, via pr-gate, or verify-whole. Fails toward caution: a broken registry is RED.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference_state import ARCHIVED, OK, UNACCOUNTED, ReferenceResolver

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "custody.yaml"
CORPORA = ROOT / "institutio" / "governance" / "corpora.yaml"

VALID_CLASS = {"archive", "remote"}
REQUIRED_ROW = ("ref", "class", "referenced_by")
RECEIPT_FIELDS = ("label", "restoration_passed", "copy_count", "independent_physical_devices")

failures: list[str] = []
notes: list[str] = []


def fail(check: str, msg: str) -> None:
    failures.append(f"  ✗ [{check}] {msg}")


def advise(check: str, msg: str) -> None:
    notes.append(f"  ↑ {check}: {msg}")


def main() -> int:
    if not REGISTRY.is_file():
        print(f"FAILED: check-custody — registry missing at {REGISTRY}")
        return 1
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    resolver = ReferenceResolver()
    if resolver.load_error:
        print(f"FAILED: check-custody — {resolver.load_error}")
        return 1

    roots = doc.get("roots") or {}
    if not roots:
        fail("A", "registry declares no `roots`")
    if not (doc.get("custody_predicate") or {}):
        fail("A", "registry declares no `custody_predicate` — the bar for 'custodied' must be explicit")

    # B: the evidence files themselves.
    for key in ("receipts_ledger", "inventory"):
        rel = str(doc.get(key) or "")
        if not rel:
            fail("B", f"no `{key}` declared")
        elif not (ROOT / rel).is_file():
            fail("B", f"{key} missing at {rel}")
    for i, receipt in enumerate(resolver.receipts):
        missing = [f for f in RECEIPT_FIELDS if f not in receipt]
        # Only CUSTODY-schema receipts participate; the ledger also carries reclaim and
        # processing events for regenerable caches which never claimed custody and so carry
        # none of these fields. Requiring them there would fail the ledger for being honest.
        if "label" in receipt and "custody" in str(receipt.get("schema", "")) and missing:
            fail("B", f"receipt[{i}] label={receipt.get('label')!r} lacks {missing} — cannot satisfy the predicate")

    labels_in_ledger = {
        r.get("label") for r in resolver.receipts if r.get("label") and "custody" in str(r.get("schema", ""))
    }

    for name, row in sorted(roots.items()):
        if not isinstance(row, dict):
            fail("A", f"{name}: row must be a mapping")
            continue

        # A: shape.
        for field in REQUIRED_ROW:
            if not row.get(field):
                fail("A", f"{name}: missing `{field}`")
        cls = row.get("class")
        if cls not in VALID_CLASS:
            fail("A", f"{name}: class {cls!r} not in {sorted(VALID_CLASS)}")
        if cls == "remote" and not row.get("remote"):
            fail("A", f"{name}: class 'remote' must name the `remote` it is recoverable from")
        label = row.get("custody_label")
        if cls == "archive" and not label:
            fail("A", f"{name}: an archive-class root has NO remote — it must name a custody_label")

        # C: the label is real.
        if label and label not in labels_in_ledger:
            fail("C", f"{name}: custody_label {label!r} appears in no receipt — a claim with no evidence")
            continue

        # D: archive-class rows must actually pass the predicate.
        if cls == "archive" and label:
            holds, why = resolver.custody_holds(str(label))
            if not holds:
                fail("D", f"{name}: archive-class root fails the custody predicate — {why}")
            else:
                advise("D", f"{name}: {why}")

        # F: a declared vault's restore rail exists.
        vault_name = row.get("vault")
        if vault_name:
            vault = (doc.get("vaults") or {}).get(vault_name)
            if not vault:
                fail("F", f"{name}: vault {vault_name!r} is not declared under `vaults`")
            else:
                cmd = str(vault.get("restore_command") or "")
                script = next((t for t in cmd.split() if t.endswith((".sh", ".py"))), "")
                if not script:
                    fail("F", f"vault {vault_name}: restore_command names no script")
                elif not (ROOT / script).is_file():
                    fail("F", f"vault {vault_name}: restore rail {script} does not exist")
                else:
                    src = (ROOT / script).read_text(encoding="utf-8")
                    if "restore" not in src:
                        fail("F", f"vault {vault_name}: {script} has no restore verb")

    # E: coverage — no corpora store may be silently absent.
    if CORPORA.is_file():
        cdoc = yaml.safe_load(CORPORA.read_text(encoding="utf-8")) or {}
        for store, srow in (cdoc.get("stores") or {}).items():
            ref = str(srow.get("root") or "")
            if not ref:
                continue
            res = resolver.resolve(ref)
            if res.state == UNACCOUNTED:
                fail(
                    "E",
                    f"corpora store {store!r} root {ref} is absent and UNACCOUNTED — declare a custody "
                    "row (this is the green-through-absence the axis exists to end)",
                )
            elif res.state == ARCHIVED or res.state != OK:
                advise("E", f"corpora store {store!r}: {res.state} — {res.detail}")

    for n in notes:
        print(n)
    if failures:
        print("custody registry: DRIFT")
        print("\n".join(failures))
        return 1
    archive_rows = sum(1 for r in roots.values() if isinstance(r, dict) and r.get("class") == "archive")
    print(
        f"custody registry: OK ({len(roots)} root(s), {archive_rows} archive-class, "
        f"{len(resolver.receipts)} receipt(s) across {len(labels_in_ledger)} label(s), checks A-F clean)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
