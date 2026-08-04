import { test } from "node:test";
import assert from "node:assert";
import {
  buildPortalGrantProposal,
  buildPortalGrantRevocationReceipt,
  buildPortalOwnerProjection,
  buildPortalComment,
  buildPortalAcknowledgement,
  buildPortalUpload,
  buildPortalTaskTransition,
  projectPortalResource,
} from "../src/index.ts";
import type {
  PartitionMembership,
  CapabilityGrant,
  PortalResource,
  PortalRuntimeSurface,
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

function fixedGrant(partial: Partial<CapabilityGrant>): CapabilityGrant {
  return {
    id: `grant-${partial.id || "base"}`,
    principalId: "collab-001",
    partitionId: "partition-a",
    resource: `portal.notes`,
    action: "portal.edit",
    effect: "allow",
    issuedBy: "owner-principal",
    issuedAt: "2026-01-02T00:00:00.000Z",
    expiresAt: null,
    ...partial,
  };
}

type NoteRow = { id: string; partitionId: string; ownerOnly?: boolean; body: string };

test("LAMBDA-03 lets owners preview collaborator projection without changing principal identity", () => {
  const rows: readonly NoteRow[] = [
    {
      id: "note-001",
      partitionId: "partition-a",
      ownerOnly: false,
      body: "shared",
    },
    {
      id: "note-002",
      partitionId: "partition-a",
      ownerOnly: true,
      body: "owner only",
    },
    {
      id: "note-003",
      partitionId: "partition-b",
      ownerOnly: false,
      body: "foreign",
    },
  ];
  const navigation = [
    {
      id: "notes",
      label: "Notes",
      href: "/portal/notes",
      minimumCapability: "viewer",
    },
    {
      id: "tasks",
      label: "Tasks",
      href: "/portal/tasks",
      minimumCapability: "contributor",
    },
  ] as const;

  const memberships = [fixedMembership("collab-001", "viewer")];
  const grants = [fixedGrant({ action: "portal.contribute" })];
  const withGrantCollaborator = projectPortalResource({
    principalId: "collab-001",
    principalType: "collaborator",
    partitionId: "partition-a",
    resource: "notes",
    memberships,
    grants,
    now: baseNow,
    requestedCapability: "viewer",
    rows,
    navigation,
    explicitlySharedRowIds: ["note-002"],
  });
  assert.strictEqual(withGrantCollaborator.granted, true);
  assert.strictEqual(withGrantCollaborator.rows.length, 2);

  const ownerPreview = buildPortalOwnerProjection({
    principalId: "owner-001",
    principalType: "owner",
    previewPrincipalId: "collab-001",
    partitionId: "partition-a",
    resource: "notes",
    memberships,
    grants,
    now: baseNow,
    requestedCapability: "viewer",
    rows,
    navigation,
    explicitlySharedRowIds: ["note-002"],
  });

  assert.strictEqual(ownerPreview.principalId, "owner-001");
  assert.strictEqual(ownerPreview.principalType, "owner");
  assert.strictEqual(ownerPreview.granted, withGrantCollaborator.granted);
  assert.deepStrictEqual(ownerPreview.rows, withGrantCollaborator.rows);
  assert.deepStrictEqual(ownerPreview.counts, withGrantCollaborator.counts);
  assert.deepStrictEqual(ownerPreview.links, withGrantCollaborator.links);
  assert.strictEqual(ownerPreview.principalType, "owner");
});

test("LAMBDA-03 denies collaboration grants after grant expiry and marks expiry receipts", () => {
  const memberships = [fixedMembership("collab-001", "editor")];
  const expiringGrant = fixedGrant({
    id: "grant-expiring",
    expiresAt: "2026-07-31T23:59:59.000Z",
  });

  const beforeExpiry = buildPortalGrantProposal({
    principalId: "collab-001",
    principalType: "collaborator",
    partitionId: "partition-a",
    requestedBy: "owner-principal",
    resource: "notes",
    requestedCapability: "editor",
    memberships,
    grants: [expiringGrant],
    now: "2026-07-31T12:00:00.000Z",
  });
  assert.strictEqual(beforeExpiry.allowed, true);

  const afterExpiry = buildPortalGrantProposal({
    principalId: "collab-001",
    principalType: "collaborator",
    partitionId: "partition-a",
    requestedBy: "owner-principal",
    resource: "notes",
    requestedCapability: "editor",
    memberships,
    grants: [expiringGrant],
    now: "2026-08-02T00:00:00.000Z",
  });
  assert.strictEqual(afterExpiry.allowed, false);

  const revocationReceipt = buildPortalGrantRevocationReceipt({
    principalId: "owner-001",
    principalType: "owner",
    partitionId: "partition-a",
    grant: expiringGrant,
    now: "2026-08-02T00:00:00.000Z",
    requestId: "revocation-001",
  });
  assert.strictEqual(revocationReceipt.status, "expired");
  assert.strictEqual(revocationReceipt.reason, "grant expired");
});

test("LAMBDA-03 generates revocation invalidations across all runtime surfaces", () => {
  const grant = fixedGrant({
    principalId: "collab-001",
    resource: "portal.tasks",
    action: "portal.edit",
    id: "grant-revoke-001",
  });
  const receipt = buildPortalGrantRevocationReceipt({
    principalId: "owner-001",
    principalType: "owner",
    partitionId: "partition-a",
    grant,
    reason: "revoked",
    requestId: "revocation-002",
  });
  const surfaces = receipt.invalidations.map((invalidation) => invalidation.surface);
  const expected: readonly PortalRuntimeSurface[] = ["session", "cache", "search", "jobs", "downloads"];
  assert.deepStrictEqual(surfaces, expected);
  for (const invalidation of receipt.invalidations) {
    assert.ok(invalidation.key.includes("partition-a"));
    assert.ok(invalidation.key.includes("collab-001"));
    assert.ok(invalidation.reason.includes("grant lifecycle"));
  }
});

test("LAMBDA-03 blocks cross-partition portal routes and tools", () => {
  const routes: readonly PortalResource[] = [
    "dashboard",
    "people",
    "organizations",
    "engagements",
    "projects",
    "tasks",
    "commitments",
    "decisions",
    "meetings",
    "notes",
    "artifacts",
    "search",
  ];
  const memberships = [fixedMembership("collab-001", "editor", "partition-a")];
  const grants = [fixedGrant({
    resource: "portal.*",
    action: "portal.edit",
    id: "grant-any",
  })];
  const navigation = [
    {
      id: "notes",
      label: "Notes",
      href: "/portal/notes",
      minimumCapability: "viewer",
    },
    {
      id: "tasks",
      label: "Tasks",
      href: "/portal/tasks",
      minimumCapability: "viewer",
    },
  ] as const;
  const rows = routes.map((route) => ({
    id: `${route}-row`,
    partitionId: "partition-a",
    ownerOnly: false,
    body: `${route}-record`,
  }));

  for (const route of routes) {
    const projection = projectPortalResource({
      principalId: "collab-001",
      principalType: "collaborator",
      partitionId: "partition-b",
      resource: route,
      memberships,
      grants,
      now: baseNow,
      requestedCapability: "viewer",
      rows,
      navigation,
    });
    assert.strictEqual(projection.granted, false);
    assert.strictEqual(projection.rows.length, 0);
    assert.strictEqual(projection.links.length, 0);

    const comment = buildPortalComment({
      kind: "comment",
      principalId: "collab-001",
      principalType: "collaborator",
      partitionId: "partition-b",
      resource: route,
      targetId: `${route}-target`,
      memberships,
      grants,
      now: baseNow,
      requestId: `comment-${route}`,
      body: "from-a-different-partition",
    });
    assert.strictEqual(comment.status, "denied");

    const acknowledgment = buildPortalAcknowledgement({
      kind: "acknowledgement",
      principalId: "collab-001",
      principalType: "collaborator",
      partitionId: "partition-b",
      resource: route,
      targetId: `${route}-target`,
      memberships,
      grants,
      now: baseNow,
      requestId: `ack-${route}`,
      acknowledged: true,
    });
    assert.strictEqual(acknowledgment.status, "denied");

    const upload = buildPortalUpload({
      kind: "upload",
      principalId: "collab-001",
      principalType: "collaborator",
      partitionId: "partition-b",
      resource: "artifacts",
      targetId: `${route}-target`,
      memberships,
      grants,
      now: baseNow,
      requestId: `upload-${route}`,
      filename: `${route}.txt`,
      mimeType: "text/plain",
      sizeBytes: 1024,
    });
    assert.strictEqual(upload.status, "denied");

    const transition = buildPortalTaskTransition({
      kind: "task.transition",
      principalId: "collab-001",
      principalType: "collaborator",
      partitionId: "partition-b",
      resource: route === "tasks" ? "tasks" : "tasks",
      targetId: `${route}-task-target`,
      memberships,
      grants,
      now: baseNow,
      requestId: `transition-${route}`,
      transition: "start",
      currentTaskState: "open",
    });
    assert.strictEqual(transition.status, "denied");
  }
});
