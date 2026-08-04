import { createHash, randomUUID } from "node:crypto";

export const POLICY_VERSION = "zeta-03-policy-v1";

const DEFAULT_NOW = new Date().toISOString();

export type PolicyPrincipalType = "owner" | "collaborator" | "service" | "agent";

export type PartitionRole = "owner" | "admin" | "editor" | "viewer" | "auditor";

export type PolicyAction =
  | "partition.read"
  | "partition.write"
  | "partition.grant"
  | "work.read"
  | "work.write"
  | "work.review"
  | "note.read"
  | "note.write"
  | "artifact.read"
  | "artifact.write"
  | "decision.read"
  | "decision.write"
  | "search.read"
  | "search.index"
  | "automation.run"
  | "audit.read"
  | "audit.write"
  | "export.read"
  | "export.write"
  | "portal.view"
  | "portal.contribute"
  | "portal.edit";

export type PortalCapability = "viewer" | "contributor" | "editor";

export type PortalResource =
  | "dashboard"
  | "people"
  | "organizations"
  | "engagements"
  | "projects"
  | "tasks"
  | "commitments"
  | "decisions"
  | "meetings"
  | "notes"
  | "artifacts"
  | "search";

export interface PolicyPrincipal {
  principalId: string;
  principalType: PolicyPrincipalType;
}

export interface PartitionMembership {
  principalId: string;
  partitionId: string;
  role: PartitionRole;
  grantedBy: string;
  grantedAt: string;
  startAt: string;
  endAt: string | null;
}

export interface CapabilityGrant {
  id: string;
  principalId: string;
  partitionId: string;
  resource: string;
  action: PolicyAction | "*" ;
  effect: "allow" | "deny";
  issuedBy: string;
  issuedAt: string;
  expiresAt: string | null;
}

export interface PolicyRequest {
  principalId: string;
  partitionId: string;
  principalType: PolicyPrincipalType;
  action: PolicyAction;
  resource: string;
  fields?: string[];
  memberships: PartitionMembership[];
  grants: CapabilityGrant[];
  now?: string;
  roleOverride?: PartitionRole;
}

export interface PolicyDecision {
  allowed: boolean;
  reasonCode: string;
  reason: string;
  policyVersion: string;
  principalId: string;
  partitionId: string;
  action: PolicyAction;
  resource: string;
  grantedFields: string[] | null;
  redactedFields: string[] | null;
  resolvedRole: PartitionRole;
}

export interface PortalNavigationSeed {
  id: string;
  label: string;
  href: string;
  minimumCapability: PortalCapability;
}

export interface PortalNavigationLink extends PortalNavigationSeed {
  href: string;
  partitionId: string;
}

export interface PortalProjectionCounts {
  visible: number;
  droppedOwnerOnly: number;
}

export interface PortalProjectionError {
  code: string;
  message: string;
}

export interface PortalProjectionEnvelope<T extends { partitionId: string; [key: string]: unknown }> {
  principalId: string;
  principalType: PolicyPrincipalType;
  partitionId: string;
  resource: PortalResource;
  requestedCapability: PortalCapability;
  resolvedCapability: PortalCapability;
  granted: boolean;
  rows: readonly T[];
  counts: PortalProjectionCounts;
  links: readonly PortalNavigationLink[];
  errors: readonly PortalProjectionError[];
}

export interface PortalProjectionInput<T extends { partitionId: string; [key: string]: unknown }> {
  principalId: string;
  principalType: PolicyPrincipalType;
  partitionId: string;
  resource: PortalResource;
  memberships: PartitionMembership[];
  grants: CapabilityGrant[];
  now?: string;
  requestedCapability: PortalCapability;
  rows: readonly T[];
  navigation: readonly PortalNavigationSeed[];
  ownerOnly?: (row: T) => boolean;
  explicitlySharedRowIds?: readonly string[];
}

export type PortalRuntimeSurface = "session" | "cache" | "search" | "jobs" | "downloads";

export interface PortalRuntimeInvalidation {
  surface: PortalRuntimeSurface;
  key: string;
  reason: string;
}

export interface PortalOwnerPreviewInput<T extends { partitionId: string; [key: string]: unknown }> extends Omit<
  PortalProjectionInput<T>,
  "principalId" | "principalType"
> {
  principalId: string;
  principalType: "owner";
  previewPrincipalId: string;
  previewPrincipalType?: PolicyPrincipalType;
}

export interface PortalGrantRevocationInput {
  principalId: string;
  principalType: PolicyPrincipalType;
  partitionId: string;
  grant: CapabilityGrant;
  now?: string;
  reason?: "revoked" | "expired";
  requestedBy?: string;
  requestId?: string;
}

export interface PortalGrantRevocationReceipt {
  receiptId: string;
  status: "revoked" | "expired";
  principalId: string;
  principalType: PolicyPrincipalType;
  partitionId: string;
  principalGrantee: string;
  grantId: string;
  resource: string;
  action: PolicyAction | "*";
  requestedBy: string;
  createdAt: string;
  invalidations: readonly PortalRuntimeInvalidation[];
  reason: string;
}

export interface PortalGrantProposalInput {
  principalId: string;
  principalType: PolicyPrincipalType;
  partitionId: string;
  requestedBy: string;
  resource: PortalResource;
  requestedCapability: PortalCapability;
  memberships: PartitionMembership[];
  grants: CapabilityGrant[];
  now?: string;
  reason?: string;
  proposalId?: string;
}

export interface PortalGrantProposalReceipt {
  proposalId: string;
  status: "preview";
  principalId: string;
  principalType: PolicyPrincipalType;
  requestedBy: string;
  partitionId: string;
  resource: PortalResource;
  requestedCapability: PortalCapability;
  resolvedCapability: PortalCapability;
  allowed: boolean;
  invitationDeliveryEnabled: false;
  reasonCode: string;
  reason: string;
  policyVersion: string;
  createdAt: string;
}

export type PortalMutationKind = "comment" | "acknowledgement" | "upload" | "task.transition";
export type PortalTaskTransition = "acknowledge" | "start" | "wait" | "block" | "complete" | "reopen";
export type PortalTaskState = "open" | "in_progress" | "waiting" | "blocked" | "completed" | "reopened";

export interface PortalMutationInput {
  kind: PortalMutationKind;
  principalId: string;
  principalType: PolicyPrincipalType;
  partitionId: string;
  resource: PortalResource;
  targetId: string;
  memberships: PartitionMembership[];
  grants: CapabilityGrant[];
  now?: string;
  requestId?: string;
  requestedBy?: string;
  requestedCapability?: PortalCapability;
}

export interface PortalCommentInput extends PortalMutationInput {
  kind: "comment";
  body: string;
}

export interface PortalAcknowledgementInput extends PortalMutationInput {
  kind: "acknowledgement";
  acknowledged: boolean;
}

export interface PortalUploadInput extends PortalMutationInput {
  kind: "upload";
  filename: string;
  mimeType: string;
  sizeBytes: number;
  sha256?: string;
}

export interface PortalTaskTransitionInput extends PortalMutationInput {
  kind: "task.transition";
  transition: PortalTaskTransition;
  currentTaskState?: PortalTaskState;
}

export interface PortalMutationReceipt {
  mutationId: string;
  kind: PortalMutationKind;
  status: "denied" | "allowed" | "quarantined";
  principalId: string;
  principalType: PolicyPrincipalType;
  partitionId: string;
  resource: PortalResource;
  targetId: string;
  requestedCapability: PortalCapability;
  resolvedCapability: PortalCapability;
  allowed: boolean;
  reasonCode: string;
  reason: string;
  policyVersion: string;
  createdAt: string;
  auditEvent?: AuditAppendEvent;
}

export interface PortalUploadMutationReceipt extends PortalMutationReceipt {
  kind: "upload";
  filename: string;
  mimeType: string;
  sizeBytes: number;
  quarantined: boolean;
  quarantineReasons: readonly string[];
}

export interface PortalTaskTransitionReceipt extends PortalMutationReceipt {
  kind: "task.transition";
  transition: PortalTaskTransition;
  currentTaskState?: PortalTaskState;
  allowedTransitions?: readonly PortalTaskTransition[];
}

export interface PolicyDecisionMatrixCell {
  principalId: string;
  partitionId: string;
  principalType: PolicyPrincipalType;
  role: PartitionRole;
  action: PolicyAction;
  resource: string;
  allowed: boolean;
  reasonCode: string;
  grantedFields: string[] | null;
  redactedFields: string[] | null;
}

export interface PolicyDecisionMatrixInput {
  principals: PolicyPrincipal[];
  partitions: string[];
  memberships: PartitionMembership[];
  grants: CapabilityGrant[];
  actions?: readonly PolicyAction[];
  now?: string;
}

export interface PolicyMatrix {
  rows: PolicyDecisionMatrixCell[];
}

export interface PolicyRedactionInput extends PolicyRequest {
  payload: Record<string, unknown>;
}

export interface PolicyRedactionResult {
  decision: PolicyDecision;
  redactedPayload: Record<string, unknown>;
  grantedFields: string[] | null;
  redactedFields: string[] | null;
  droppedFields: string[];
}

export interface PolicyLeakageFinding {
  path: string;
  field: string;
  reason: string;
}

export interface AuditAppendEvent {
  id: string;
  actor_id: string;
  partition_id: string;
  causation_id: string;
  correlation_id: string;
  action: PolicyAction;
  resource_type: string;
  resource_id: string;
  decision_code: string;
  decision_reason: string;
  policy_version: string;
  request: Record<string, unknown>;
  redacted_payload: Record<string, unknown>;
  granted_fields: string[] | null;
  redacted_fields: string[] | null;
  reason: string;
  chain_index: number;
  previous_hash: string;
  chain_hash: string;
  chain_hash_algorithm: "sha256";
  created_at: string;
}

export interface AuditAppendEventInput {
  actorId: string;
  partitionId: string;
  causationId: string;
  correlationId: string;
  action: PolicyAction;
  resourceType: string;
  resourceId: string;
  decision: PolicyDecision;
  request: Record<string, unknown>;
  redactedPayload: Record<string, unknown>;
  reason?: string;
  createdAt?: string;
}

export interface AuditChainViolation {
  index: number;
  field: "index" | "previous_hash" | "chain_hash";
  expected: string;
  actual: string;
}

const PRIVACY_DISTRIBUTED_FIELDS: ReadonlyArray<string> = [
  "access_token",
  "refresh_token",
  "api_key",
  "client_secret",
  "bearer_token",
  "private_key",
  "encryption_nonce",
  "ciphertext",
  "raw_headers",
  "identity_map",
  "redaction_receipts",
  "confidential_comment",
  "legal_hold",
  "reviewer_notes",
  "risk_notes",
  "sensitive_reason",
];

const AUDIT_HASH_SEED = "zeta-03-audit-chain-v1";
const HASH_ALGORITHM: "sha256" = "sha256";

const actionPriority: Record<PolicyAction, number> = {
  "partition.read": 0,
  "partition.write": 1,
  "partition.grant": 2,
  "work.read": 3,
  "work.write": 4,
  "work.review": 5,
  "note.read": 6,
  "note.write": 7,
  "artifact.read": 8,
  "artifact.write": 9,
  "decision.read": 10,
  "decision.write": 11,
  "search.read": 12,
  "search.index": 13,
  "automation.run": 14,
  "audit.read": 15,
  "audit.write": 16,
  "export.read": 17,
  "export.write": 18,
  "portal.view": 19,
  "portal.contribute": 20,
  "portal.edit": 21,
};

const rolePriority: Record<PartitionRole, number> = {
  owner: 100,
  admin: 90,
  editor: 75,
  viewer: 50,
  auditor: 40,
};

const ROLE_ACTION_MATRIX: Record<PartitionRole, ReadonlySet<PolicyAction>> = {
  owner: new Set([
    "partition.read",
    "partition.write",
    "partition.grant",
    "work.read",
    "work.write",
    "work.review",
    "note.read",
    "note.write",
    "artifact.read",
    "artifact.write",
    "decision.read",
    "decision.write",
    "search.read",
    "search.index",
    "automation.run",
    "audit.read",
    "audit.write",
    "export.read",
    "export.write",
    "portal.view",
    "portal.contribute",
    "portal.edit",
  ]),
  admin: new Set([
    "partition.read",
    "partition.write",
    "work.read",
    "work.write",
    "work.review",
    "note.read",
    "note.write",
    "artifact.read",
    "artifact.write",
    "decision.read",
    "decision.write",
    "search.read",
    "search.index",
    "automation.run",
    "audit.read",
    "audit.write",
    "export.read",
    "portal.view",
    "portal.contribute",
  ]),
  editor: new Set([
    "work.read",
    "work.write",
    "work.review",
    "note.read",
    "note.write",
    "artifact.read",
    "artifact.write",
    "search.read",
    "search.index",
    "automation.run",
    "export.read",
    "portal.view",
    "portal.contribute",
  ]),
  viewer: new Set([
    "partition.read",
    "work.read",
    "note.read",
    "artifact.read",
    "decision.read",
    "search.read",
    "export.read",
    "audit.read",
    "portal.view",
  ]),
  auditor: new Set([
    "partition.read",
    "work.read",
    "artifact.read",
    "decision.read",
    "search.read",
    "audit.read",
    "export.read",
    "portal.view",
  ]),
};

const PRINCIPAL_TYPE_ACTION_MATRIX: Record<PolicyPrincipalType, ReadonlySet<PolicyAction>> = {
  owner: new Set([
    "partition.read",
    "partition.write",
    "partition.grant",
    "work.read",
    "work.write",
    "work.review",
    "note.read",
    "note.write",
    "artifact.read",
    "artifact.write",
    "decision.read",
    "decision.write",
    "search.read",
    "search.index",
    "automation.run",
    "audit.read",
    "audit.write",
    "export.read",
    "export.write",
    "portal.view",
    "portal.contribute",
    "portal.edit",
  ]),
  service: new Set([
    "work.read",
    "note.read",
    "search.index",
    "automation.run",
    "export.read",
  ]),
  agent: new Set([
    "work.read",
    "work.write",
    "note.read",
    "search.read",
    "search.index",
    "automation.run",
    "export.read",
  ]),
  collaborator: new Set([
    "partition.read",
    "work.read",
    "note.read",
    "artifact.read",
    "decision.read",
    "search.read",
    "export.read",
  ]),
};

const VISIBLE_FIELDS_BY_ROLE: Record<PartitionRole, Record<string, ReadonlySet<string>>> = {
  owner: {
    note: new Set([]),
    artifact: new Set([]),
    decision: new Set([]),
    export: new Set([]),
    audit: new Set([]),
    portal: new Set([]),
  },
  admin: {
    note: new Set(["confidential_comment"]),
    artifact: new Set(["ciphertext"]),
    decision: new Set([]),
    export: new Set([]),
    audit: new Set([]),
    portal: new Set([]),
  },
  editor: {
    note: new Set(["confidential_comment", "legal_hold"]),
    artifact: new Set(["ciphertext"]),
    decision: new Set(["risk_notes"]),
    export: new Set(["redaction_receipts"]),
    audit: new Set(["raw_headers"]),
    portal: new Set([]),
  },
  viewer: {
    note: new Set(["confidential_comment", "legal_hold"]),
    artifact: new Set(["ciphertext", "encryption_nonce"]),
    decision: new Set(["risk_notes"]),
    export: new Set(["identity_map"]),
    audit: new Set(["raw_headers"]),
    portal: new Set([]),
  },
  auditor: {
    note: new Set(["confidential_comment", "reviewer_notes"]),
    artifact: new Set(["ciphertext"]),
    decision: new Set(["sensitive_reason"]),
    export: new Set(["identity_map"]),
    audit: new Set([]),
    portal: new Set([]),
  },
};

const PORTAL_CAPABILITY_PRIORITY: Record<PortalCapability, number> = {
  viewer: 10,
  contributor: 20,
  editor: 30,
};

const BASE_CAPABILITY_BY_ROLE: Record<PartitionRole, PortalCapability> = {
  owner: "editor",
  admin: "editor",
  editor: "contributor",
  viewer: "viewer",
  auditor: "viewer",
};

const PORTAL_RESOURCE_ACTION_MATRIX: Record<PortalResource, Record<PortalCapability, PolicyAction>> = {
  dashboard: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  people: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  organizations: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  engagements: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  projects: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  tasks: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  commitments: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  decisions: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  meetings: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  notes: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  artifacts: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
  search: {
    viewer: "portal.view",
    contributor: "portal.contribute",
    editor: "portal.edit",
  },
};

const PORTAL_UPLOAD_QUARANTINE_SIZE_BYTES = 16 * 1024 * 1024;
const PORTAL_COMMENT_MAX_BYTES = 2048;

const PORTAL_TASK_TRANSITION_POLICY: Record<PortalTaskTransition, { requiredCapability: PortalCapability; from: PortalTaskState[]; to: PortalTaskState }> = {
  acknowledge: {
    requiredCapability: "viewer",
    from: ["open", "in_progress", "waiting", "blocked", "reopened", "completed"],
    to: "reopened",
  },
  start: {
    requiredCapability: "contributor",
    from: ["open", "waiting", "reopened"],
    to: "in_progress",
  },
  wait: {
    requiredCapability: "contributor",
    from: ["open", "in_progress", "reopened"],
    to: "waiting",
  },
  block: {
    requiredCapability: "editor",
    from: ["open", "in_progress", "waiting", "reopened", "completed"],
    to: "blocked",
  },
  complete: {
    requiredCapability: "editor",
    from: ["in_progress", "waiting", "reopened"],
    to: "completed",
  },
  reopen: {
    requiredCapability: "editor",
    from: ["completed", "blocked"],
    to: "reopened",
  },
};

const LAMBDA_03_REVOCATION_SURFACES: readonly PortalRuntimeSurface[] = [
  "session",
  "cache",
  "search",
  "jobs",
  "downloads",
];

function portalCapabilityFromAction(action: PolicyAction | "*"): PortalCapability | null {
  switch (action) {
    case "portal.view":
      return "viewer";
    case "portal.contribute":
      return "contributor";
    case "portal.edit":
      return "editor";
    default:
      return null;
  }
}

function maxPortalCapability(
  left: PortalCapability,
  right: PortalCapability,
): PortalCapability {
  return PORTAL_CAPABILITY_PRIORITY[left] >= PORTAL_CAPABILITY_PRIORITY[right] ? left : right;
}

function isCapabilityAtLeast(candidate: PortalCapability, minimum: PortalCapability): boolean {
  return PORTAL_CAPABILITY_PRIORITY[candidate] >= PORTAL_CAPABILITY_PRIORITY[minimum];
}

function getRowOwnerOnly<T extends { [key: string]: unknown }>(
  row: T,
  ownerOnly: ((row: T) => boolean) | undefined,
): boolean {
  if (ownerOnly) {
    return ownerOnly(row);
  }
  return row.ownerOnly === true;
}

function getRowId<T extends { [key: string]: unknown }>(row: T): string | undefined {
  const candidate = row.id;
  return typeof candidate === "string" ? candidate : undefined;
}

function portalResourceAction(resource: PortalResource, capability: PortalCapability): PolicyAction {
  return PORTAL_RESOURCE_ACTION_MATRIX[resource][capability];
}

function portalGrantMatchesRequest(
  grant: CapabilityGrant,
  principalId: string,
  partitionId: string,
  resource: PortalResource,
  nowIso: string,
): PortalCapability | null {
  if (
    grant.principalId !== principalId ||
    grant.partitionId !== partitionId ||
    isExpired(grant.expiresAt, nowIso)
  ) {
    return null;
  }
  if (
    !(
      matchesPattern(grant.resource, "*") ||
      matchesPattern(grant.resource, `portal.${resource}`) ||
      matchesPattern(grant.resource, "portal")
    )
  ) {
    return null;
  }
  if (grant.action === "*") {
    return "editor";
  }
  return portalCapabilityFromAction(grant.action as PolicyAction);
}

function resolvePortalCapability(
  principalId: string,
  partitionId: string,
  memberships: PartitionMembership[],
  grants: CapabilityGrant[],
  resource: PortalResource,
  now: string,
): PortalCapability {
  const role = highestMembership(memberships, principalId, partitionId, now);
  const base = role === null ? "viewer" : BASE_CAPABILITY_BY_ROLE[role];
  const grantCapabilities = grants
    .map((grant) => portalGrantMatchesRequest(grant, principalId, partitionId, resource, now))
    .filter((value): value is PortalCapability => value !== null);
  return grantCapabilities.reduce((current, next) => maxPortalCapability(current, next), base);
}

export function resolvePortalCapabilityFromGrants(input: {
  principalId: string;
  partitionId: string;
  memberships: PartitionMembership[];
  grants: CapabilityGrant[];
  resource: PortalResource;
  now?: string;
}): PortalCapability {
  return resolvePortalCapability(
    input.principalId,
    input.partitionId,
    input.memberships,
    input.grants,
    input.resource,
    nowIsoFrom(input.now),
  );
}

function parseTimestamp(value: string): number {
  return Date.parse(value);
}

function nowIsoFrom(input?: string): string {
  return input || DEFAULT_NOW;
}

function isExpired(timestamp: string | null, nowIso: string): boolean {
  if (!timestamp) {
    return false;
  }
  return parseTimestamp(timestamp) <= parseTimestamp(nowIso);
}

function isMembershipActive(membership: PartitionMembership, nowIso: string): boolean {
  const now = parseTimestamp(nowIso);
  if (parseTimestamp(membership.startAt) > now) {
    return false;
  }
  if (membership.endAt && parseTimestamp(membership.endAt) <= now) {
    return false;
  }
  return true;
}

function matchesPattern(pattern: string, candidate: string): boolean {
  if (pattern === "*") {
    return true;
  }
  if (pattern.endsWith(".*")) {
    const prefix = pattern.slice(0, -2);
    return candidate === pattern || candidate.startsWith(prefix + ".");
  }
  return pattern === candidate;
}

function activeMemberships(
  memberships: PartitionMembership[],
  principalId: string,
  partitionId: string,
  now: string,
): PartitionMembership[] {
  return memberships
    .filter((membership) =>
      membership.principalId === principalId &&
      membership.partitionId === partitionId &&
      isMembershipActive(membership, now),
    )
    .sort((left, right) => rolePriority[right.role] - rolePriority[left.role]);
}

function highestMembership(
  memberships: PartitionMembership[],
  principalId: string,
  partitionId: string,
  now: string,
): PartitionRole | null {
  const active = activeMemberships(memberships, principalId, partitionId, now);
  if (active.length === 0) {
    return null;
  }
  return active[0].role;
}

function matchingGrant(
  grants: CapabilityGrant[],
  principalId: string,
  partitionId: string,
  action: PolicyAction,
  resource: string,
  nowIso: string,
): CapabilityGrant | undefined {
  return grants
    .filter(
      (grant) =>
        grant.principalId === principalId &&
        grant.partitionId === partitionId &&
        matchesPattern(grant.action, action) &&
        (matchesPattern(grant.resource, resource) || matchesPattern(grant.resource, "*")) &&
        !isExpired(grant.expiresAt, nowIso),
    )
    .sort((left, right) => parseTimestamp(right.issuedAt) - parseTimestamp(left.issuedAt))[0];
}

function redactFields(resource: string, role: PartitionRole, requested: string[] | undefined): {
  grantedFields: string[] | null;
  redactedFields: string[] | null;
} {
  if (!requested || requested.length === 0) {
    return { grantedFields: null, redactedFields: null };
  }
  const hidden = VISIBLE_FIELDS_BY_ROLE[role][resource] || new Set<string>();
  const granted = requested.filter((field) => !hidden.has(field));
  const redacted = requested.filter((field) => hidden.has(field));
  return {
    grantedFields: granted,
    redactedFields: redacted,
  };
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((entry) => stableStringify(entry)).join(",")}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
    left.localeCompare(right),
  );
  return `{${entries.map(([key, value]) => `${JSON.stringify(key)}:${stableStringify(value)}`).join(",")}}`;
}

function detectPrivateFieldLeakageValue(value: unknown, pathPrefix: string = ""): PolicyLeakageFinding[] {
  if (value === null || typeof value !== "object") {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((entry, index) =>
      detectPrivateFieldLeakageValue(entry, `${pathPrefix}[${index}]`),
    );
  }

  const findings: PolicyLeakageFinding[] = [];
  for (const [field, fieldValue] of Object.entries(value as Record<string, unknown>)) {
    const fieldPath = pathPrefix ? `${pathPrefix}.${field}` : field;
    const lowered = field.toLowerCase();
    if (PRIVACY_DISTRIBUTED_FIELDS.includes(lowered) || lowered.includes("token")) {
      findings.push({
        path: fieldPath,
        field,
        reason: "private field surfaced in generated artifact",
      });
    }
    findings.push(...detectPrivateFieldLeakageValue(fieldValue, fieldPath));
  }
  return findings;
}

function normalizedPayloadCopy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function stripPrivateKeys(value: unknown, sensitiveFields: readonly string[]): unknown {
  const denylist = new Set(sensitiveFields.map((entry) => entry.toLowerCase()));
  if (value === null || typeof value !== "object") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((entry) => stripPrivateKeys(entry, sensitiveFields));
  }

  const stripped: Record<string, unknown> = {};
  for (const [field, fieldValue] of Object.entries(value as Record<string, unknown>)) {
    if (denylist.has(field.toLowerCase())) {
      continue;
    }
    stripped[field] = stripPrivateKeys(fieldValue, sensitiveFields);
  }
  return stripped;
}

function visibleFieldsForRoleAndResource(resource: string, role: PartitionRole): Set<string> {
  return new Set(VISIBLE_FIELDS_BY_ROLE[role][resource] || []);
}

function getPayloadValue(source: Record<string, unknown>, path: string): unknown {
  const parts = path.split(".");
  let value: unknown = source;
  for (const part of parts) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      return undefined;
    }
    const next = (value as Record<string, unknown>)[part];
    if (typeof next === "undefined") {
      return undefined;
    }
    value = next;
  }
  return value;
}

function setPayloadValue(target: Record<string, unknown>, path: string, value: unknown): void {
  const parts = path.split(".");
  let cursor: Record<string, unknown> = target;

  for (let index = 0; index < parts.length; index += 1) {
    const key = parts[index];
    const last = index === parts.length - 1;

    if (last) {
      cursor[key] = value;
      return;
    }

    if (typeof cursor[key] !== "object" || cursor[key] === null || Array.isArray(cursor[key])) {
      cursor[key] = {};
    }
    cursor = cursor[key] as Record<string, unknown>;
  }
}

function computeAuditEventHash(payload: unknown, previousHash: string): string {
  return createHash(HASH_ALGORITHM).update(`${previousHash}:${stableStringify(payload)}`).digest("hex");
}

function buildPortalRuntimeInvalidation(
  surface: PortalRuntimeSurface,
  partitionId: string,
  principalId: string,
  resource: string,
): PortalRuntimeInvalidation {
  const key = `${surface}:partition:${partitionId}:principal:${principalId}:resource:${resource}`;
  const reason = `${surface} cache invalidated due to grant lifecycle change`;
  return { surface, key, reason };
}

function buildPortalRuntimeInvalidations(
  partitionId: string,
  principalId: string,
  resource: string,
): readonly PortalRuntimeInvalidation[] {
  return LAMBDA_03_REVOCATION_SURFACES.map((surface) =>
    buildPortalRuntimeInvalidation(surface, partitionId, principalId, resource),
  );
}

function grantLifecycleStatus(
  grant: CapabilityGrant,
  now: string,
): "revoked" | "expired" {
  if (isExpired(grant.expiresAt, now)) {
    return "expired";
  }
  return "revoked";
}

export function buildPortalOwnerProjection<T extends { partitionId: string; [key: string]: unknown }>(
  input: PortalOwnerPreviewInput<T>,
): PortalProjectionEnvelope<T> {
  const now = nowIsoFrom(input.now);
  const previewPrincipalType = input.previewPrincipalType ?? "collaborator";
  const collaboratorProjection = projectPortalResource({
    principalId: input.previewPrincipalId,
    principalType: previewPrincipalType,
    partitionId: input.partitionId,
    resource: input.resource,
    memberships: input.memberships,
    grants: input.grants,
    now,
    requestedCapability: input.requestedCapability,
    rows: input.rows,
    navigation: input.navigation,
    ownerOnly: input.ownerOnly,
    explicitlySharedRowIds: input.explicitlySharedRowIds,
  });

  return {
    ...collaboratorProjection,
    principalId: input.principalId,
    principalType: input.principalType,
  };
}

export function buildPortalGrantRevocationReceipt(
  input: PortalGrantRevocationInput,
): PortalGrantRevocationReceipt {
  const now = nowIsoFrom(input.now);
  const status = input.reason || grantLifecycleStatus(input.grant, now);
  const requestedBy = input.requestedBy ?? input.grant.issuedBy;
  return {
    receiptId: input.requestId ?? randomUUID(),
    status,
    principalId: input.grant.principalId,
    principalType: input.principalType,
    partitionId: input.partitionId,
    principalGrantee: input.grant.principalId,
    grantId: input.grant.id,
    resource: input.grant.resource,
    action: input.grant.action,
    requestedBy,
    createdAt: now,
    reason: status === "expired" ? "grant expired" : "grant revoked",
    invalidations: buildPortalRuntimeInvalidations(
      input.partitionId,
      input.grant.principalId,
      input.grant.resource,
    ),
  };
}

export function buildPortalGrantProposal(input: PortalGrantProposalInput): PortalGrantProposalReceipt {
  const now = nowIsoFrom(input.now);
  const proposalId = input.proposalId ?? randomUUID();
  const resolvedCapability = resolvePortalCapability(
    input.principalId,
    input.partitionId,
    input.memberships,
    input.grants,
    input.resource,
    now,
  );
  const requiredAction = portalResourceAction(input.resource, input.requestedCapability);
  const decision = evaluatePolicyDecision({
    principalId: input.principalId,
    partitionId: input.partitionId,
    principalType: input.principalType,
    action: requiredAction,
    resource: `portal.${input.resource}`,
    memberships: input.memberships,
    grants: input.grants,
    now,
    fields: [],
  });
  const allowed = decision.allowed && isCapabilityAtLeast(resolvedCapability, input.requestedCapability);
  const finalDecision = {
    ...decision,
    allowed,
    reasonCode: allowed ? "ALLOW_PORTAL_GRANT_PREVIEW" : decision.reasonCode,
    reason: allowed ? "Portal grant proposal preview is authorized." : decision.reason,
  };

  return {
    proposalId,
    status: "preview",
    principalId: input.principalId,
    principalType: input.principalType,
    requestedBy: input.requestedBy,
    partitionId: input.partitionId,
    resource: input.resource,
    requestedCapability: input.requestedCapability,
    resolvedCapability,
    allowed,
    invitationDeliveryEnabled: false,
    reasonCode: finalDecision.reasonCode,
    reason: finalDecision.reason,
    policyVersion: finalDecision.policyVersion,
    createdAt: now,
  };
}

export function projectPortalResource<T extends { partitionId: string; [key: string]: unknown }>(
  input: PortalProjectionInput<T>,
): PortalProjectionEnvelope<T> {
  const now = nowIsoFrom(input.now);
  const resolvedCapability = resolvePortalCapability(
    input.principalId,
    input.partitionId,
    input.memberships,
    input.grants,
    input.resource,
    now,
  );
  const requiredAction = portalResourceAction(input.resource, input.requestedCapability);
  const decision = evaluatePolicyDecision({
    principalId: input.principalId,
    partitionId: input.partitionId,
    principalType: input.principalType,
    action: requiredAction,
    resource: `portal.${input.resource}`,
    memberships: input.memberships,
    grants: input.grants,
    now,
    fields: [],
  });
  const granted = decision.allowed && isCapabilityAtLeast(resolvedCapability, input.requestedCapability);

  if (!granted) {
    return {
      principalId: input.principalId,
      principalType: input.principalType,
      partitionId: input.partitionId,
      resource: input.resource,
      requestedCapability: input.requestedCapability,
      resolvedCapability,
      granted: false,
      rows: [],
      counts: {
        visible: 0,
        droppedOwnerOnly: 0,
      },
      links: [],
      errors: [{ code: "DENY_PORTAL_ACCESS", message: "portal projection unavailable" }],
    };
  }

  const samePartition = input.rows.filter((row) => row.partitionId === input.partitionId);
  const sharedArtifactIds = input.explicitlySharedRowIds ?? [];
  const visible = samePartition.filter((row) => {
    const isSharedArtifact = sharedArtifactIds.includes(getRowId(row) || "");
    const isOwnerOnly = getRowOwnerOnly(row, input.ownerOnly);
    return !isOwnerOnly || isCapabilityAtLeast(resolvedCapability, "editor") || isSharedArtifact;
  });
  const droppedOwnerOnly = samePartition.length - visible.length;
  const links = input.navigation
    .filter((link) => isCapabilityAtLeast(resolvedCapability, link.minimumCapability))
    .map((link) => ({
      ...link,
      href: link.href,
      partitionId: input.partitionId,
    }));

  return {
    principalId: input.principalId,
    principalType: input.principalType,
    partitionId: input.partitionId,
    resource: input.resource,
    requestedCapability: input.requestedCapability,
    resolvedCapability,
    granted: true,
    rows: visible,
    counts: {
      visible: visible.length,
      droppedOwnerOnly,
    },
    links,
    errors: [],
  };
}

function evaluatePortalMutationEligibility(
  input: PortalMutationInput,
  resource: PortalResource,
  requestedCapability: PortalCapability,
): PortalDecisionForMutation {
  const now = nowIsoFrom(input.now);
  const resolvedCapability = resolvePortalCapability(
    input.principalId,
    input.partitionId,
    input.memberships,
    input.grants,
    resource,
    now,
  );
  const requiredAction = portalResourceAction(resource, requestedCapability);
  const decision = evaluatePolicyDecision({
    principalId: input.principalId,
    partitionId: input.partitionId,
    principalType: input.principalType,
    action: requiredAction,
    resource: `portal.${input.resource}`,
    memberships: input.memberships,
    grants: input.grants,
    now,
    fields: [],
  });
  const allowed = decision.allowed && isCapabilityAtLeast(resolvedCapability, requestedCapability);
  const reason = allowed ? `Portal mutation ${input.kind} authorized.` : decision.reason;
  return {
    now,
    resolvedCapability,
    requiredCapability: requestedCapability,
    allowed,
    decision: {
      ...decision,
      allowed,
      reason,
      reasonCode: allowed ? `ALLOW_PORTAL_${input.kind.toUpperCase().replace(".", "_")}` : decision.reasonCode,
    },
  };
}

export function buildPortalComment(input: PortalCommentInput): PortalMutationReceipt {
  const requestedCapability: PortalCapability = input.requestedCapability ?? "contributor";
  const evaluated = evaluatePortalMutationEligibility(input, input.resource, requestedCapability);
  const mutationId = input.requestId ?? randomUUID();
  const baseReceipt: PortalMutationReceipt = {
    mutationId,
    kind: "comment",
    status: evaluated.allowed ? "allowed" : "denied",
    principalId: input.principalId,
    principalType: input.principalType,
    partitionId: input.partitionId,
    resource: input.resource,
    targetId: input.targetId,
    requestedCapability,
    resolvedCapability: evaluated.resolvedCapability,
    allowed: evaluated.allowed,
    reasonCode: evaluated.decision.reasonCode,
    reason: evaluated.decision.reason,
    policyVersion: evaluated.decision.policyVersion,
    createdAt: evaluated.now,
  };

  if (input.principalType === "collaborator" && evaluated.allowed && input.body.trim().length > 0) {
    baseReceipt.auditEvent = appendPolicyAuditEvent([], {
      actorId: input.principalId,
      partitionId: input.partitionId,
      causationId: mutationId,
      correlationId: input.requestId ?? mutationId,
      action: "portal.contribute",
      resourceType: "portal.comment",
      resourceId: input.targetId,
      decision: evaluated.decision,
      request: {
        kind: "comment",
        targetResource: input.resource,
        commentLength: input.body.length,
      },
      redactedPayload: {
        kind: "comment",
        targetResource: input.resource,
        targetId: input.targetId,
      },
    });
  }

  return baseReceipt;
}

export function buildPortalAcknowledgement(input: PortalAcknowledgementInput): PortalMutationReceipt {
  const requestedCapability: PortalCapability = input.requestedCapability ?? "viewer";
  const evaluated = evaluatePortalMutationEligibility(input, input.resource, requestedCapability);
  const mutationId = input.requestId ?? randomUUID();
  const baseReceipt: PortalMutationReceipt = {
    mutationId,
    kind: "acknowledgement",
    status: evaluated.allowed ? "allowed" : "denied",
    principalId: input.principalId,
    principalType: input.principalType,
    partitionId: input.partitionId,
    resource: input.resource,
    targetId: input.targetId,
    requestedCapability,
    resolvedCapability: evaluated.resolvedCapability,
    allowed: evaluated.allowed,
    reasonCode: evaluated.decision.reasonCode,
    reason: evaluated.decision.reason,
    policyVersion: evaluated.decision.policyVersion,
    createdAt: evaluated.now,
  };

  if (input.principalType === "collaborator" && evaluated.allowed) {
    baseReceipt.auditEvent = appendPolicyAuditEvent([], {
      actorId: input.principalId,
      partitionId: input.partitionId,
      causationId: mutationId,
      correlationId: input.requestId ?? mutationId,
      action: "portal.view",
      resourceType: "portal.acknowledgement",
      resourceId: input.targetId,
      decision: evaluated.decision,
      request: {
        kind: "acknowledgement",
        targetResource: input.resource,
        acknowledged: input.acknowledged,
      },
      redactedPayload: {
        kind: "acknowledgement",
        targetResource: input.resource,
        targetId: input.targetId,
        acknowledged: input.acknowledged,
      },
    });
  }

  return baseReceipt;
}

export function buildPortalUpload(input: PortalUploadInput): PortalUploadMutationReceipt {
  const requestedCapability: PortalCapability = input.requestedCapability ?? "contributor";
  const evaluated = evaluatePortalMutationEligibility(input, input.resource, requestedCapability);
  const mutationId = input.requestId ?? randomUUID();
  const quarantineReasons: string[] = [];

  if (input.sizeBytes <= 0) {
    quarantineReasons.push("invalid-size");
  }
  if (input.sizeBytes > PORTAL_UPLOAD_QUARANTINE_SIZE_BYTES) {
    quarantineReasons.push("size-limit");
  }
  if (!input.mimeType) {
    quarantineReasons.push("missing-mime");
  }

  const quarantined = evaluated.allowed && quarantineReasons.length > 0;
  const status: PortalMutationReceipt["status"] = !evaluated.allowed ? "denied" : quarantined ? "quarantined" : "allowed";
  const baseReceipt: PortalUploadMutationReceipt = {
    mutationId,
    kind: "upload",
    status,
    principalId: input.principalId,
    principalType: input.principalType,
    partitionId: input.partitionId,
    resource: input.resource,
    targetId: input.targetId,
    requestedCapability,
    resolvedCapability: evaluated.resolvedCapability,
    allowed: evaluated.allowed,
    reasonCode: evaluated.decision.reasonCode,
    reason: evaluated.decision.reason,
    policyVersion: evaluated.decision.policyVersion,
    createdAt: evaluated.now,
    filename: input.filename,
    mimeType: input.mimeType,
    sizeBytes: input.sizeBytes,
    quarantined,
    quarantineReasons,
  };

  if (input.principalType === "collaborator" && evaluated.allowed) {
    baseReceipt.auditEvent = appendPolicyAuditEvent([], {
      actorId: input.principalId,
      partitionId: input.partitionId,
      causationId: mutationId,
      correlationId: input.requestId ?? mutationId,
      action: quarantined ? "portal.contribute" : "portal.edit",
      resourceType: "portal.upload",
      resourceId: input.targetId,
      decision: evaluated.decision,
      request: {
        kind: "upload",
        targetResource: input.resource,
        filename: input.filename,
        mimeType: input.mimeType,
        sizeBytes: input.sizeBytes,
      },
      redactedPayload: {
        kind: "upload",
        targetResource: input.resource,
        filename: input.filename,
        mimeType: input.mimeType,
        sizeBytes: input.sizeBytes,
        quarantined,
      },
    });
  }

  return baseReceipt;
}

export function buildPortalTaskTransition(input: PortalTaskTransitionInput): PortalTaskTransitionReceipt {
  const transitionRule = PORTAL_TASK_TRANSITION_POLICY[input.transition];
  const requestedCapability: PortalCapability = input.requestedCapability ?? transitionRule.requiredCapability;
  const resolved = evaluatePortalMutationEligibility(input, input.resource, requestedCapability);
  const mutationId = input.requestId ?? randomUUID();
  const stateBlocked = input.currentTaskState && transitionRule.from.length > 0
    && !transitionRule.from.includes(input.currentTaskState);
  const allowedByState = !stateBlocked;
  const allowed = resolved.allowed && isCapabilityAtLeast(resolved.resolvedCapability, transitionRule.requiredCapability)
    && allowedByState;
  const reason = allowed ? `Task transition ${input.transition} allowed.` : resolved.decision.reason;
  const reasonCode = allowed
    ? `ALLOW_TASK_TRANSITION_${input.transition.toUpperCase()}`
    : resolved.decision.reasonCode;

  const receipt: PortalTaskTransitionReceipt = {
    mutationId,
    kind: "task.transition",
    status: allowed ? "allowed" : "denied",
    principalId: input.principalId,
    principalType: input.principalType,
    partitionId: input.partitionId,
    resource: input.resource,
    targetId: input.targetId,
    requestedCapability,
    resolvedCapability: resolved.resolvedCapability,
    allowed,
    reasonCode,
    reason,
    policyVersion: resolved.decision.policyVersion,
    createdAt: resolved.now,
    transition: input.transition,
    currentTaskState: input.currentTaskState,
    allowedTransitions: Object.entries(PORTAL_TASK_TRANSITION_POLICY)
      .filter(([_, transition]) => input.currentTaskState ? transition.from.includes(input.currentTaskState) : true)
      .map(([transition]) => transition as PortalTaskTransition),
  };

  if (input.principalType === "collaborator" && allowed) {
    receipt.auditEvent = appendPolicyAuditEvent([], {
      actorId: input.principalId,
      partitionId: input.partitionId,
      causationId: mutationId,
      correlationId: input.requestId ?? mutationId,
      action: "portal.edit",
      resourceType: "portal.task.transition",
      resourceId: input.targetId,
      decision: {
        ...resolved.decision,
        reasonCode,
        reason,
        allowed,
      },
      request: {
        kind: "task.transition",
        targetResource: "tasks",
        transition: input.transition,
        currentTaskState: input.currentTaskState,
        nextTaskState: transitionRule.to,
      },
      redactedPayload: {
        kind: "task.transition",
        transition: input.transition,
        currentTaskState: input.currentTaskState,
        nextTaskState: transitionRule.to,
      },
    });
  }

  if (!allowed && input.currentTaskState) {
    receipt.status = "denied";
    receipt.reason = `Transition ${input.transition} is not valid from ${input.currentTaskState}.`;
    receipt.reasonCode = "DENY_TASK_TRANSITION_STATE";
  }

  return receipt;
}

type PortalDecisionForMutation = {
  now: string;
  resolvedCapability: PortalCapability;
  requiredCapability: PortalCapability;
  allowed: boolean;
  decision: PolicyDecision;
};

export function evaluatePolicyDecision(input: PolicyRequest): PolicyDecision {
  const now = nowIsoFrom(input.now);
  const grant = matchingGrant(input.grants, input.principalId, input.partitionId, input.action, input.resource, now);

  if (grant && grant.effect === "deny") {
    return {
      allowed: false,
      reasonCode: "DENY_GRANT",
      reason: "A non-transitive explicit deny grant matched the request.",
      policyVersion: POLICY_VERSION,
      principalId: input.principalId,
      partitionId: input.partitionId,
      action: input.action,
      resource: input.resource,
      grantedFields: null,
      redactedFields: null,
      resolvedRole: "owner",
    };
  }
  if (grant && grant.effect === "allow") {
    const redacted = redactFields(input.resource, "owner", input.fields);
    return {
      allowed: true,
      reasonCode: "ALLOW_GRANT",
      reason: `Explicit grant ${grant.id} allowed action ${input.action} on ${input.resource}.`,
      policyVersion: POLICY_VERSION,
      principalId: input.principalId,
      partitionId: input.partitionId,
      action: input.action,
      resource: input.resource,
      grantedFields: redacted.grantedFields,
      redactedFields: redacted.redactedFields,
      resolvedRole: "owner",
    };
  }

  const resolvedRole = input.roleOverride ?? highestMembership(input.memberships, input.principalId, input.partitionId, now);
  if (!resolvedRole) {
    const hasOwnerByType = input.principalType === "owner";
    if (!hasOwnerByType) {
      return {
        allowed: false,
        reasonCode: "DENY_NO_MEMBERSHIP",
        reason: "No active partition membership and no explicit allow grant.",
        policyVersion: POLICY_VERSION,
        principalId: input.principalId,
        partitionId: input.partitionId,
        action: input.action,
        resource: input.resource,
        grantedFields: null,
        redactedFields: null,
        resolvedRole: hasOwnerByType ? "owner" : "viewer",
      };
    }
  }

  const actorRole: PartitionRole = resolvedRole ?? "viewer";
  const principalActions = PRINCIPAL_TYPE_ACTION_MATRIX[input.principalType];
  const roleActions = ROLE_ACTION_MATRIX[actorRole];
  const allowedByRole = principalActions.has(input.action) || roleActions.has(input.action);

  if (!allowedByRole) {
    return {
      allowed: false,
      reasonCode: "DENY_ROLE_MATRIX",
      reason: `Role ${actorRole} does not include action ${input.action}.`,
      policyVersion: POLICY_VERSION,
      principalId: input.principalId,
      partitionId: input.partitionId,
      action: input.action,
      resource: input.resource,
      grantedFields: null,
      redactedFields: null,
      resolvedRole: actorRole,
    };
  }

  const redacted = redactFields(input.resource, actorRole, input.fields);
  if (redacted.redactedFields?.length && redacted.grantedFields && redacted.grantedFields.length === 0) {
    return {
      allowed: false,
      reasonCode: "DENY_FIELD_VISIBILITY",
      reason: `Action ${input.action} was denied for ${input.resource}; requested fields were all redacted.`,
      policyVersion: POLICY_VERSION,
      principalId: input.principalId,
      partitionId: input.partitionId,
      action: input.action,
      resource: input.resource,
      grantedFields: redacted.grantedFields,
      redactedFields: redacted.redactedFields,
      resolvedRole: actorRole,
    };
  }

  const action = redacted.redactedFields && redacted.redactedFields.length > 0
    ? "ALLOW_FIELD_REDACTED"
    : "ALLOW_ROLE_MATRIX";
  const reason = redacted.redactedFields && redacted.redactedFields.length > 0
    ? `Read request allowed with redaction for resource ${input.resource}.`
    : `Role ${actorRole} allowed action ${input.action} on ${input.resource}.`;
  return {
    allowed: true,
    reasonCode: action,
    reason,
    policyVersion: POLICY_VERSION,
    principalId: input.principalId,
    partitionId: input.partitionId,
    action: input.action,
    resource: input.resource,
    grantedFields: redacted.grantedFields,
    redactedFields: redacted.redactedFields,
    resolvedRole: actorRole,
  };
}

export function redactPayloadForPolicy(input: PolicyRedactionInput): PolicyRedactionResult {
  const decision = evaluatePolicyDecision(input);
  const role = decision.resolvedRole;
  const hiddenFields = visibleFieldsForRoleAndResource(input.resource, role);
  const denied = !decision.allowed;
  const droppedFields: string[] = [];

  if (denied) {
    return {
      decision,
      redactedPayload: {},
      grantedFields: decision.grantedFields,
      redactedFields: decision.redactedFields,
      droppedFields: Object.keys(input.payload),
    };
  }

  const allowField = (fieldPath: string): boolean => {
    const head = fieldPath.split(".")[0];
    const lowered = fieldPath.toLowerCase();
    const hasSensitiveSegment = fieldPath.toLowerCase().split(".").some((segment) =>
      PRIVACY_DISTRIBUTED_FIELDS.includes(segment) || segment.includes("token"),
    );
    if (hiddenFields.has(head)) {
      droppedFields.push(head);
      return false;
    }
    if (hasSensitiveSegment) {
      droppedFields.push(fieldPath);
      return false;
    }
    if (PRIVACY_DISTRIBUTED_FIELDS.includes(head.toLowerCase()) || head.toLowerCase().includes("token")) {
      droppedFields.push(head);
      return false;
    }
    return true;
  };

  if (input.fields && input.fields.length > 0) {
    const projected: Record<string, unknown> = {};
    for (const field of input.fields) {
      if (!allowField(field)) {
        continue;
      }
      const value = getPayloadValue(input.payload, field);
      if (typeof value === "undefined") {
        continue;
      }
      setPayloadValue(projected, field, stripPrivateKeys(value, PRIVACY_DISTRIBUTED_FIELDS));
    }

    return {
      decision,
      redactedPayload: projected,
      grantedFields: decision.grantedFields,
      redactedFields: decision.redactedFields,
      droppedFields: Array.from(new Set(droppedFields)),
    };
  }

  const redacted = stripPrivateKeys(
    normalizedPayloadCopy(input.payload),
    PRIVACY_DISTRIBUTED_FIELDS,
  ) as Record<string, unknown>;
  for (const hiddenField of hiddenFields) {
    if (Object.prototype.hasOwnProperty.call(redacted, hiddenField)) {
      delete redacted[hiddenField];
      droppedFields.push(hiddenField);
    }
  }

  return {
    decision,
    redactedPayload: redacted,
    grantedFields: decision.grantedFields,
    redactedFields: decision.redactedFields,
    droppedFields: Array.from(new Set(droppedFields)),
  };
}

export function redactForSerialization(input: PolicyRedactionInput): string {
  const redaction = redactPayloadForPolicy(input);
  return JSON.stringify(redaction.redactedPayload);
}

export function sanitizeForLogging(input: PolicyRedactionInput): string {
  return redactForSerialization(input);
}

export function sanitizeForIndexing(input: PolicyRedactionInput): Record<string, unknown> {
  return redactPayloadForPolicy(input).redactedPayload;
}

export function sanitizeForExport(input: PolicyRedactionInput): Record<string, unknown> {
  return sanitizeForIndexing(input);
}

export function detectPrivateFieldLeakage(artifact: unknown): PolicyLeakageFinding[] {
  return detectPrivateFieldLeakageValue(artifact);
}

export function assertNoPrivateFieldLeakage(artifact: unknown): void {
  const findings = detectPrivateFieldLeakage(artifact);
  if (findings.length > 0) {
    throw new Error(`private field leakage detected: ${findings.map((finding) => finding.path).join(", ")}`);
  }
}

export function appendPolicyAuditEvent(ledger: AuditAppendEvent[], input: AuditAppendEventInput): AuditAppendEvent {
  const previous = ledger.at(-1);
  const previousHash = previous?.chain_hash ?? AUDIT_HASH_SEED;
  const chainIndex = (previous?.chain_index ?? -1) + 1;
  const createdAt = input.createdAt ?? new Date().toISOString();
  const core = {
    actor_id: input.actorId,
    partition_id: input.partitionId,
    causation_id: input.causationId,
    correlation_id: input.correlationId,
    action: input.action,
    resource_type: input.resourceType,
    resource_id: input.resourceId,
    decision_code: input.decision.reasonCode,
    decision_reason: input.decision.reason,
    policy_version: input.decision.policyVersion,
    request: input.request,
    redacted_payload: input.redactedPayload,
    granted_fields: input.decision.grantedFields ?? null,
    redacted_fields: input.decision.redactedFields ?? null,
    reason: input.reason ?? input.decision.reason,
    chain_index: chainIndex,
    previous_hash: previousHash,
    created_at: createdAt,
  };
  return {
    id: randomUUID(),
    ...core,
    chain_hash: computeAuditEventHash(core, previousHash),
    chain_hash_algorithm: HASH_ALGORITHM,
  };
}

export function verifyAuditChain(ledger: AuditAppendEvent[]): { ok: boolean; violations: AuditChainViolation[] } {
  const violations: AuditChainViolation[] = [];

  for (let index = 0; index < ledger.length; index += 1) {
    const event = ledger[index];
    const expectedIndex = index;
    if (event.chain_index !== expectedIndex) {
      violations.push({
        index,
        field: "index",
        expected: String(expectedIndex),
        actual: String(event.chain_index),
      });
    }

    const expectedPrevious = index === 0 ? AUDIT_HASH_SEED : ledger[index - 1].chain_hash;
    if (event.previous_hash !== expectedPrevious) {
      violations.push({
        index,
        field: "previous_hash",
        expected: expectedPrevious,
        actual: event.previous_hash,
      });
    }

    const expectedHash = computeAuditEventHash(
      {
        actor_id: event.actor_id,
        partition_id: event.partition_id,
        causation_id: event.causation_id,
        correlation_id: event.correlation_id,
        action: event.action,
        resource_type: event.resource_type,
        resource_id: event.resource_id,
        decision_code: event.decision_code,
        decision_reason: event.decision_reason,
        policy_version: event.policy_version,
        request: event.request,
        redacted_payload: event.redacted_payload,
        granted_fields: event.granted_fields,
        redacted_fields: event.redacted_fields,
        reason: event.reason,
        chain_index: event.chain_index,
        previous_hash: event.previous_hash,
        created_at: event.created_at,
      },
      expectedPrevious,
    );
    if (event.chain_hash !== expectedHash) {
      violations.push({
        index,
        field: "chain_hash",
        expected: expectedHash,
        actual: event.chain_hash,
      });
    }
  }

  return {
    ok: violations.length === 0,
    violations,
  };
}

const DEFAULT_ACTIONS: readonly PolicyAction[] = Object.keys(actionPriority).sort(
  (left, right) => actionPriority[left as PolicyAction] - actionPriority[right as PolicyAction],
) as readonly PolicyAction[];

export function buildPolicyDecisionMatrix(input: PolicyDecisionMatrixInput): PolicyMatrix {
  const now = nowIsoFrom(input.now);
  const actions = input.actions ? [...input.actions] : [...DEFAULT_ACTIONS];
  const rows: PolicyDecisionMatrixCell[] = [];

  for (const principal of input.principals) {
    for (const partitionId of input.partitions) {
      const memberships = activeMemberships(input.memberships, principal.principalId, partitionId, now);
      const roles = memberships.length > 0
        ? memberships.map((membership) => membership.role)
        : ["viewer"];

      const uniqueRoles = [...new Set(roles)];

      for (const role of uniqueRoles) {
        for (const action of actions) {
          const resource = action.split(".")[0];
          const decision = evaluatePolicyDecision({
            principalId: principal.principalId,
            partitionId,
            principalType: principal.principalType,
            action,
            resource,
            memberships: input.memberships,
            grants: input.grants,
            now,
            roleOverride: role,
          });
          rows.push({
            principalId: principal.principalId,
            partitionId,
            principalType: principal.principalType,
            role,
            action,
            resource,
            allowed: decision.allowed,
            reasonCode: decision.reasonCode,
            grantedFields: decision.grantedFields,
            redactedFields: decision.redactedFields,
          });
        }
      }
    }
  }

  rows.sort((left, right) => {
    if (left.principalId !== right.principalId) {
      return left.principalId.localeCompare(right.principalId);
    }
    if (left.partitionId !== right.partitionId) {
      return left.partitionId.localeCompare(right.partitionId);
    }
    if (left.role !== right.role) {
      return rolePriority[right.role] - rolePriority[left.role];
    }
    return actionPriority[left.action] - actionPriority[right.action];
  });

  return { rows };
}
