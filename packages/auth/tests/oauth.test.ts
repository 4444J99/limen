import { test } from "node:test";
import assert from "node:assert";
import * as crypto from "crypto";
import { OAuthProvider } from "../oauth.ts";

test("OAuth2 Authorization Code Flow with PKCE S256", async () => {
  const provider = new OAuthProvider();

  const codeVerifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
  const codeChallenge = crypto
    .createHash("sha256")
    .update(codeVerifier)
    .digest("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  const code = provider.createAuthorizationCode(
    "client-id-01",
    "http://localhost:3000/callback",
    "user-123",
    "read write",
    codeChallenge,
    "S256"
  );

  assert.ok(code.startsWith("code_"));

  // Token exchange
  const tokenRes = await provider.handleAuthorizationCodeFlow({
    clientId: "client-id-01",
    code,
    redirectUri: "http://localhost:3000/callback",
    codeVerifier,
  });

  assert.strictEqual(tokenRes.token_type, "Bearer");
  assert.ok(tokenRes.access_token.startsWith("limen_at_"));
  assert.ok(tokenRes.refresh_token?.startsWith("limen_rt_"));
  assert.strictEqual(tokenRes.scope, "read write");

  // Single-use constraint: second use should fail
  await assert.rejects(
    async () => {
      await provider.handleAuthorizationCodeFlow({
        clientId: "client-id-01",
        code,
        redirectUri: "http://localhost:3000/callback",
        codeVerifier,
      });
    },
    { message: /already been used/ }
  );
});

test("OAuth2 Client Credentials Flow with constant-time verification", async () => {
  const provider = new OAuthProvider();

  const tokenRes = await provider.handleClientCredentialsFlow({
    clientId: "client-id-01",
    clientSecret: "client-secret-01-super-secret-value-24-chars",
    scope: "read",
  });

  assert.strictEqual(tokenRes.token_type, "Bearer");
  assert.ok(tokenRes.access_token.startsWith("limen_at_"));
  assert.strictEqual(tokenRes.scope, "read");

  // Invalid secret should fail
  await assert.rejects(
    async () => {
      await provider.handleClientCredentialsFlow({
        clientId: "client-id-01",
        clientSecret: "wrong-secret",
      });
    },
    { message: /authentication failed/ }
  );
});

test("3-Tier Persona Check", () => {
  const provider = new OAuthProvider();
  const tokens = {
    ownerTokens: new Set(["owner-secret-token"]),
    clientTokens: new Set(["client-secret-token"]),
  };

  assert.strictEqual(provider.resolvePersona(undefined, tokens), "public");
  assert.strictEqual(provider.resolvePersona("Bearer owner-secret-token", tokens), "owner");
  assert.strictEqual(provider.resolvePersona("Bearer client-secret-token", tokens), "client");
  assert.throws(() => provider.resolvePersona("Bearer bad-token", tokens), /Invalid or unassigned/);
});
