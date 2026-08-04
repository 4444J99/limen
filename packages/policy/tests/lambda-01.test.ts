import { test } from "node:test";
import assert from "node:assert";
import {
  buildPortalGrantProposal,
  projectPortalResource,
  resolvePortalCapabilityFromGrants,
} from "../src/index.ts";
import type {
  PartitionMembership,
  CapabilityGrant,
  PortalResource,
  PortalNavigationSeed,
  PortalGrantProposalInput,
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
    id: `grant-${partial.id || "base"}`,
    principalId: "alice",
    partitionId: "partition-a",
    resource: "portal.notes",
    action: "portal.edit",
    effect: "allow",
    issuedBy: "owner-principal",
    issuedAt: "2026-01-02T00:00:00.000Z",
    expiresAt: null,
    ...partial,
  };
}

test("LAMBDA-01 derives portal capability by partition role and explicit grant", () => {
  assert.strictEqual(
    resolvePortalCapabilityFromGrants({
      principalId: "alice",
      partitionId: "partition-a",
      memberships: [fixedMembership("alice", "editor")],
      grants: [],
      resource: "notes",
      now: baseNow,
    }),
    "contributor",
  );

  assert.strictEqual(
    resolvePortalCapabilityFromGrants({
      principalId: "alice",
      partitionId: "partition-a",
      memberships: [fixedMembership("alice", "admin")],
      grants: [fixedPortalGrant({ action: "portal.view" })],
      resource: "notes",
      now: baseNow,
    }),
    "editor",
  );

  assert.strictEqual(
    resolvePortalCapabilityFromGrants({
      principalId: "alice",
      partitionId: "partition-a",
      memberships: [fixedMembership("alice", "admin"), fixedMembership("alice", "viewer")],
      grants: [fixedPortalGrant({ action: "portal.edit", resource: "portal.notes" })],
      resource: "notes",
      now: baseNow,
    }),
    "editor",
  );
});

test("LAMBDA-01 builds collaborator-safe grant preview receipts without invitations", () => {
  const denied = buildPortalGrantProposal({
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    requestedBy: "owner-principal",
    resource: "notes",
    requestedCapability: "editor",
    memberships: [fixedMembership("alice", "viewer")],
    grants: [],
    now: baseNow,
  } as PortalGrantProposalInput);

  assert.strictEqual(denied.allowed, false);
  assert.strictEqual(denied.invitationDeliveryEnabled, false);
  assert.strictEqual(denied.resolvedCapability, "viewer");
  assert.strictEqual(denied.requestedCapability, "editor");

  const grant = fixedPortalGrant({
    id: "grant-portal-edit",
    action: "portal.edit",
    resource: "portal.notes",
  });
  const allowed = buildPortalGrantProposal({
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    requestedBy: "owner-principal",
    resource: "notes",
    requestedCapability: "editor",
    memberships: [fixedMembership("alice", "viewer")],
    grants: [grant],
    now: baseNow,
  } as PortalGrantProposalInput);

  assert.strictEqual(allowed.allowed, true);
  assert.strictEqual(allowed.invitationDeliveryEnabled, false);
  assert.strictEqual(allowed.resolvedCapability, "editor");
  assert.strictEqual(allowed.status, "preview");
});

test("LAMBDA-01 projects portal records without foreign partition or owner-only leakage", () => {
  type NoteRecord = {
    id: string;
    partitionId: string;
    ownerOnly?: boolean;
    body: string;
  };

  const navigation: readonly PortalNavigationSeed[] = [
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
      minimumCapability: "editor",
    },
  ];

  const rows: readonly NoteRecord[] = [
    {
      id: "n-01",
      partitionId: "partition-a",
      ownerOnly: false,
      body: "shared note",
    },
    {
      id: "n-02",
      partitionId: "partition-a",
      ownerOnly: true,
      body: "private note",
    },
    {
      id: "n-03",
      partitionId: "partition-b",
      ownerOnly: false,
      body: "other partition",
    },
  ];

  const viewerProjection = projectPortalResource<NoteRecord>({
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-a",
    resource: "notes" as PortalResource,
    memberships: [fixedMembership("alice", "viewer")],
    grants: [],
    now: baseNow,
    requestedCapability: "viewer",
    rows,
    navigation,
  });

  assert.strictEqual(viewerProjection.granted, true);
  assert.strictEqual(viewerProjection.rows.length, 1);
  assert.strictEqual(viewerProjection.rows[0].id, "n-01");
  assert.strictEqual(viewerProjection.counts.visible, 1);
  assert.strictEqual(viewerProjection.counts.droppedOwnerOnly, 1);
  assert.strictEqual(viewerProjection.links.length, 1);
  assert.strictEqual(viewerProjection.links[0]?.id, "notes");

  const deniedProjection = projectPortalResource<NoteRecord>({
    principalId: "alice",
    principalType: "collaborator",
    partitionId: "partition-b",
    resource: "notes" as PortalResource,
    memberships: [fixedMembership("alice", "viewer", "partition-a")],
    grants: [],
    now: baseNow,
    requestedCapability: "editor",
    rows,
    navigation,
  });

  assert.strictEqual(deniedProjection.granted, false);
  assert.strictEqual(deniedProjection.rows.length, 0);
  assert.strictEqual(deniedProjection.counts.visible, 0);
  assert.strictEqual(deniedProjection.counts.droppedOwnerOnly, 0);
  assert.strictEqual(deniedProjection.links.length, 0);
  assert.strictEqual(deniedProjection.errors.length, 1);
});
