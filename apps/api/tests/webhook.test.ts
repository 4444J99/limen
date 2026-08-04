import { test } from "node:test";
import assert from "node:assert";
import * as crypto from "crypto";
import { WebhookIngress } from "../webhook.ts";

test("WebhookIngress valid signature verification", () => {
  const ingress = new WebhookIngress();
  const secret = "test-secret-key-99";  // allow-secret
  const timestamp = Math.floor(Date.now() / 1000);
  const payloadStr = JSON.stringify({ event: "task.created", taskId: "task-99" });

  const dataToSign = `${timestamp}.${payloadStr}`;
  const hexSig = crypto.createHmac("sha256", secret).update(dataToSign).digest("hex");
  const signatureHeader = `t=${timestamp},v1=${hexSig}`;

  const res = ingress.handleWebhook(payloadStr, signatureHeader, secret, "key-001");
  assert.strictEqual(res.valid, true);
  assert.strictEqual(res.payload.taskId, "task-99");
});

test("WebhookIngress rejects signature mismatch", () => {
  const ingress = new WebhookIngress();
  const secret = "test-secret-key-99";  // allow-secret
  const timestamp = Math.floor(Date.now() / 1000);
  const payloadStr = JSON.stringify({ event: "task.created", taskId: "task-99" });

  const signatureHeader = `t=${timestamp},v1=00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff`;

  const res = ingress.handleWebhook(payloadStr, signatureHeader, secret);
  assert.strictEqual(res.valid, false);
  assert.strictEqual(res.reason, "Signature mismatch");
});

test("WebhookIngress rejects timestamp drift > 300s", () => {
  const ingress = new WebhookIngress();
  const secret = "test-secret-key-99";  // allow-secret
  const staleTimestamp = Math.floor(Date.now() / 1000) - 400; // 400s old
  const payloadStr = JSON.stringify({ event: "task.created" });

  const dataToSign = `${staleTimestamp}.${payloadStr}`;
  const hexSig = crypto.createHmac("sha256", secret).update(dataToSign).digest("hex");
  const signatureHeader = `t=${staleTimestamp},v1=${hexSig}`;

  const res = ingress.handleWebhook(payloadStr, signatureHeader, secret);
  assert.strictEqual(res.valid, false);
  assert.ok(res.reason?.includes("Timestamp drift exceeds"));
});

test("WebhookIngress rejects duplicate idempotency key replay", () => {
  const ingress = new WebhookIngress();
  const secret = "test-secret-key-99";  // allow-secret
  const timestamp = Math.floor(Date.now() / 1000);
  const payloadStr = JSON.stringify({ event: "task.created" });

  const dataToSign = `${timestamp}.${payloadStr}`;
  const hexSig = crypto.createHmac("sha256", secret).update(dataToSign).digest("hex");
  const signatureHeader = `t=${timestamp},v1=${hexSig}`;

  const res1 = ingress.handleWebhook(payloadStr, signatureHeader, secret, "key-repeat-01");
  assert.strictEqual(res1.valid, true);

  const res2 = ingress.handleWebhook(payloadStr, signatureHeader, secret, "key-repeat-01");
  assert.strictEqual(res2.valid, false);
  assert.ok(res2.reason?.includes("Replay attack detected"));
});
