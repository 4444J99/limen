import policy from "../../../../institutio/github/dependency-completion.json" with { type: "json" };

const KEY = "dependency-completion-hints:v1";
const SHA = /^[a-f0-9]{40}$/;
export class DependencyCompletionError extends Error {
  constructor(message, status = 400) { super(message); this.status = status; }
}
function requireValue(value, message, status = 400) {
  if (!value) throw new DependencyCompletionError(message, status);
}
function positive(value) { return Number.isSafeInteger(value) && value > 0; }
function authority(principal, configured, reading) {
  const roles = principal?.roles;
  requireValue(Array.isArray(roles), "dependency_completion_unauthorized", 403);
  if (reading) {
    requireValue(roles.includes("conductor"), "dependency_completion_unauthorized", 403);
  } else {
    requireValue(roles.length === 1 && roles[0] === "dependency_observer"
      && principal.principal_id === configured.principal_id, "dependency_completion_unauthorized", 403);
  }
  requireValue(configured.schema === "limen.dependency_completion_policy.v1"
    && configured.installed === true && positive(configured.max_records)
    && configured.max_records <= 100, "dependency_completion_not_installed", 503);
}
function validAssessment(value) {
  if (value === undefined) return true;
  return value && typeof value === "object"
    && typeof value.run_id === "string" && /^[A-Za-z0-9._:-]{1,256}$/.test(value.run_id)
    && value.automatic_acceptance === false
    && (value.status === "unmeasured" || (value.status === "reported"
      && typeof value.receipt_id === "string" && value.receipt_id.length <= 256
      && ["succeeded", "failed", "blocked", "cancelled", "partial"].includes(value.outcome)
      && typeof value.accepted_at === "string" && Number.isFinite(Date.parse(value.accepted_at))));
}
function records(value) {
  if (value === undefined) return [];
  requireValue(Array.isArray(value) && value.length <= 100
    && value.every(row => row && typeof row === "object"
      && positive(row.repository_id) && positive(row.run_id) && positive(row.run_attempt)
      && row.key === `${row.repository_id}:${row.run_id}:${row.run_attempt}`
      && typeof row.head_sha === "string" && SHA.test(row.head_sha)
      && typeof row.coordinate === "string" && typeof row.default_branch === "string"
      && typeof row.principal_id === "string" && typeof row.received_at === "string"
      && Number.isFinite(Date.parse(row.received_at))
      && row.assessment === "unmeasured" && row.automatic_acceptance === false
      && validAssessment(row.broker_assessment))
    && new Set(value.map(row => row.key)).size === value.length,
  "dependency_completion_storage_unmeasured", 503);
  return value;
}

// Hints only: no source code, credentials, provider launch, lease, debit or merge.
// The conductor must independently bind current GitHub evidence and use normal
// broker admission. This store is not a second task lifecycle authority.
export async function submitCompletionHint(storage, principal, input, configured = policy) {
  authority(principal, configured, false);
  requireValue(input && typeof input === "object" && !Array.isArray(input), "dependency_completion_invalid");
  const fields = ["repository_id", "run_id", "run_attempt", "head_sha"];
  requireValue(Object.keys(input).length === fields.length
    && fields.every(field => Object.hasOwn(input, field)), "dependency_completion_invalid");
  requireValue(positive(input.repository_id) && positive(input.run_id) && positive(input.run_attempt)
    && typeof input.head_sha === "string" && SHA.test(input.head_sha), "dependency_completion_invalid");
  const repository = configured.repositories?.[String(input.repository_id)];
  requireValue(repository && typeof repository.coordinate === "string"
    && typeof repository.default_branch === "string", "dependency_completion_scope_unconfigured", 403);
  const key = `${input.repository_id}:${input.run_id}:${input.run_attempt}`;
  return storage.transaction(async transaction => {
    const rows = records(await transaction.get(KEY));
    const existing = rows.find(row => row.key === key);
    if (existing) {
      requireValue(existing.head_sha === input.head_sha, "dependency_completion_replay_conflict", 409);
      return { ...existing, duplicate: true };
    }
    requireValue(rows.length < configured.max_records, "dependency_completion_capacity", 503);
    const row = { key, ...input, coordinate: repository.coordinate,
      default_branch: repository.default_branch, principal_id: principal.principal_id,
      received_at: new Date().toISOString(), assessment: "unmeasured", automatic_acceptance: false };
    await transaction.put(KEY, [...rows, row]);
    return { ...row, duplicate: false };
  });
}
export async function readCompletionHints(storage, principal, configured = policy) {
  authority(principal, configured, true);
  return { schema: "limen.dependency_completion_hints.v1", automatic_acceptance: false,
    hints: records(await storage.get(KEY)) };
}

export function completionWorkKey(hint) {
  return `dependency-completion:${hint.key}:${hint.head_sha}`;
}

// The supplied run ID is only a lookup hint. Read the graph from this keeper;
// never accept a caller-supplied receipt or promote predicate success to merge.
export async function reconcileCompletionAssessment(storage, principal, key, runId, readGraph, configured = policy) {
  authority(principal, configured, true);
  requireValue(typeof key === "string" && /^\d+:\d+:\d+$/.test(key)
    && typeof runId === "string" && /^[A-Za-z0-9._:-]{1,256}$/.test(runId), "dependency_assessment_invalid");
  const hint = records(await storage.get(KEY)).find(row => row.key === key);
  requireValue(hint, "dependency_completion_unknown", 404);
  const repository = configured.repositories?.[String(hint.repository_id)];
  requireValue(repository?.coordinate === hint.coordinate && repository?.default_branch === hint.default_branch,
    "dependency_completion_scope_unconfigured", 403);
  let graph;
  try { graph = await readGraph(runId); }
  catch { throw new DependencyCompletionError("dependency_assessment_unmeasured", 503); }
  requireValue(graph?.schema_version === "limen.conduct_graph.v1" && Array.isArray(graph.nodes)
    && graph.nodes.length === 1 && graph.root_run_id === runId, "dependency_assessment_scope_mismatch", 409);
  const run = graph.nodes[0];
  const packet = run?.packet;
  const binding = packet?.intent?.dependency_completion;
  const fields = ["repository_id", "run_id", "run_attempt", "head_sha"];
  requireValue(run.run_id === runId && packet?.work_key === completionWorkKey(hint)
    && packet.effect === "read" && packet.authority?.may_delegate === false
    && Array.isArray(packet.authority?.external_effects) && packet.authority.external_effects.length === 0
    && packet.authority?.repositories?.length === 1 && packet.authority.repositories[0] === hint.coordinate
    && binding && fields.every(field => binding[field] === hint[field])
    && packet.execution?.observed_heads?.dependency_head === hint.head_sha,
  "dependency_assessment_scope_mismatch", 409);
  const outcomes = { succeeded: "succeeded", failed: "failed", blocked: "blocked", cancelled: "cancelled", partial: "failed" };
  const accepted = (Array.isArray(run.receipts) ? run.receipts : []).filter(receipt =>
    receipt?.mutation_authorized === true && receipt.run_id === runId
    && receipt.lease_id === run.lease_id && receipt.lease_generation === run.lease?.generation
    && typeof receipt.receipt_id === "string" && typeof receipt.accepted_at === "string"
    && Number.isFinite(Date.parse(receipt.accepted_at))
    && Object.hasOwn(outcomes, receipt.outcome) && outcomes[receipt.outcome] === run.status
    && receipt.observed_heads_before?.dependency_head === hint.head_sha
    && receipt.observed_heads_after?.dependency_head === hint.head_sha
    && receipt.predicate?.command === packet.predicate
    && (receipt.outcome !== "succeeded" || receipt.predicate.exit_code === 0));
  requireValue(accepted.length <= 1, "dependency_assessment_receipts_ambiguous", 409);
  const receipt = accepted[0];
  const assessment = { run_id: runId, status: receipt ? "reported" : "unmeasured", automatic_acceptance: false,
    ...(receipt ? { receipt_id: receipt.receipt_id, outcome: receipt.outcome, accepted_at: receipt.accepted_at } : {}) };
  return storage.transaction(async transaction => {
    const rows = records(await transaction.get(KEY));
    const current = rows.find(row => row.key === key);
    requireValue(current && current.head_sha === hint.head_sha, "dependency_completion_changed", 409);
    requireValue(!current.broker_assessment || current.broker_assessment.run_id === runId,
      "dependency_assessment_binding_conflict", 409);
    // A later stale read must not erase an accepted historical observation.
    if (current.broker_assessment?.status === "reported") {
      requireValue(!receipt || current.broker_assessment.receipt_id === receipt.receipt_id,
        "dependency_assessment_receipt_conflict", 409);
      return current.broker_assessment;
    }
    current.broker_assessment = assessment;
    await transaction.put(KEY, rows);
    return assessment;
  });
}
