import * as crypto from "crypto";

/**
 * Deterministic RFC8785 JSON Canonicalization Scheme (JCS)
 */
export function canonicalizeJson(val: any): string {
  if (val === null || typeof val !== "object") {
    return JSON.stringify(val);
  }
  if (Array.isArray(val)) {
    return "[" + val.map((item) => canonicalizeJson(item)).join(",") + "]";
  }
  const keys = Object.keys(val).sort();
  const pairs = keys.map((key) => `${JSON.stringify(key)}:${canonicalizeJson(val[key])}`);
  return "{" + pairs.join(",") + "}";
}

export function signPayload(payload: any, secret: string, timestamp?: number): { signatureHeader: string; timestamp: number; canonicalJson: string } {  // allow-secret
  const ts = timestamp ?? Math.floor(Date.now() / 1000);
  const canonicalJson = canonicalizeJson(payload);
  const dataToSign = `${ts}.${canonicalJson}`;
  const hmac = crypto.createHmac("sha256", secret).update(dataToSign).digest("hex");
  const signatureHeader = `t=${ts},v1=${hmac}`;
  return { signatureHeader, timestamp: ts, canonicalJson };
}

export interface WebhookDeliveryOptions {
  targetUrl: string;
  payload: any;
  secret: string;  // allow-secret
  timeoutMs?: number;
  maxAttempts?: number;
}

export interface WebhookDeliveryResult {
  success: boolean;
  statusCode?: number;
  attempts: number;
  signatureHeader: string;
  error?: string;
}

export class WebhookDispatcher {
  public async deliverWebhook(options: WebhookDeliveryOptions): Promise<WebhookDeliveryResult> {
    const { targetUrl, payload, secret, maxAttempts = 3 } = options;
    const { signatureHeader, canonicalJson } = signPayload(payload, secret);

    let attempts = 0;
    let lastError: string | undefined;

    while (attempts < maxAttempts) {
      attempts++;
      try {
        const response = await fetch(targetUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Collab-Signature": signatureHeader,
          },
          body: canonicalJson,
        });

        if (response.ok) {
          return {
            success: true,
            statusCode: response.status,
            attempts,
            signatureHeader,
          };
        }
        lastError = `HTTP ${response.status}: ${response.statusText}`;
      } catch (err: any) {
        lastError = err.message || String(err);
      }

      if (attempts < maxAttempts) {
        const delayMs = Math.pow(2, attempts) * 100;
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }

    return {
      success: false,
      attempts,
      signatureHeader,
      error: lastError || "Failed delivery after retries",
    };
  }
}
