import { canonicalHash } from "./schemas.js";

export const INVENTORY_CEILING = 250;
export const INVENTORY_MAX_AGE_MS = 900000;
const GENERATION = /^[0-9a-f]{64}$/;
const CONNECTION_KINDS = ["pull_requests", "issues", "branches", "checks"];
const contexts = new WeakSet();

export class InventoryAdmissionError extends Error {
  constructor(code) {
    super(code);
    this.status = 409;
  }
}

function requireFact(condition, code) {
  if (!condition) throw new InventoryAdmissionError(code);
}

function integer(value, code) {
  requireFact(Number.isSafeInteger(value) && value >= 0, code);
  return value;
}

function timestamp(value) {
  requireFact(typeof value === "string"
    && /^(?!0000)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(value)
    && Number.isFinite(Date.parse(value))
    && new Date(value).toISOString().slice(0, 19) === value.slice(0, 19), "inventory_timestamp_invalid");
  return Date.parse(value);
}

// Administrator-installed authority only. No request payload selects scope,
// principal, generation, ceiling, freshness, or an override.
export function configuredInventoryAuthority(env) {
  let value;
  try { value = JSON.parse(env.LIMEN_INVENTORY_AUTHORITY || "null"); } catch { value = null; }
  requireFact(value?.schema_version === "limen.inventory_authority.v1"
    && typeof value.principal_id === "string" && value.principal_id.length > 0
    && GENERATION.test(value.source_generation || "")
    && Array.isArray(value.repository_ids) && value.repository_ids.length > 0
    && value.repository_ids.length <= 10000
    && value.repository_ids.every((id) => typeof id === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(id))
    && new Set(value.repository_ids).size === value.repository_ids.length,
  "inventory_admission_adapter_unavailable");
  return Object.freeze({ schema_version: value.schema_version, principal_id: value.principal_id,
    source_generation: value.source_generation, repository_ids: Object.freeze([...value.repository_ids].sort()) });
}

export function requireInventoryCollector(authority, principal) {
  requireFact(authority && principal?.principal_id === authority.principal_id
    && principal.roles?.length === 1 && principal.roles[0] === "inventory_collector",
  "inventory_collector_unauthorized");
}

// This is the Worker counterpart of inventory_admission.inventory_count. It
// verifies the collector's existing content and per-repository cursor receipts.
export async function inventoryCount(observation, authority, now = new Date()) {
  requireFact(authority, "inventory_admission_adapter_unavailable");
  requireFact(observation?.schema === "limen.github-estate-census.v1", "inventory_schema_invalid");
  const report = observation.source_report;
  requireFact(report?.exhaustive === true && Array.isArray(observation.failures)
    && observation.failures.length === 0, "inventory_partial_or_unknown");
  requireFact(report.source_generation === authority.source_generation, "inventory_generation_changed");
  const observed = timestamp(report.generated_at);
  requireFact(now.getTime() >= observed && now.getTime() - observed <= INVENTORY_MAX_AGE_MS, "inventory_stale");
  const { repositories, cursors, leaves, repository_receipts: receipts } = observation;
  requireFact([repositories, cursors, leaves, receipts].every(Array.isArray), "inventory_private_full_facts_required");
  const aliases = new Map();
  for (const row of repositories) {
    requireFact(row && typeof row.name_with_owner === "string" && row.name_with_owner.split("/").length === 2
      && !aliases.has(row.name_with_owner)
      && ((typeof row.repository_id === "string" && row.repository_id.length > 0)
        || (Number.isSafeInteger(row.repository_id) && row.repository_id > 0)), "inventory_repository_identity_invalid");
    aliases.set(row.name_with_owner, String(row.repository_id));
  }
  requireFact(JSON.stringify([...new Set(aliases.values())].sort()) === JSON.stringify(authority.repository_ids),
    "inventory_scope_changed");
  const summary = report.cursor;
  requireFact(summary?.leaf_count_complete === true
    && integer(report.normalized_leaf_count, "inventory_leaf_count_invalid") === leaves.length
    && integer(summary.known_leaf_count, "inventory_leaf_count_invalid") === leaves.length,
  "inventory_leaf_count_invalid");
  requireFact(report.content_sha256 === await canonicalHash(leaves), "inventory_content_digest_invalid");
  requireFact(summary.repository?.exhaustive === true
    && integer(summary.repository.expected_total, "inventory_repository_total_unknown") === repositories.length
    && integer(summary.repository.known_count, "inventory_repository_total_unknown") === repositories.length
    && integer(summary.repository.page_count, "inventory_repository_pagination_incomplete") > 0,
  "inventory_repository_pagination_incomplete");
  const rows = new Map([...aliases.keys()].map((name) => [name, []]));
  for (const cursor of cursors) {
    requireFact(rows.has(cursor?.repository), "inventory_connection_receipt_invalid");
    rows.get(cursor.repository).push(cursor);
  }
  const received = new Set();
  const counts = new Map();
  for (const receipt of receipts) {
    const name = receipt?.repository;
    requireFact(aliases.has(name) && !received.has(name)
      && String(receipt.repository_id) === aliases.get(name)
      && receipt.source_generation === authority.source_generation && receipt.complete === true,
    "inventory_connection_receipt_invalid");
    received.add(name);
    const connections = rows.get(name);
    requireFact(connections.length === CONNECTION_KINDS.length
      && CONNECTION_KINDS.every((kind) => connections.filter((row) => row.kind === kind).length === 1),
    "inventory_connection_partition_missing");
    requireFact(connections.every((row) => row.complete === true && row.exhaustive === true
      && GENERATION.test(row.source_generation || "") && row.source_generation === connections[0].source_generation),
    "inventory_connection_partition_incomplete");
    requireFact(receipt.connection_receipt_digest === await canonicalHash(connections), "inventory_connection_receipt_invalid");
    const pr = connections.find((row) => row.kind === "pull_requests");
    const count = integer(pr.expected_total, "inventory_pr_total_unknown");
    requireFact(integer(pr.known_count, "inventory_pr_total_unknown") === count && pr.page_cursor === null
      && (integer(pr.page_count, "inventory_pr_pagination_invalid") > 0 || count === 0),
    "inventory_pr_pagination_incomplete");
    counts.set(name, count);
  }
  requireFact(received.size === aliases.size, "inventory_repository_receipts_required");
  const seen = new Map();
  const named = new Set();
  const observedCounts = new Map([...aliases.keys()].map((name) => [name, 0]));
  for (const leaf of leaves) {
    requireFact(leaf && typeof leaf === "object" && !Array.isArray(leaf), "inventory_content_digest_invalid");
    if (leaf.kind !== "pull_request") continue;
    const number = integer(leaf.number, "inventory_pr_identity_invalid");
    requireFact(aliases.has(leaf.repository) && number > 0
      && typeof leaf.author_login === "string" && leaf.author_login.length > 0, "inventory_pr_identity_or_author_unknown");
    const namedKey = JSON.stringify([leaf.repository, number]);
    requireFact(!named.has(namedKey), "inventory_pr_duplicate");
    named.add(namedKey);
    observedCounts.set(leaf.repository, observedCounts.get(leaf.repository) + 1);
    const key = JSON.stringify([aliases.get(leaf.repository), number]);
    const author = leaf.author_login.toLowerCase();
    requireFact(!seen.has(key) || seen.get(key) === author, "inventory_migration_conflict");
    seen.set(key, author);
  }
  requireFact([...counts].every(([name, count]) => observedCounts.get(name) === count), "inventory_pr_total_changed");
  return [...seen.values()].filter((author) => author === "4444j99").length;
}

export async function acceptInventoryObservation(authority, principal, observation, prior, now) {
  requireInventoryCollector(authority, principal);
  const count = await inventoryCount(observation, authority, now);
  const started = timestamp(observation.inventory_collection?.started_at);
  const observed = timestamp(observation.source_report.generated_at);
  requireFact(started <= observed && now.getTime() - started <= INVENTORY_MAX_AGE_MS
    && observation.cursors.every((row) => row.reused === false), "inventory_fresh_collection_required");
  if (prior) requireFact(observed > timestamp(prior.observation?.source_report?.generated_at), "inventory_observation_replayed");
  // Deliberately omit local Git census, universe baselines, and arbitrary extras.
  const keys = ["schema", "source_report", "repositories", "cursors", "leaves", "failures", "repository_receipts", "inventory_collection"];
  return { authority_sha256: await canonicalHash(authority), principal_id: principal.principal_id,
    observation: structuredClone(Object.fromEntries(keys.map((key) => [key, observation[key]]))),
    accepted_at: now.toISOString(), count };
}

export async function inventoryProjectionContext(authority, stored, now) {
  requireFact(authority && stored && stored.principal_id === authority.principal_id
    && stored.authority_sha256 === await canonicalHash(authority), "inventory_admission_adapter_unavailable");
  const count = await inventoryCount(stored.observation, authority, now);
  const context = Object.freeze({ count,
    collectionStartedAt: timestamp(stored.observation.inventory_collection?.started_at),
    repositories: Object.freeze(stored.observation.repositories.map((row) => row.name_with_owner)) });
  contexts.add(context);
  return context;
}

// The projection obtains context only from authenticated private keeper custody.
// Neither task fields nor a lookalike serialized context can grant admission.
function routineGeneration(task) {
  const labels = Array.isArray(task?.labels) ? new Set(task.labels) : new Set();
  return /^(GEN-|BLD-|BLD2-)/.test(String(task?.id || ""))
    || (labels.has("generated") && labels.has("build-out"));
}

export function inventoryAdmissionDenied(prior, candidate) {
  return (prior == null || prior.status === "open")
    && ["dispatched", "in_progress"].includes(candidate.status)
    && (routineGeneration(prior) || routineGeneration(candidate));
}

export function inventoryClassificationChanged(prior, candidate) {
  return routineGeneration(prior) && !routineGeneration(candidate);
}

export function requireInventoryCapacity(board, prior, candidate, context) {
  if (routineGeneration(prior) && ["dispatched", "in_progress"].includes(prior.status)) {
    requireFact(prior.repo === candidate.repo, "inventory_reservation_repository_immutable");
  }
  if (!inventoryAdmissionDenied(prior, candidate)) return;
  requireFact(contexts.has(context), "inventory_admission_adapter_unavailable");
  requireFact(context.repositories.includes(candidate.repo)
    && (prior == null || context.repositories.includes(prior.repo)), "inventory_task_scope_changed");
  const active = new Set((board.tasks || []).filter((task) => routineGeneration(task)
    && ["dispatched", "in_progress"].includes(task.status)).map((task) => task.id));
  const held = Object.values(board.inventory_growth_reservations || {}).filter((row) => {
    if (!row.settled_at && active.has(row.task_id)) return false;
    return !row.settled_at || !context.repositories.includes(row.repository)
      || context.collectionStartedAt <= timestamp(row.settled_at);
  });
  requireFact(context.count + active.size + held.length < INVENTORY_CEILING, "inventory_growth_ceiling");
}

export function eventRequiresInventory(board, event) {
  const prior = (board.tasks || []).find((task) => task.id === event.task_id);
  const intent = event.intent;
  const candidate = intent ? { ...prior, ...(intent.task || intent.patch || {}) }
    : { ...prior, status: event.status };
  return inventoryAdmissionDenied(prior, candidate);
}

export function recordInventoryTransition(board, prior, candidate, event) {
  if (!(routineGeneration(prior) || routineGeneration(candidate))) return;
  const active = ["dispatched", "in_progress"];
  const key = String(event.lease_id || "");
  if (!active.includes(prior?.status) && !active.includes(candidate.status)) return;
  requireFact(key.length > 0, "inventory_reservation_identity_required");
  board.inventory_growth_reservations ||= {};
  const ledger = board.inventory_growth_reservations;
  const existing = Object.values(ledger).find((row) => row.task_id === candidate.id && !row.settled_at);
  const row = existing || { task_id: candidate.id, repository: String(candidate.repo || prior?.repo || ""),
    lease_id: key, started: prior?.status === "in_progress", reserved_at: event.timestamp };
  ledger[row.lease_id] = row;
  if (candidate.status === "in_progress") row.started = true;
  if (active.includes(prior?.status) && !active.includes(candidate.status)) {
    // Only a canonical prelaunch refund may drop custody immediately. Unknown
    // outcomes and post-launch settlement retain their slot until fresh coverage.
    const repair = event.intent?.log?.lifecycle_repair;
    // Called after projection transition/receipt validation and actual refund.
    const refunded = prior.status === "dispatched"
      && ((candidate.status === "open" && !["plan-handoff-complete", "provider-reroute"].includes(repair)
        && (event.intent?.kind === "task.status" || event.budget_action === "refund"))
        || (candidate.status === "failed" && event.intent?.kind === "task.status"
          && repair === "prelaunch-successor-hold"));
    if (!row.started && refunded) delete ledger[row.lease_id];
    else row.settled_at = event.timestamp;
  }
}
