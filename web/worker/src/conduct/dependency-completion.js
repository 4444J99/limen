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
      && row.assessment === "unmeasured" && row.automatic_acceptance === false)
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
