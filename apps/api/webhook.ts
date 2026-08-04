import * as crypto from "crypto";

export interface WebhookVerificationResult {
  valid: boolean;
  reason?: string;
  timestamp?: number;
  payload?: any;
}

export class WebhookIngress {
  private processedKeys: Set<string> = new Set();
  private maxDriftSec: number = 300; // 5 minutes max timestamp drift
  private maxPayloadBytes: number = 1048576; // 1 MB payload ceiling

  constructor(options?: { maxDriftSec?: number; maxPayloadBytes?: number }) {
    if (options?.maxDriftSec) this.maxDriftSec = options.maxDriftSec;
    if (options?.maxPayloadBytes) this.maxPayloadBytes = options.maxPayloadBytes;
  }

  public checkSizeBounds(rawBody: string | Buffer): boolean {
    const byteLength = typeof rawBody === "string" ? Buffer.byteLength(rawBody) : rawBody.length;
    return byteLength <= this.maxPayloadBytes;
  }

  public parseSignatureHeader(header: string): { timestamp: number; v1Sig: string } | null {
    if (!header) return null;
    let timestamp: number | null = null;
    let v1Sig: string | null = null;

    const parts = header.split(",");
    for (const part of parts) {
      const [key, val] = part.trim().split("=");
      if (key === "t" && val) {
        timestamp = parseInt(val, 10);
      } else if (key === "v1" && val) {
        v1Sig = val;
      }
    }

    if (!timestamp || isNaN(timestamp) || !v1Sig) {
      return null;
    }
    return { timestamp, v1Sig };
  }

  public verifySignature(rawBody: string | Buffer, signatureHeader: string, secret: string): { valid: boolean; timestamp?: number; reason?: string } {  // allow-secret
    const parsed = this.parseSignatureHeader(signatureHeader);
    if (!parsed) {
      return { valid: false, reason: "Malformed X-Collab-Signature header" };
    }

    const { timestamp, v1Sig } = parsed;
    const bodyStr = typeof rawBody === "string" ? rawBody : rawBody.toString("utf-8");
    const dataToSign = `${timestamp}.${bodyStr}`;

    const computedHex = crypto.createHmac("sha256", secret).update(dataToSign).digest("hex");

    const v1Buf = Buffer.from(v1Sig, "hex");
    const computedBuf = Buffer.from(computedHex, "hex");

    if (v1Buf.length !== computedBuf.length || !crypto.timingSafeEqual(v1Buf, computedBuf)) {
      return { valid: false, timestamp, reason: "Signature mismatch" };
    }

    return { valid: true, timestamp };
  }

  public checkReplay(timestamp: number, idempotencyKey?: string): { valid: boolean; reason?: string } {
    const now = Math.floor(Date.now() / 1000);
    const drift = Math.abs(now - timestamp);

    if (drift > this.maxDriftSec) {
      return { valid: false, reason: `Timestamp drift exceeds ${this.maxDriftSec}s threshold (${drift}s)` };
    }

    if (idempotencyKey) {
      if (this.processedKeys.has(idempotencyKey)) {
        return { valid: false, reason: `Replay attack detected: duplicate idempotency key '${idempotencyKey}'` };
      }
      this.processedKeys.add(idempotencyKey);
    }

    return { valid: true };
  }

  public handleWebhook(
    rawBody: string | Buffer,
    signatureHeader: string,
    secret: string,  // allow-secret
    idempotencyKey?: string
  ): WebhookVerificationResult {
    if (!this.checkSizeBounds(rawBody)) {
      return { valid: false, reason: `Payload size exceeds ${this.maxPayloadBytes} bytes limit` };
    }

    const sigResult = this.verifySignature(rawBody, signatureHeader, secret);
    if (!sigResult.valid || !sigResult.timestamp) {
      return { valid: false, reason: sigResult.reason || "Invalid signature" };
    }

    const replayResult = this.checkReplay(sigResult.timestamp, idempotencyKey);
    if (!replayResult.valid) {
      return { valid: false, reason: replayResult.reason };
    }

    try {
      const bodyStr = typeof rawBody === "string" ? rawBody : rawBody.toString("utf-8");
      const parsedPayload = JSON.parse(bodyStr);
      return { valid: true, timestamp: sigResult.timestamp, payload: parsedPayload };
    } catch {
      return { valid: false, reason: "Invalid JSON payload" };
    }
  }
}
