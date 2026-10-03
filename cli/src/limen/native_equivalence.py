"""Compare complete native inventories without claiming recreated history.

ctime is filesystem-maintained and atime changes when recovery reads files.
Their original measurements must remain in encrypted custody, not be asserted
equal to newly materialized clocks. This comparator does not authorize location
rebinding, retirement, or session release, and does not observe a filesystem.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from limen import portable_custody

PROFILE = "limen.native_inventory_equivalence.v1"
HISTORICAL_CLOCKS = frozenset({"atime_ns", "ctime_ns"})


def compare_native_manifests(
    original: bytes,
    observed: bytes,
    *,
    session_id: str,
    original_scope_paths: Mapping[str, str],
    observed_scope_paths: Mapping[str, str],
) -> dict[str, Any]:
    """Require exact membership and all reproducible native fields.

    Caller supplies authenticated original inventory and freshly measured current
    inventory. Digest equality alone, this report, and a substituted scope mapping
    are not custody, freshness, or relocation proof. Both complete input records
    remain required, including their distinct historical clock measurements.
    """
    if not original_scope_paths or set(original_scope_paths) != set(observed_scope_paths):
        raise portable_custody.PortableCustodyError("native equivalence original scope is incomplete")
    for paths in (original_scope_paths, observed_scope_paths):
        if any(not isinstance(value, str) or not portable_custody.DIGEST.fullmatch(value) for value in paths.values()):
            raise portable_custody.PortableCustodyError("native equivalence path binding is malformed")
    inventories = []
    for raw, paths in ((original, original_scope_paths), (observed, observed_scope_paths)):
        manifest = json.loads(raw)
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != "limen.native_capture.v1"
            or manifest.get("session_id") != session_id
            or manifest.get("scope_paths") != dict(paths)
        ):
            raise portable_custody.PortableCustodyError("native equivalence inventory binding mismatch")
        entries = manifest.get("entries")
        if not isinstance(entries, dict) or set(entries) != set(paths):
            raise portable_custody.PortableCustodyError("native equivalence scope denominator mismatch")
        flattened = {}
        for root, rows in entries.items():
            if not isinstance(rows, dict) or not rows or "." not in rows:
                raise portable_custody.PortableCustodyError("native equivalence root is unmeasured")
            for relative, entry in rows.items():
                if not portable_custody._relative(relative):
                    raise portable_custody.PortableCustodyError("native equivalence member path is malformed")
                flattened[root, relative] = portable_custody._native_entry(entry)
        inventories.append(flattened)
    baseline, current = inventories
    if set(baseline) != set(current):
        raise portable_custody.PortableCustodyError("native equivalence atom denominator differs")
    changed_clocks = 0
    for atom, metadata in baseline.items():
        projected = {key: value for key, value in metadata.items() if key not in HISTORICAL_CLOCKS}
        measured = {key: value for key, value in current[atom].items() if key not in HISTORICAL_CLOCKS}
        if projected != measured:
            raise portable_custody.PortableCustodyError("native equivalence content or materialized metadata differs")
        changed_clocks += any(metadata[key] != current[atom][key] for key in HISTORICAL_CLOCKS)
    return {
        "schema": PROFILE,
        "session_id": session_id,
        "original_native_sha256": hashlib.sha256(original).hexdigest(),
        "observed_native_sha256": hashlib.sha256(observed).hexdigest(),
        "root_count": len(original_scope_paths),
        "atom_count": len(baseline),
        "materialized_fields_equal": True,
        "historical_clock_records_required": sorted(HISTORICAL_CLOCKS),
        "atoms_with_distinct_historical_clocks": changed_clocks,
        "clock_equality_claimed": False,
        "freshness_verified": False,
        "custody_verified": False,
        "relocation_authorized": False,
        "retirement_authorized": False,
        "session_release_certified": False,
    }
