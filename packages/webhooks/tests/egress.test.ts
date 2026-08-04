import { test } from "node:test";
import assert from "node:assert";
import { canonicalizeJson, signPayload } from "../egress.ts";

test("RFC8785 canonical JSON sorting", () => {
  const input = { z: 1, a: 2, c: { b: 3, a: 4 } };
  const canonical = canonicalizeJson(input);
  assert.strictEqual(canonical, '{"a":2,"c":{"a":4,"b":3},"z":1}');
});

test("Webhook signature calculation with X-Collab-Signature header", () => {
  const payload = { event: "task.verified", taskId: "task-01" };
  const secret = "webhook-secret-key-12345";  // allow-secret
  const timestamp = 1700000000;

  const { signatureHeader, canonicalJson } = signPayload(payload, secret, timestamp);

  assert.ok(signatureHeader.startsWith("t=1700000000,v1="));
  assert.strictEqual(canonicalJson, '{"event":"task.verified","taskId":"task-01"}');
});
