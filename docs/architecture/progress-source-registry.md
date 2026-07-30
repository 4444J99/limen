# Work-universe source registry

The source registry is the runtime discovery boundary for universe work. It is
separate from `limen progress`, which remains an explicitly partial board and
source-readiness lens.

Each source has two contracts:

1. a durable registration under `config/progress-sources/*.json` (or another
   root named by `LIMEN_PROGRESS_SOURCE_REGISTRY_DIRS`); and
2. a runtime report produced by the owning system.

A registration names `source_id`, `owner.id`, `owner.surface`, `report_path`,
`required`, and `max_age_seconds`. A report uses schema
`limen.progress-source-report.v1` and reports the same `source_id`, a cursor
(which may be null), an explicit exhaustive boolean, RFC 3339 generation time,
the SHA-256 of the source-owned content, semantic status, and normalized leaf
count.

The registry accepts these semantic statuses: `ready`, `partial`, `capped`,
`failed`, `unavailable`, `stale`, and `unknown`. A `ready` report with
`exhaustive: false` is normalized to `partial`. An expired report is normalized
to `stale`. Missing or malformed reports, duplicate source IDs, unreadable
registration roots, and an empty registry remain coverage debt. Unknown leaf
counts are null and counted separately; they are never rendered as zero work.
The aggregate `normalized_leaf_count` is also null when any source count or
discovery root is unknown; `known_normalized_leaf_count` remains available as a
strictly partial subtotal.

Source IDs and registration filenames are data. Tests use arbitrary and renamed
IDs so adding, removing, or reordering a source never requires a code change.

Python consumers call:

```python
from pathlib import Path
from limen.progress_source_registry import build_source_registry

registry = build_source_registry(Path("/path/to/limen"))
```

Operators can inspect the same contract without writing a receipt:

```bash
limen progress-sources
limen progress-sources --json-output
limen progress-sources --registry-dir /path/to/owner-registrations
```

The result uses schema `limen.progress-source-registry.v1` and includes a
content-addressed discovery contract, source rows, discovery exhaustiveness,
coverage debt, unknown-count debt, and the sum of known normalized leaves.
This registry defines the interface; the dependent GitHub-estate,
prompt-lineage, lifecycle, CI, mail, financial, contribution, and owner-gate
packets add their own owner registrations and reports.
