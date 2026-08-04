import { test } from "node:test";
import assert from "node:assert";
import {
  appendPolicyAuditEvent,
  assertNoPrivateFieldLeakage,
  detectPrivateFieldLeakage,
  sanitizeForIndexing,
  verifyAuditChain,
  redactPayloadForPolicy,
} from "../src/index.ts";
import type {
  PolicyAction,
  PolicyDecision,
  PolicyPrincipalType,
  PolicyRequest,
  PolicyRedactionInput,
} from "../src/index.ts";

const principal: PolicyPrincipalType = "collaborator";
const baseNow = "2026-08-01T00:00:00.000Z";

function membership(partitionId: string, role: "owner" | "admin" | "editor" | "viewer" | "auditor"): PolicyRequest["memberships"][number] {
  return {
    principalId: "alice",
    partitionId,
    role,
    grantedBy: "owner-principal",
    grantedAt: "2026-01-01T00:00:00.000Z",
    startAt: "2025-01-01T00:00:00.000Z",
    endAt: null,
  };
}

const baseRequest = {
  principalId: "alice",
  partitionId: "partition-a",
  principalType: principal,
  action: "note.read" as PolicyAction,
  resource: "note",
  memberships: [membership("partition-a", "viewer")],
  grants: [],
  now: baseNow,
};

test("policy redaction strips role-hidden fields before projection", () => {
  const payload = {
    id: "note-01",
    body: "public note",
    confidential_comment: "do not expose",
    nested: {
      encryption_nonce: "secret nonce",
      snippet: "text snippet",
    },
  };

  const redaction = redactPayloadForPolicy({
    ...baseRequest,
    fields: ["id", "body", "confidential_comment", "nested.snippet", "nested.encryption_nonce"],
    payload,
  } as PolicyRedactionInput);

  assert.deepStrictEqual(redaction.redactedPayload, {
    id: "note-01",
    body: "public note",
    nested: {
      snippet: "text snippet",
    },
  });
  assert.ok(redaction.droppedFields.includes("confidential_comment"));
  assert.ok(redaction.droppedFields.includes("nested.encryption_nonce"));
  assert.strictEqual(redaction.decision.allowed, true);
});

test("policy serialization helpers produce redacted payloads and deny payload on rejected decisions", () => {
  const denied = redactPayloadForPolicy({
    ...baseRequest,
    principalType: "service",
    action: "partition.write" as PolicyAction,
    fields: ["id"],
    payload: {
      id: "partition-01",
      display_name: "Private partition",
    },
  } as PolicyRedactionInput);

  assert.strictEqual(denied.decision.allowed, false);
  assert.deepStrictEqual(denied.redactedPayload, {});

  const indexed = sanitizeForIndexing({
    ...baseRequest,
    fields: undefined,
    payload: {
      id: "note-01",
      body: "public",
      access_token: "leaky-token",
      nested: {
        legal_hold: "hidden",
        public: "visible",
      },
    },
  } as PolicyRedactionInput);

  assert.deepStrictEqual(indexed, {
    id: "note-01",
    body: "public",
    nested: {
      public: "visible",
    },
  });
});

test("audit chain can verify integrity and detect tampering", () => {
  const redactionOne: PolicyRedactionInput = {
    ...baseRequest,
    fields: ["id"],
    payload: { id: "note-01", confidential_comment: "remove me" },
  };
  const decisionOne: PolicyDecision = {
    allowed: true,
    reasonCode: "ALLOW_ROLE_MATRIX",
    reason: "ok",
    policyVersion: "zeta-03-policy-v1",
    principalId: baseRequest.principalId,
    partitionId: baseRequest.partitionId,
    action: "note.read",
    resource: "note",
    grantedFields: ["id"],
    redactedFields: [],
    resolvedRole: "viewer",
  };

  const first = appendPolicyAuditEvent([], {
    actorId: "alice",
    partitionId: "partition-a",
    causationId: "cause-01",
    correlationId: "corr-01",
    action: "note.read",
    resourceType: "note",
    resourceId: "note-01",
    decision: decisionOne,
    request: redactionOne,
    redactedPayload: redactPayloadForPolicy(redactionOne).redactedPayload,
    reason: "first event",
  });

  const second = appendPolicyAuditEvent([first], {
    actorId: "alice",
    partitionId: "partition-a",
    causationId: "cause-02",
    correlationId: "corr-01",
    action: "note.read",
    resourceType: "note",
    resourceId: "note-02",
    decision: decisionOne,
    request: redactionOne,
    redactedPayload: redactPayloadForPolicy(redactionOne).redactedPayload,
    reason: "second event",
  });

  const valid = verifyAuditChain([first, second]);
  assert.strictEqual(valid.ok, true);
  assert.strictEqual(valid.violations.length, 0);

  const tampered = { ...second, chain_hash: "0000deadbeef" };
  const tamperCheck = verifyAuditChain([first, tampered]);
  assert.strictEqual(tamperCheck.ok, false);
  assert.strictEqual(tamperCheck.violations.length > 0, true);
});

test("private leakage detector catches sensitive artifacts before export", () => {
  const artifact = {
    id: "note-01",
    body: "public",
    raw_headers: {
      authorization: "token-value",
    },
    nested: {
      reviewer_notes: "hidden context",
      public: "ok",
    },
  };

  const leaks = detectPrivateFieldLeakage(artifact);
  assert.ok(leaks.length >= 2);
  assertNoPrivateFieldLeakage({
    id: "note-01",
    body: "safe",
    nested: { public: "ok" },
  });
});
