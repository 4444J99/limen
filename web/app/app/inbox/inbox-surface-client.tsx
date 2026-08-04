"use client";

import { useMemo, useState } from "react";
import SurfaceNav from "../surface-nav";
import { type InboxPartition, type InboxRecord, type InboxSourceType, type InboxStatusData } from "../lib/inbox-model";

function formatDate(value?: string) {
  if (!value) return "Never";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(time));
}

type FilterPartition = InboxPartition | "all";
type SourceType = InboxSourceType;

type PendingMove = { kind: "move"; record: InboxRecord; targetPartition: InboxPartition };
type PendingCapture = {
  kind: "capture";
  draft: {
    title: string;
    sourceType: SourceType;
    sourceReference: string;
    bodyExcerpt: string;
    partition: InboxPartition;
  };
};
type PendingAction = PendingMove | PendingCapture | null;

type CaptureFormState = {
  title: string;
  sourceType: SourceType;
  sourceReference: string;
  bodyExcerpt: string;
  partition: InboxPartition;
  capturedBy: string;
};

const INBOX_PARTITIONS: InboxPartition[] = ["inbox", "entities", "tasks", "decisions", "links", "archive", "quarantine"];
const SOURCE_TYPES: SourceType[] = ["note", "url", "file", "source_ref"];

const PROVENANCE_PRESETS: Record<SourceType, string> = {
  note: "Free-form note or prose capture from human desk.",
  url: "External URL reference used to prove source origin.",
  file: "File handle attached as capture source reference.",
  source_ref: "Explicit source identifier from upstream connector.",
};

function makeRecordPreview(
  draft: PendingCapture["draft"],
  nowIso: string,
  capturedBy: string,
  policyConsequenceMap: Record<InboxPartition, string[]>,
) {
  return {
    id: `preview-${Date.now()}`,
    title: draft.title,
    source_type: draft.sourceType,
    source_reference: draft.sourceReference,
    body_excerpt: draft.bodyExcerpt,
    partition: draft.partition,
    captured_at: nowIso,
    captured_by: capturedBy,
    policy_consequences: policyConsequenceMap[draft.partition],
    provenance: {
      source_system: "static-form",
      source_reference: draft.sourceReference,
      observed_at: nowIso,
      policy_vector: ["operator-capture", draft.sourceType, draft.partition],
      source_note: PROVENANCE_PRESETS[draft.sourceType],
    },
  };
}

function policyConsequenceMap(data: InboxStatusData) {
  const inferred: Record<InboxPartition, string[]> = {
    inbox: ["No explicit partition yet; this record remains in inbox pending review."],
    entities: [],
    tasks: [],
    decisions: [],
    links: [],
    archive: [],
    quarantine: [],
  };
  for (const partition of INBOX_PARTITIONS) {
    inferred[partition] = [];
  }
  const defaults = [
    {
      partition: "entities" as const,
      lines: [
        "Classify as an entity candidate.",
        "Policy consequence: this path requires identity verification before graph edge creation.",
      ],
    },
    {
      partition: "tasks" as const,
      lines: [
        "Classify as task intake.",
        "Policy consequence: task routing remains owner-gated and read-only until dispatch.",
      ],
    },
    {
      partition: "decisions" as const,
      lines: [
        "Classify as decision artifact.",
        "Policy consequence: records here require rationale trace and replay evidence.",
      ],
    },
    {
      partition: "links" as const,
      lines: [
        "Classify as linkage evidence.",
        "Policy consequence: edges are non-authoritative until source signatures validate.",
      ],
    },
    {
      partition: "archive" as const,
      lines: [
        "Classify as archive.",
        "Policy consequence: suppress from active steering and prevent automation routing.",
      ],
    },
    {
      partition: "quarantine" as const,
      lines: [
        "Classify as quarantine.",
        "Policy consequence: block runtime/automation until release clearance.",
      ],
    },
  ];
  for (const row of defaults) {
    inferred[row.partition] = row.lines;
  }
  const existing = Object.entries(data.records.reduce((acc, record) => {
    acc[record.partition] = record.policy_consequences;
    return acc;
  }, {} as Partial<Record<InboxPartition, string[]>>));
  for (const [partition, consequences] of existing) {
    if (!inferred[partition as InboxPartition]?.length) {
      inferred[partition as InboxPartition] = consequences;
    }
  }
  return inferred;
}

function partitionLabel(partition: InboxPartition) {
  return partition === "inbox" ? "Inbox" : partition.charAt(0).toUpperCase() + partition.slice(1);
}

function sortRecords(records: InboxRecord[]) {
  return [...records].sort((a, b) => new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime());
}

export default function InboxSurfaceClient({ initialStatus }: { initialStatus: InboxStatusData }) {
  const [records, setRecords] = useState<InboxRecord[]>(() => sortRecords(initialStatus.records || []));
  const [filter, setFilter] = useState<FilterPartition>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string>(records[0]?.id || "");
  const [pending, setPending] = useState<PendingAction>(null);
  const [capture, setCapture] = useState<CaptureFormState>({
    title: "",
    sourceType: "note",
    sourceReference: "",
    bodyExcerpt: "",
    partition: "inbox",
    capturedBy: "owner",
  });

  const consequences = useMemo(() => policyConsequenceMap(initialStatus), [initialStatus.records]);
  const filtered = useMemo(() => {
    return records.filter((record) => {
      const matchesPartition = filter === "all" || record.partition === filter;
      const haystack = `${record.title} ${record.body_excerpt} ${record.source_reference}`.toLowerCase();
      const matchesQuery = !query || haystack.includes(query.toLowerCase());
      return matchesPartition && matchesQuery;
    });
  }, [records, filter, query]);
  const selectedRecord = useMemo(() => records.find((record) => record.id === selectedId) || records[0] || null, [records, selectedId]);
  const partitionCounts = useMemo(() => {
    const counts = {
      inbox: 0,
      entities: 0,
      tasks: 0,
      decisions: 0,
      links: 0,
      archive: 0,
      quarantine: 0,
    };
    for (const record of records) counts[record.partition] += 1;
    return counts;
  }, [records]);

  function openCaptureConfirmation(event: React.FormEvent) {
    event.preventDefault();
    if (!capture.title.trim()) return;
    const now = new Date().toISOString();
    const draft = {
      title: capture.title.trim(),
      sourceType: capture.sourceType,
      sourceReference: capture.sourceReference.trim() || `${capture.sourceType}://${now}`,
      bodyExcerpt: capture.bodyExcerpt.trim(),
      partition: capture.partition,
    };
    setPending({ kind: "capture", draft });
  }

  function openMoveConfirmation(record: InboxRecord, targetPartition: InboxPartition) {
    if (record.partition === targetPartition) return;
    setPending({
      kind: "move",
      record,
      targetPartition,
    });
  }

  function clearPending() {
    setPending(null);
  }

  function confirmPendingAction() {
    if (!pending) return;
    if (pending.kind === "capture") {
      const now = new Date().toISOString();
      const nextRecord: InboxRecord = makeRecordPreview(
        pending.draft,
        now,
        capture.capturedBy || "owner",
        consequences,
      );
      setRecords((prev) => sortRecords([nextRecord, ...prev]));
      setSelectedId(nextRecord.id);
      setCapture({
        title: "",
        sourceType: "note",
        sourceReference: "",
        bodyExcerpt: "",
        partition: "inbox",
        capturedBy: "owner",
      });
    } else {
      const moved = pending.record.id;
      const nextPartition = pending.targetPartition;
      setRecords((prev) =>
        sortRecords(prev.map((record) => (
          record.id === moved ? { ...record, partition: nextPartition } : record
        ))),
      );
    }
    setPending(null);
  }

  function nextPartitions(current: InboxPartition) {
    return INBOX_PARTITIONS.filter((partition) => partition !== current);
  }

  const pendingLabel = pending?.kind === "capture"
    ? `Capture ${pending.draft.title} into ${partitionLabel(pending.draft.partition)}`
    : pending?.kind === "move"
      ? `Move ${pending.record.title} to ${partitionLabel(pending.targetPartition)}`
      : "";
  const previewRecord = pending?.kind === "capture"
    ? makeRecordPreview(pending.draft, new Date().toISOString(), capture.capturedBy || "owner", consequences)
    : pending?.kind === "move"
      ? pending.record
      : null;
  const previewConsequences = pending
    ? pending.kind === "capture"
      ? consequences[pending.draft.partition]
      : consequences[pending.targetPartition]
    : [];

  return (
    <main className="audienceShell inboxShell">
      <SurfaceNav active="inbox" />
      <header className="audienceHeader">
        <p className="caption">Owner surface</p>
        <h1>Inbox</h1>
        <p>Capture notes, URLs, files, and source references and route them through explicit partition review.</p>
      </header>

      <section className="audienceMetrics" aria-label="Inbox throughput">
        <div>
          <span>Total captures</span>
          <strong>{records.length}</strong>
          <p>From static source fixtures and operator intake</p>
        </div>
        <div>
          <span>Inbox queue</span>
          <strong>{partitionCounts.inbox}</strong>
          <p>Pending classification</p>
        </div>
        <div>
          <span>Active partitions</span>
          <strong>{Math.max(0, records.filter((record) => record.partition !== "inbox").length)}</strong>
          <p>Entities, tasks, decisions, links, archive, quarantine</p>
        </div>
        <div>
          <span>Last updated</span>
          <strong>{formatDate(initialStatus.generated_at)}</strong>
          <p>Static snapshot metadata</p>
        </div>
      </section>

      <section className="audienceGrid inboxWorkspace">
        <div className="surfacePanel wide">
          <div className="panelTitle">
            <span>Quick capture</span>
            <strong>Create a source record and choose explicit destination partition.</strong>
          </div>
          <form className="assignPanel inboxCaptureForm" onSubmit={openCaptureConfirmation}>
            <label>
              <span>Title</span>
              <input
                value={capture.title}
                onChange={(event) => setCapture((state) => ({ ...state, title: event.target.value }))}
                placeholder="Task, decision, or relation title"
                required
              />
            </label>
            <label>
              <span>Source type</span>
              <select
                value={capture.sourceType}
                onChange={(event) => setCapture((state) => ({ ...state, sourceType: event.target.value as SourceType }))}
              >
                {SOURCE_TYPES.map((sourceType) => (
                  <option key={sourceType} value={sourceType}>
                    {sourceType}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Source reference</span>
              <input
                value={capture.sourceReference}
                onChange={(event) => setCapture((state) => ({ ...state, sourceReference: event.target.value }))}
                placeholder={capture.sourceType === "url" ? "https://..." : "task://... or file://..."}
              />
            </label>
            <label>
              <span>Body / excerpt</span>
              <textarea
                value={capture.bodyExcerpt}
                onChange={(event) => setCapture((state) => ({ ...state, bodyExcerpt: event.target.value }))}
                placeholder="What was captured?"
                rows={4}
              />
            </label>
            <label>
              <span>Initial partition</span>
              <select
                value={capture.partition}
                onChange={(event) => setCapture((state) => ({ ...state, partition: event.target.value as InboxPartition }))}
              >
                {INBOX_PARTITIONS.map((partition) => (
                  <option key={partition} value={partition}>
                    {partitionLabel(partition)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Captured by</span>
              <input
                value={capture.capturedBy}
                onChange={(event) => setCapture((state) => ({ ...state, capturedBy: event.target.value || "owner" }))}
              />
            </label>
            <button type="submit">Review capture</button>
          </form>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Filters</span>
            <strong>Search and partition by explicit routing state.</strong>
          </div>
          <div className="inboxFilters">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search title, excerpt, or source..."
            />
            <select value={filter} onChange={(event) => setFilter(event.target.value as FilterPartition)}>
              <option value="all">All</option>
              {INBOX_PARTITIONS.map((partition) => (
                <option key={partition} value={partition}>
                  {partitionLabel(partition)}
                </option>
              ))}
            </select>
          </div>
          <div className="inboxRecords">
            {filtered.length === 0 ? (
              <p className="muted">No records match the current filter.</p>
            ) : (
              filtered.map((record) => (
                <button
                  key={record.id}
                  type="button"
                  className={`inboxRow ${selectedId === record.id ? "active" : ""}`}
                  onClick={() => setSelectedId(record.id)}
                >
                  <span className="inboxBadge">
                    {record.partition.toUpperCase()}
                  </span>
                  <strong>{record.title}</strong>
                  <small>{record.source_type} · {record.source_reference}</small>
                </button>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="audienceGrid inboxWorkspace">
        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Partition ledger</span>
            <strong>Source routing and policy consequence summary.</strong>
          </div>
          <div className="inboxLedger">
            {INBOX_PARTITIONS.map((partition) => (
              <article key={partition}>
                <span>{partitionLabel(partition)}</span>
                <strong>{partitionCounts[partition]}</strong>
              </article>
            ))}
          </div>
        </div>
        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Provenance & policy preview</span>
            <strong>Review this record before any partition move.</strong>
          </div>
          {!selectedRecord ? (
            <p className="muted">Select a record to inspect provenance and policy consequences.</p>
          ) : (
            <>
              <h3 style={{ marginTop: 0 }}>{selectedRecord.title}</h3>
              <p className="surfaceCopy" style={{ marginBottom: "0.8rem" }}>{selectedRecord.body_excerpt}</p>
              <dl className="inboxMeta">
                <dt>Source</dt>
                <dd>{selectedRecord.source_type}</dd>
                <dt>Reference</dt>
                <dd>{selectedRecord.source_reference}</dd>
                <dt>Partition</dt>
                <dd>{partitionLabel(selectedRecord.partition)}</dd>
                <dt>Captured at</dt>
                <dd>{formatDate(selectedRecord.captured_at)}</dd>
                <dt>Captured by</dt>
                <dd>{selectedRecord.captured_by}</dd>
              </dl>
              <p className="surfaceCopy" style={{ marginBottom: "0.6rem" }}>
                Provenance source: <strong>{selectedRecord.provenance.source_system}</strong>
              </p>
              <p className="surfaceCopy" style={{ marginBottom: "0.8rem" }}>{selectedRecord.provenance.source_note}</p>
              <div className="surfaceCopy">
                <p><strong>Policy vector:</strong> {selectedRecord.provenance.policy_vector.join(" · ") || "n/a"}</p>
              </div>
              <ul className="rankList">
                {(selectedRecord.policy_consequences || []).map((item) => (
                  <li key={item}>
                    <span>Policy consequence</span>
                    <strong>{item}</strong>
                  </li>
                ))}
              </ul>

              <label style={{ display: "grid", gap: "6px", marginTop: "12px" }}>
                <span>Move to partition</span>
                <div className="buttonRow">
                  <select
                    defaultValue="none"
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value === "none" || value === selectedRecord.partition) {
                        return;
                      }
                      const target = value as InboxPartition;
                      if (target) {
                        openMoveConfirmation(selectedRecord, target);
                      }
                    }}
                  >
                    <option value="none">select destination</option>
                    {nextPartitions(selectedRecord.partition).map((partition) => (
                      <option key={partition} value={partition}>
                        {partitionLabel(partition)}
                      </option>
                    ))}
                  </select>
                </div>
              </label>
            </>
          )}
        </div>
      </section>

      {pending && previewRecord ? (
        <section className="surfacePanel inboxConfirm" aria-label="Pending classification">
          <div className="panelTitle">
            <span>Pending classification</span>
            <strong>{pendingLabel}</strong>
          </div>
          <p>Provenance and policy consequences are displayed before mutation is applied.</p>
          <p><strong>Target partition:</strong> {pending.kind === "capture" ? partitionLabel(pending.draft.partition) : partitionLabel(pending.targetPartition)}</p>
          <ul className="rankList">
            {previewConsequences.map((line) => (
              <li key={line}>
                <span>Policy consequence</span>
                <strong>{line}</strong>
              </li>
            ))}
          </ul>
          <div className="inboxConfirmActions">
            <button type="button" onClick={confirmPendingAction} className="button">
              Apply with policy review
            </button>
            <button type="button" onClick={clearPending} className="button">
              Cancel
            </button>
          </div>
        </section>
      ) : null}
    </main>
  );
}
