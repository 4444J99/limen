import { test } from "node:test";
import assert from "node:assert";
import {
  buildPortalAcknowledgement,
  buildPortalComment,
  buildPortalUpload,
  buildPortalTaskTransition,
  projectPortalResource,
} from "../src/index.ts";
import type {
  PortalAcknowledgementInput,
  PortalUploadInput,
  PartitionMembership,
  CapabilityGrant,
  PortalResource,
} from "../src/index.ts";

const baseNow = "2026-08-01T00:00:00.000Z";

function fixedMembership(principalId: string, role: string, partitionId = "partition-a"): PartitionMembership {
  return {
    principalId,
    partitionId,
    role: role as any,
    grantedBy: "owner-principal",
    grantedAt: "2026-01-01T00:00:00.000Z",
    startAt: "2026-01-01T00:00:00.000Z",
    endAt: null,
  };
}

function fixedPortalGrant(partial: Partial<CapabilityGrant>): CapabilityGrant {
  return {
    id: "grant-001",
    principalId: "alice",
    partitionId: "partition-a",
    resource: "portal.artifacts",
    action: "portal.contribute",
    effect: "allow",
    issuedBy: "owner-principal",
    issuedAt: "2026-01-02T00:00:00.000Z",
    expiresAt: null,
    ...partial,
  };
}

test("LAMBDA-02 explicitly-shared artifacts are visible even when owner-only", () => {
  type ArtifactRow = { id: string; partitionId: string; ownerOnly?: boolean; kind: string };
  const nav = [{ id: "artifacts", label: "Artifacts", href: "/portal/artifacts", minimumCapability: "viewer" }] as const;
  const rows: readonly ArtifactRow[] = [
    { id: "public-1", partitionId: "partition-a", kind: "summary" },
    { id: "shared-owner-only", partitionId: "partition-a", ownerOnly: true, kind: "sensitive" },
    { id: "owner-only", partitionId: "partition-a", ownerOnly: true, kind: "sensitive" },
    { id: "foreign", partitionId: "partition-b", kind: "summary" },
  ];

  const projection = projectPortalResource<ArtifactRow>({
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    resource: "artifacts",
    memberships: [fixedMembership("alice", "viewer")],
    grants: [],
    now: baseNow,
    requestedCapability: "viewer",
    rows,
    navigation: nav,
    explicitlySharedRowIds: ["shared-owner-only"],
  });

  assert.strictEqual(projection.granted, true);
  assert.strictEqual(projection.rows.length, 2);
  assert.strictEqual(projection.counts.visible, 2);
  assert.strictEqual(projection.counts.droppedOwnerOnly, 1);
});

test("LAMBDA-02 gates collaborator comments by requested capability", () => {
  const viewInput = {
    kind: "comment" as const,
    principalId: "alice",
    principalType: "collaborator" as const,
    partitionId: "partition-a",
    resource: "notes" as PortalResource,
    targetId: "note-001",
    memberships: [fixedMembership("alice", "viewer")],
    grants: [],
    now: baseNow,
    requestId: "comment-001",
    body: "a short note",
  };
  const denied = buildPortalComment(viewInput);

  assert.strictEqual(denied.allowed, false);
  assert.strictEqual(denied.status, "denied");
  assert.strictEqual(denied.auditEvent, undefined);

  const allowInput = {
    ...viewInput,
    memberships: [fixedMembership("alice", "editor")],
  };
  const allowed = buildPortalComment(allowInput);

  assert.strictEqual(allowed.allowed, true);
  assert.strictEqual(allowed.status, "allowed");
  assert.ok(allowed.auditEvent);
  assert.strictEqual(allowed.auditEvent?.resource_id, "note-001");
});

test("LAMBDA-02 supports acknowledgements as contributor-visible mutations", () => {
  const baseInput: PortalAcknowledgementInput = {
    kind: "acknowledgement",
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    resource: "notes" as PortalResource,
    targetId: "note-001",
    memberships: [fixedMembership("alice", "viewer")],
    grants: [fixedPortalGrant({ action: "portal.view" })],
    now: baseNow,
    requestId: "ack-001",
    acknowledged: true,
  };

  const acknowledged = buildPortalAcknowledgement(baseInput);
  assert.strictEqual(acknowledged.allowed, true);
  assert.strictEqual(acknowledged.status, "allowed");
  assert.ok(acknowledged.auditEvent);
  assert.strictEqual(acknowledged.auditEvent?.resource_type, "portal.acknowledgement");
});

test("LAMBDA-02 quarantines oversized uploads while still emitting audit", () => {
  const input: PortalUploadInput = {
    kind: "upload",
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    resource: "artifacts",
    targetId: "artifact-001",
    memberships: [fixedMembership("alice", "editor")],
    grants: [fixedPortalGrant({ action: "portal.edit" })],
    now: baseNow,
    requestId: "upload-001",
    filename: "invoice.pdf",
    mimeType: "application/pdf",
    sizeBytes: 64 * 1024 * 1024,
  };

  const upload = buildPortalUpload(input);
  assert.strictEqual(upload.allowed, true);
  assert.strictEqual(upload.status, "quarantined");
  assert.strictEqual(upload.quarantined, true);
  assert.ok(upload.quarantineReasons.includes("size-limit"));
  assert.ok(upload.auditEvent);
});

test("LAMBDA-02 validates task transition rules and allowed transitions", () => {
  const blocked = buildPortalTaskTransition({
    kind: "task.transition",
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    resource: "tasks",
    targetId: "task-001",
    transition: "complete",
    currentTaskState: "open",
    memberships: [fixedMembership("alice", "editor")],
    grants: [],
    now: baseNow,
    requestId: "transition-001",
  });

  assert.strictEqual(blocked.status, "denied");
  assert.strictEqual(blocked.reasonCode, "DENY_TASK_TRANSITION_STATE");

  const allowed = buildPortalTaskTransition({
    kind: "task.transition",
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    resource: "tasks",
    targetId: "task-001",
    transition: "complete",
    currentTaskState: "in_progress",
    memberships: [fixedMembership("alice", "editor")],
    grants: [fixedPortalGrant({ action: "portal.edit", resource: "portal.tasks" })],
    now: baseNow,
    requestId: "transition-002",
  });

  assert.strictEqual(allowed.status, "allowed");
  assert.strictEqual(allowed.transition, "complete");
  assert.ok(allowed.auditEvent);
  assert.strictEqual(allowed.auditEvent?.resource_type, "portal.task.transition");
  assert.ok(allowed.allowedTransitions?.includes("complete"));
  assert.strictEqual(allowed.allowedTransitions?.includes("start"), false);
});
