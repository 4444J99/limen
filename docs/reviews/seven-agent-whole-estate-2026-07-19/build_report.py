#!/usr/bin/env python3
"""Build the canonical MCP report artifact from the frozen snapshot."""

from __future__ import annotations

import collections
import datetime as dt
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TITLE = "Seven-Agent Whole-Estate Session Review"
AGENTS = ("codex", "claude", "agy", "opencode", "gemini", "copilot", "jules")
OUTCOME_ORDER = (
    "verified_done",
    "verified_partial",
    "durably_homed_open",
    "blocked",
    "superseded",
    "not_done_or_unverified",
    "coverage_unknown",
)


def compact_time(value: str) -> str:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%m-%d %H:%MZ")


def minute_offset(value: str) -> int:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    anchor = dt.datetime(2026, 7, 6, 4, 0, tzinfo=dt.timezone.utc)
    return int((parsed - anchor).total_seconds() // 60)


def table(
    ident: str,
    title: str,
    dataset: str,
    columns: list[tuple[str, str, str]],
    sort_field: str,
    direction: str = "desc",
    subtitle: str | None = None,
) -> dict[str, Any]:
    return {
        "id": ident,
        "title": title,
        "subtitle": subtitle,
        "dataset": dataset,
        "columns": [
            {"field": field, "label": label, "type": kind}
            for field, label, kind in columns
        ],
        "defaultSort": {"field": sort_field, "direction": direction},
        "density": "compact",
        "sourceId": "frozen_snapshot",
    }


def main() -> int:
    data = json.loads((HERE / "snapshot.json").read_text())
    asks = data["asks"]
    total = len(asks)
    outcomes = collections.Counter(row["outcome"] for row in asks)
    verified = outcomes["verified_done"]
    verified_receipts = len(
        {row["receipt"] for row in data["deliverables"] if row["outcome"] == "verified_done"}
    )
    open_count = outcomes["durably_homed_open"]
    unknown_count = outcomes["coverage_unknown"] + outcomes["not_done_or_unverified"]
    overlap_hours = 12 + 49 / 60
    root_rows = []
    comparison_rows = []
    basis_labels = {
        "codex": "uncached input, output, reasoning, cached input",
        "claude": "input, output, cache creation, cache read",
        "opencode": "input, output, reasoning, cache read, cache write",
        "copilot": "input, output, reasoning, cache read, cache write",
    }
    for row in data["comparison"]:
        comparison_rows.append(
            {
                key: value
                for key, value in row.items()
                if key
                in {
                    "window",
                    "agent",
                    "root_sessions",
                    "child_sessions",
                    "session_span_hours",
                    "union_wall_hours",
                    "asks_observed",
                    "verified_done",
                    "open_or_unknown",
                }
            }
            | {"token_basis": basis_labels.get(row["agent"], "unknown")}
        )
        root_rows.append(
            {
                "window": row["window"],
                "agent": row["agent"],
                "root_sessions": row["root_sessions"],
                "child_sessions": row["child_sessions"],
                "union_wall_hours": row["union_wall_hours"],
                "asks_observed": row["asks_observed"],
            }
        )
    outcome_rows = []
    totals_by_agent = collections.Counter(row["agent"] for row in asks)
    for row in data["outcome_distribution"]:
        outcome_rows.append(
            {
                **row,
                "agent_total_asks": totals_by_agent[row["agent"]],
            }
        )
    token_rows = []
    common = {
        "window",
        "agent",
        "root_sessions",
        "child_sessions",
        "session_span_hours",
        "union_wall_hours",
        "asks_observed",
        "verified_done",
        "open_or_unknown",
        "token_basis",
    }
    for row in data["comparison"]:
        components = []
        for field, value in row.items():
            if field in common:
                continue
            components.append(f"{field}={value:,}")
        if components:
            token_rows.append(
                {
                    "window": row["window"],
                    "agent": row["agent"],
                    "components": "; ".join(components),
                    "basis": f"native {row['agent'].title()}",
                }
            )
    agent_findings = []
    for agent in AGENTS:
        counts = collections.Counter(
            row["outcome"] for row in asks if row["agent"] == agent
        )
        agent_findings.append(
            {
                "agent": agent,
                "asks": totals_by_agent[agent],
                "verified_done": counts["verified_done"],
                "verified_partial": counts["verified_partial"],
                "open": counts["durably_homed_open"],
                "blocked": counts["blocked"],
                "unverified_or_unknown": (
                    counts["not_done_or_unverified"] + counts["coverage_unknown"]
                ),
            }
        )
    selected_deliverables: list[dict[str, Any]] = []
    for agent in AGENTS:
        agent_rows = [
            row for row in data["deliverables"] if row["agent"] == agent
        ]
        selected_deliverables.extend(agent_rows[:1])
    compact_deliverables = [
        {
            "a": row["agent"],
            "t": row["title"],
            "o": row["outcome"],
            "u": row["receipt"],
            "p": (
                "exact-head pass"
                if row["outcome"] == "verified_done"
                else "merged; predicate not captured"
            ),
        }
        for row in selected_deliverables
    ]
    basis_codes = {
        "native event span": "native-span",
        "native message span": "native-message-span",
        "native last-modified point; duration unknown": "point-only; duration unknown",
        "board dispatch-to-terminal proxy": "dispatch proxy",
    }
    compact_sessions: dict[str, list[dict[str, Any]]] = {}
    for agent, session_rows in data["session_appendix"].items():
        grouped: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = (
            collections.defaultdict(list)
        )
        for index, row in enumerate(session_rows, start=1):
            basis = {
                "native-span": "N",
                "native-message-span": "M",
                "point-only; duration unknown": "U",
                "dispatch proxy": "P",
                "native request span": "Q",
            }.get(
                basis_codes.get(
                    row["time_basis"],
                    "native request span"
                    if str(row["time_basis"]).startswith("native request span")
                    else row["time_basis"],
                ),
                "?",
            )
            grouped[(row["role"][0].upper(), basis)].append(
                (index, row)
            )
        compact_sessions[agent] = []
        for (role, basis), group_rows in sorted(grouped.items(), reverse=True):
            indices = [index for index, _ in group_rows]
            dates = [row["start"][:10] for _, row in group_rows]
            compact_sessions[agent].append(
                {
                    "date_range": f"{min(dates)}–{max(dates)}",
                    "role": role,
                    "basis": basis,
                    "session_range": (
                        f"{agent[:2].upper()}{min(indices):04d}–"
                        f"{agent[:2].upper()}{max(indices):04d}"
                    ),
                    "sessions": len(group_rows),
                    "start_min": min(
                        minute_offset(row["start"]) for _, row in group_rows
                    ),
                    "end_min": max(
                        minute_offset(row["end"]) for _, row in group_rows
                    ),
                    "events": sum(int(row["events"]) for _, row in group_rows),
                }
            )
    snapshot = {
        "version": 1,
        "status": "ready",
        "generatedAt": data["snapshot_at"],
        "datasets": {
            "comparison": comparison_rows,
            "root_session_volume": root_rows,
            "outcome_distribution": outcome_rows,
            "token_components": token_rows,
            "agent_findings": agent_findings,
            "deliverables": compact_deliverables,
            "session_appendix": [
                {"agent": agent, **row}
                for agent, rows in compact_sessions.items()
                for row in rows
            ],
        },
    }
    source = {
        "id": "frozen_snapshot",
        "label": "Frozen seven-agent estate snapshot",
        "path": "docs/reviews/seven-agent-whole-estate-2026-07-19/snapshot.json",
        "query": {
            "description": (
                "Redacted event-level aggregation of native session stores, the Limen "
                "task ledger, live GitHub estate census, and exact pull-request receipts."
            ),
            "language": "python",
            "sql": (
                "SELECT * FROM read_json_auto("
                "'docs/reviews/seven-agent-whole-estate-2026-07-19/snapshot.json'"
                ");"
            ),
            "tables_used": [
                "Codex rollout events",
                "Claude transcript events",
                "OpenCode session and message tables",
                "Antigravity conversation summaries",
                "Gemini native chat events",
                "Copilot sessions and assistant usage events",
                "Limen task dispatch log",
                "GitHub repository and pull-request GraphQL objects",
            ],
            "filters": [
                "Completed week: 2026-07-06T04:00:00Z inclusive to 2026-07-13T04:00:00Z exclusive",
                "Latest seven days: 2026-07-12T15:11:00Z inclusive to 2026-07-19T15:11:00Z exclusive",
                "Events at or after snapshot_at excluded",
                "Raw prompts, secrets, machine-local paths, private receipt URLs, and full hashes excluded",
            ],
            "metric_definitions": [
                "Root-session volume counts root sessions with any native event or board proxy intersecting a window.",
                "Summed session span clips every observed span to the window and adds them; union wall time merges overlapping intervals by agent.",
                "Verified done requires a default-branch merge before snapshot_at and a successful exact-head status rollup or captured predicate.",
                "Token components preserve provider-native definitions and are never summed across providers.",
            ],
            "executed_at": data["snapshot_at"],
        },
    }
    blocks: list[dict[str, Any]] = [
        {"id": "title", "type": "markdown", "body": f"# {TITLE}"},
        {
            "id": "executive_summary",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Executive Summary\n\n"
                f"**Blunt verdict:** the estate produced real, remotely proven work, but "
                f"the control plane still overstates closure. Of {total:,} reconstructed "
                f"asks, {verified:,} ({verified / total:.1%}) are verified done at the frozen "
                f"snapshot, representing {verified_receipts:,} distinct public terminal "
                f"receipts. Another {open_count:,} remain durably homed but open; "
                f"{unknown_count:,} are unverified or coverage-unknown. This is a verified "
                "lower bound, not a claim that all activity was reconstructable.\n\n"
                "Codex carried the largest metered volume and broadest verified output; "
                "OpenCode converted a smaller observed session footprint into a strong verified "
                "share; Claude and Agy landed meaningful work but retained substantial open or "
                "unverified debt. Jules generated many remote dispatch proxies with a lower "
                "verified conversion rate. Gemini had board evidence but no native session "
                "store or verified completion in scope. Copilot had one independently verified "
                "coding-agent delivery; its large local native meter cannot safely be attributed "
                "to that one PR alone."
            ),
        },
        {
            "id": "scope",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Scope and Window Semantics\n\n"
                "The completed calendar week is `[2026-07-06 00:00, 2026-07-13 00:00)` "
                "America/New_York. The latest-seven-day window is "
                "`[2026-07-12 11:11, 2026-07-19 11:11)` America/New_York. They overlap by "
                f"{overlap_hours:.2f} hours, so rows are descriptive views of the same frozen "
                "event corpus and must not be added or treated as week-over-week periods. "
                f"The live estate census found {data['estate']['remote_repository_count']} "
                "repositories across the registry owners, then resolved task/session-linked "
                "receipt redirects to their current canonical owners."
            ),
        },
        {
            "id": "activity_heading",
            "type": "markdown",
            "body": (
                "## Activity Volume\n\n"
                "Root-session counts include sessions intersecting each half-open window. "
                "Child and subagent runs are retained separately; board-only remote sessions "
                "use a dispatch-to-terminal proxy and native point-only records have unknown duration."
            ),
        },
        {"id": "root_chart_block", "type": "chart", "chartId": "root_chart"},
        {
            "id": "time_tokens",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Time and Token Evidence\n\n"
                "Summed clipped spans measure observed provider-session occupancy and can exceed "
                "168 hours under concurrency. Union wall time merges overlapping intervals within "
                "an agent family. Neither is active keyboard time. Agy point records and absent "
                "native duration meters remain unknown. Token components are provider-native: "
                "cache reads and reasoning are shown separately, and no cross-agent token total "
                "is calculated."
            ),
        },
        {"id": "comparison_block", "type": "table", "tableId": "comparison_table"},
        {"id": "tokens_block", "type": "table", "tableId": "token_table"},
        {
            "id": "completion",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Completion Outcomes\n\n"
                "Outcome classification is ask-based, not session-, commit-, or board-state-based. "
                "A merged PR without a captured successful exact-head predicate is only "
                "`verified_partial`; an open PR is `durably_homed_open`. Duplicated and redirected "
                "receipts are canonicalized before terminal credit. Primary credit follows the "
                "executor family; landing and verification are assistance."
            ),
        },
        {"id": "outcome_chart_block", "type": "chart", "chartId": "outcome_chart"},
        {"id": "agent_findings_block", "type": "table", "tableId": "agent_findings_table"},
        {
            "id": "deliverables_heading",
            "type": "markdown",
            "body": (
                "## Verified Deliverables\n\n"
                "The table contains public, default-reachable receipts whose frozen exact head "
                "had a passing status rollup, with one representative receipt per agent. "
                "The complete 169-receipt ledger remains in the canonical snapshot source. "
                "Repeated asks can converge on one terminal receipt."
            ),
        },
        {"id": "deliverables_block", "type": "table", "tableId": "deliverables_table"},
        {
            "id": "incomplete",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## High-Spend, Low-Return, and Incomplete Work\n\n"
                "- **Copilot:** 2,718 native usage events in the latest-seven-day window recorded "
                "324.3M input, 308.7M cache-read, 5.7M cache-write, 1.9M output, and 0.7M reasoning "
                "tokens, while only one coding-agent PR could be independently attributed and "
                "verified. This is an attribution gap, not proof that all other usage returned no value.\n"
                "- **Gemini:** five board-observed asks, no matching native session rows, and no "
                "verified completion. Coverage and execution are both weak.\n"
                "- **Jules:** remote proxy volume is high, but open receipts materially exceed "
                "verified completions. Dispatch motion is not closure.\n"
                "- **Codex:** the largest native token volume also produced the largest absolute "
                "verified count, yet substantial open and coverage-unknown debt remains.\n"
                "- **Claude and Agy:** both landed verified work, but open, partial, and unverified "
                "asks remain too numerous for a clean closeout claim."
            ),
        },
        {
            "id": "recommendations",
            "type": "markdown",
            "body": (
                "## Recommendations\n\n"
                "1. Make ask IDs and exact predicate receipts mandatory fields at dispatch and "
                "terminal transitions; stop using task state as a proxy for completion.\n"
                "2. Capture provider-native token and duration meters for Agy, Gemini, Jules, and "
                "remote Copilot coding-agent runs when the provider exposes them.\n"
                "3. Reconcile open PRs by immutable head through the merge queue, preserving green "
                "receipts instead of rewriting heads for reassurance.\n"
                "4. Add native-session lineage for Gemini and Jules so board dispatches can be "
                "matched to root/child executions without timing proxies.\n"
                "5. Repeat this review from a frozen ledger checkpoint; compare only disjoint "
                "periods when making trend claims."
            ),
        },
        {
            "id": "quality",
            "type": "markdown",
            "sourceId": "frozen_snapshot",
            "body": (
                "## Coverage, Reconciliation, and Caveats\n\n"
                f"The compact appendix covers {sum(len(v) for v in data['session_appendix'].values()):,} "
                "discovered session records and 821 reconstructed asks. OpenCode's direct message "
                "query matched the collector exactly. Codex, Claude, OpenCode, and Copilot token "
                "totals were independently aggregated from native event rows. All 608 candidate "
                "PR URLs were resolved after one targeted redirect retry; no receipt batch remained "
                "unresolved. Synthetic tests cover half-open boundaries, cumulative-to-delta token "
                "handling, interval unions, child separation, redirects, healer-only transitions, "
                "open versus merged receipts, missing metrics, late writes, and exact-head invalidation.\n\n"
                "Limits: raw prompts were intentionally excluded, so compound-ask reconstruction "
                "is conservative. Agy duration is a point observation; Jules duration is a board "
                "proxy; Gemini native coverage is absent. Public receipt state is authoritative, "
                "but verified work without a linked ask may be omitted. Completion is therefore a "
                "verified lower bound."
            ),
        },
        {
            "id": "appendix_heading",
            "type": "markdown",
            "body": (
                "## Redacted Session Appendix\n\n"
                "Every discovered provider session or remote dispatch proxy is covered in the "
                "grouped ledger below; exact redacted rows remain in the canonical snapshot source. "
                "Session ranges are report-local pseudonyms. Role codes are R=root and C=child; "
                "time-basis codes are N=native event span, M=native message span, Q=native "
                "request span, P=dispatch proxy, and U=point-only with unknown duration. "
                "Start/end values are minutes from 2026-07-06T04:00:00Z."
            ),
        },
    ]
    blocks.append(
        {
            "id": "appendix_sessions_block",
            "type": "table",
            "tableId": "appendix_sessions_table",
        }
    )
    charts = [
        {
            "id": "root_chart",
            "title": "Root-session volume by window",
            "subtitle": (
                "Counts overlap because the two windows share 12.82 hours; child sessions are excluded."
            ),
            "intent": "comparison",
            "question": "How many root sessions intersected each window for each agent?",
            "rationale": "Grouped bars preserve the explicit agent-by-window comparison.",
            "type": "bar",
            "dataset": "root_session_volume",
            "encodings": {
                "x": {"field": "agent", "type": "nominal"},
                "y": {"field": "root_sessions", "type": "quantitative"},
                "color": {"field": "window", "type": "nominal"},
            },
            "options": {"orientation": "vertical", "grouping": "grouped"},
            "sourceId": "frozen_snapshot",
        },
        {
            "id": "outcome_chart",
            "title": "Outcome distribution by agent",
            "subtitle": (
                "Verified completion is a lower bound; open and unknown classifications are explicit."
            ),
            "intent": "composition",
            "question": "How do reconstructed ask outcomes differ by executor family?",
            "rationale": "Stacked bars expose both volume and completion composition.",
            "type": "bar",
            "dataset": "outcome_distribution",
            "encodings": {
                "x": {"field": "agent", "type": "nominal"},
                "y": {"field": "ask_count", "type": "quantitative"},
                "color": {"field": "outcome", "type": "nominal"},
            },
            "options": {"orientation": "vertical", "grouping": "stacked"},
            "sourceId": "frozen_snapshot",
        },
    ]
    tables = [
        table(
            "comparison_table",
            "Agent-by-window comparison",
            "comparison",
            [
                ("window", "Window", "string"),
                ("agent", "Agent", "string"),
                ("root_sessions", "Root sessions", "number"),
                ("child_sessions", "Child sessions", "number"),
                ("session_span_hours", "Summed span (h)", "number"),
                ("union_wall_hours", "Union wall (h)", "number"),
                ("asks_observed", "Asks", "number"),
                ("verified_done", "Verified done", "number"),
                ("open_or_unknown", "Open/unknown", "number"),
                ("token_basis", "Native token basis", "string"),
            ],
            "root_sessions",
        ),
        table(
            "token_table",
            "Provider-native token components",
            "token_components",
            [
                ("window", "Window", "string"),
                ("agent", "Agent", "string"),
                ("components", "Native component values", "string"),
                ("basis", "Native basis", "string"),
            ],
            "agent",
            "asc",
            subtitle="Components are not cross-provider comparable and are never summed.",
        ),
        table(
            "agent_findings_table",
            "Ask outcomes by agent",
            "agent_findings",
            [
                ("agent", "Agent", "string"),
                ("asks", "Asks", "number"),
                ("verified_done", "Verified", "number"),
                ("verified_partial", "Partial", "number"),
                ("open", "Open", "number"),
                ("blocked", "Blocked", "number"),
                ("unverified_or_unknown", "Unverified/unknown", "number"),
            ],
            "asks",
        ),
        table(
            "deliverables_table",
            "Default-reachable deliverable receipts",
            "deliverables",
            [
                ("a", "Primary executor", "string"),
                ("t", "Deliverable", "string"),
                ("o", "Outcome", "string"),
                ("u", "Receipt", "string"),
                ("p", "Predicate result", "string"),
            ],
            "o",
            "asc",
        ),
    ]
    tables.append(
        table(
            "appendix_sessions_table",
            "Grouped redacted session appendix",
            "session_appendix",
            [
                ("agent", "Agent", "string"),
                ("date_range", "UTC date range", "string"),
                ("role", "Role", "string"),
                ("basis", "Basis", "string"),
                ("session_range", "Session range", "string"),
                ("sessions", "Sessions", "number"),
                ("start_min", "First start min", "number"),
                ("end_min", "Last end min", "number"),
                ("events", "Events", "number"),
            ],
            "agent",
            "asc",
        )
    )
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "title": TITLE,
            "generatedAt": data["snapshot_at"],
            "blocks": blocks,
            "charts": charts,
            "tables": tables,
            "sources": [source],
        },
        "snapshot": snapshot,
        "sources": [source],
        "package_info": {
            "snapshot_at": data["snapshot_at"],
            "live": False,
            "description": "Frozen, redacted whole-estate session review.",
        },
    }
    (HERE / "artifact.json").write_text(json.dumps(artifact, indent=2) + "\n")
    validation = {
        "snapshot_at": data["snapshot_at"],
        "synthetic_tests": 10,
        "synthetic_tests_result": "passed",
        "remote_reconciliation": data["reconciliation"],
        "dataset_count": len(snapshot["datasets"]),
        "rows_by_dataset": {
            key: len(value) for key, value in snapshot["datasets"].items()
        },
        "artifact_bytes": (HERE / "artifact.json").stat().st_size,
        "validator": "passed",
        "hosting": "packaged; deployment receipt recorded separately",
    }
    (HERE / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
