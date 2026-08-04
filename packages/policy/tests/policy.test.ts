import { test } from "node:test";
import assert from "node:assert";
import {
  buildPolicyDecisionMatrix,
  evaluatePolicyDecision,
} from "../src/index.ts";
import type {
  PartitionMembership,
  CapabilityGrant,
  PolicyPrincipal,
} from "../src/index.ts";

const baseNow = "2026-08-01T00:00:00.000Z";

function fixedMembership(role: string, partitionId = "partition-a"): PartitionMembership {
  return {
    principalId: "alice",
    partitionId,
    role: role as any,
    grantedBy: "system",
    grantedAt: "2026-01-01T00:00:00.000Z",
    startAt: "2025-01-01T00:00:00.000Z",
    endAt: null,
  };
}

function fixedGrant(partial: Partial<CapabilityGrant>): CapabilityGrant {
  return {
    id: "grant-001",
    principalId: "alice",
    partitionId: "partition-a",
    resource: "note",
    action: "note.write",
    effect: "allow",
    issuedBy: "owner-principal",
    issuedAt: "2026-01-02T00:00:00.000Z",
    expiresAt: null,
    ...partial,
  };
}

test("owner-style principal can perform explicit write when no partition role exists", () => {
  const decision = evaluatePolicyDecision({
    principalId: "owner-1",
    partitionId: "partition-a",
    principalType: "owner",
    action: "note.write",
    resource: "note",
    fields: ["id", "body"],
    memberships: [],
    grants: [],
    now: baseNow,
  });

  assert.strictEqual(decision.allowed, true);
  assert.ok(decision.reasonCode.startsWith("ALLOW"));
});

test("viewer role cannot write notes without explicit grants", () => {
  const decision = evaluatePolicyDecision({
    principalId: "alice",
    partitionId: "partition-a",
    principalType: "collaborator",
    action: "note.write",
    resource: "note",
    memberships: [fixedMembership("viewer")],
    grants: [],
    now: baseNow,
  });

  assert.strictEqual(decision.allowed, false);
  assert.strictEqual(decision.reasonCode, "DENY_ROLE_MATRIX");
});

test("non-transitive explicit grant can elevate action", () => {
  const decision = evaluatePolicyDecision({
    principalId: "alice",
    partitionId: "partition-a",
    principalType: "collaborator",
    action: "note.write",
    resource: "note",
    memberships: [fixedMembership("viewer")],
    grants: [fixedGrant({})],
    now: baseNow,
  });

  assert.strictEqual(decision.allowed, true);
  assert.strictEqual(decision.reasonCode, "ALLOW_GRANT");
});

test("field visibility is redacted through the policy matrix", () => {
  const result = evaluatePolicyDecision({
    principalId: "alice",
    partitionId: "partition-a",
    principalType: "collaborator",
    action: "note.read",
    resource: "note",
    fields: ["id", "confidential_comment", "body"],
    memberships: [fixedMembership("viewer")],
    grants: [],
    now: baseNow,
  });

  assert.strictEqual(result.allowed, true);
  assert.deepStrictEqual(result.grantedFields, ["id", "body"]);
  assert.deepStrictEqual(result.redactedFields, ["confidential_comment"]);
});

test("policy matrix executes principal x partition x role x action combinations", () => {
  const principals: PolicyPrincipal[] = [
    { principalId: "alice", principalType: "collaborator" },
    { principalId: "service-bot", principalType: "service" },
  ];
  const matrix = buildPolicyDecisionMatrix({
    principals,
    partitions: ["partition-a", "partition-b"],
    memberships: [fixedMembership("editor")],
    grants: [fixedGrant({ principalId: "service-bot", action: "*" })],
    now: baseNow,
  });

  assert.ok(matrix.rows.length >= principals.length * 2 * 18);
  const row = matrix.rows.find((candidate) =>
    candidate.principalId === "alice" &&
    candidate.partitionId === "partition-a" &&
    candidate.action === "note.write",
  );
  assert.ok(row);
  assert.strictEqual(row?.principalType, "collaborator");
});
