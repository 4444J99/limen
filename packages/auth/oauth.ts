import * as crypto from "crypto";

export interface AuthorizationCodeParams {
  clientId: string;
  clientSecret?: string;
  code: string;
  redirectUri: string;
  codeVerifier: string;
}

export interface ClientCredentialsParams {
  clientId: string;
  clientSecret: string;
  scope?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  refresh_token?: string;
  scope?: string;
}

export interface AuthCodeRecord {
  code: string;
  clientId: string;
  redirectUri: string;
  userId: string;
  scope: string;
  codeChallenge: string;
  codeChallengeMethod: string;
  used: boolean;
  expiresAt: number; // Unix timestamp in ms
}

export interface ClientRecord {
  clientId: string;
  clientSecret: string;
  redirectUris: string[];
  defaultScope: string;
}

export interface OAuthGrant {
  id: string;
  principalId: string;
  clientId: string;
  scope: string;
  createdAt: string;
}

export interface ConsentScreenPayload {
  clientId: string;
  clientName: string;
  requestedScopes: string[];
  requiresConsent: boolean;
}

export type Persona = "owner" | "client" | "public";

export type PrincipalType = "owner" | "collaborator" | "service" | "agent";

export interface PrincipalRecord {
  id: string;
  principalType: PrincipalType;
  externalSubject: string;
  displayName: string;
  metadata?: Record<string, unknown>;
}

export interface SessionClaims {
  sessionId: string;
  principalId: string;
  principalType: PrincipalType;
  externalSubject: string;
  displayName: string;
  testIdentity: boolean;
  issuedAt: string;
  expiresAt: string;
}

export interface SessionRecord {
  id: string;
  principalId: string;
  tokenHash: string;
  issuedAt: string;
  expiresAt: string;
  revokedAt: string | null;
  testIdentity: boolean;
  rotatedFrom: string | null;
}

export interface PersonaTokens {
  ownerTokens: Set<string>;
  clientTokens: Set<string>;
}

export class OAuthProvider {
  private codes: Map<string, AuthCodeRecord> = new Map();
  private clients: Map<string, ClientRecord> = new Map();
  private grants: Map<string, OAuthGrant[]> = new Map();
  private tokens: Map<string, { principalId: string; scope: string; expiresAt: number; type: string }> = new Map();
  private principals: Map<string, PrincipalRecord> = new Map();
  private sessions: Map<string, SessionRecord> = new Map();
  private sessionTokens: Map<string, string> = new Map();

  constructor() {
    // Seed default test client
    this.registerClient({
      clientId: "client-id-01",
      clientSecret: "client-secret-01-super-secret-value-24-chars",
      redirectUris: ["http://localhost:3000/callback", "https://example.com/oauth/callback"],
      defaultScope: "read write",
    });

    this.seedDefaultPrincipals();
  }

  private seedDefaultPrincipals(): void {
    this.principals.set("owner-principal", {
      id: "owner-principal",
      principalType: "owner",
      externalSubject: "owner@collaboration.local",
      displayName: "System Owner",
    });
    this.principals.set("agent-principal", {
      id: "agent-principal",
      principalType: "agent",
      externalSubject: "agent@collaboration.local",
      displayName: "Automation Agent",
    });
  }

  private newSessionToken(): string {
    return `zeta01_at_${crypto.randomBytes(24).toString("hex")}`;
  }

  private hashToken(token: string): string {  // allow-secret
    return crypto.createHash("sha256").update(token).digest("hex");
  }

  private nowIso(): string {
    return new Date().toISOString();
  }

  private toClaims(record: SessionRecord, principal: PrincipalRecord): SessionClaims {
    return {
      sessionId: record.id,
      principalId: principal.id,
      principalType: principal.principalType,
      externalSubject: principal.externalSubject,
      displayName: principal.displayName,
      testIdentity: record.testIdentity,
      issuedAt: record.issuedAt,
      expiresAt: record.expiresAt,
    };
  }

  public registerClient(client: ClientRecord): void {
    this.clients.set(client.clientId, client);
  }

  public registerPrincipal(principal: PrincipalRecord): void {
    this.principals.set(principal.id, principal);
  }

  public getPrincipal(principalId: string): PrincipalRecord | null {
    return this.principals.get(principalId) ?? null;
  }

  public issueSession(
    principalId: string,
    options?: {
      ttlMs?: number;
      testIdentity?: boolean;
      rotateFromSessionId?: string;
      scope?: string;
    },
  ): { accessToken: string; claims: SessionClaims; scope: string } {
    const principal = this.principals.get(principalId);
    if (!principal) {
      throw new Error(`unknown principal ${principalId}`);
    }
    if (options?.rotateFromSessionId) {
      const current = this.sessions.get(options.rotateFromSessionId);
      if (current) {
        current.revokedAt = this.nowIso();
      }
    }

    const ttlMs = options?.ttlMs ?? 3600_000;
    const issuedAt = this.nowIso();
    const sessionId = crypto.randomUUID();
    const accessToken = this.newSessionToken();
    const expiresAt = new Date(Date.now() + ttlMs).toISOString();
    const tokenHash = this.hashToken(accessToken);

    const record: SessionRecord = {
      id: sessionId,
      principalId,
      tokenHash,
      issuedAt,
      expiresAt,
      revokedAt: null,
      testIdentity: Boolean(options?.testIdentity),
      rotatedFrom: options?.rotateFromSessionId ?? null,
    };

    this.sessions.set(sessionId, record);
    this.sessionTokens.set(tokenHash, sessionId);
    return {
      accessToken,
      scope: options?.scope ?? "read",
      claims: this.toClaims(record, principal),
    };
  }

  public resolveSession(authorizationHeader: string | undefined | null): SessionClaims {
    if (!authorizationHeader) {
      throw new Error("401: Missing Authorization header");
    }
    const [scheme, token] = authorizationHeader.split(" ");
    if (scheme?.toLowerCase() !== "bearer" || !token) {
      throw new Error("401: Invalid authorization scheme");
    }
    const tokenHash = this.hashToken(token);
    const sessionId = this.sessionTokens.get(tokenHash);
    if (!sessionId) {
      throw new Error("401: Invalid or unassigned token");
    }
    const session = this.sessions.get(sessionId);
    if (!session || session.revokedAt) {
      throw new Error("401: Session revoked");
    }
    if (Date.parse(session.expiresAt) <= Date.now()) {
      throw new Error("401: Session expired");
    }
    const principal = this.principals.get(session.principalId);
    if (!principal) {
      throw new Error("401: Session principal not found");
    }
    return this.toClaims(session, principal);
  }

  public rotateSession(
    authorizationHeader: string | undefined | null,
    options?: {
      ttlMs?: number;
      testIdentity?: boolean;
    },
  ): { accessToken: string; claims: SessionClaims } {
    const currentClaims = this.resolveSession(authorizationHeader);
    const output = this.issueSession(currentClaims.principalId, {
      ttlMs: options?.ttlMs,
      testIdentity: options?.testIdentity,
      rotateFromSessionId: currentClaims.sessionId,
    });
    return {
      accessToken: output.accessToken,
      claims: output.claims,
    };
  }

  public revokeSession(sessionId: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session || session.revokedAt) {
      return false;
    }
    session.revokedAt = this.nowIso();
    return true;
  }

  public revokePrincipalSessions(principalId: string): number {
    let revoked = 0;
    for (const session of this.sessions.values()) {
      if (session.principalId === principalId && !session.revokedAt) {
        session.revokedAt = this.nowIso();
        revoked += 1;
      }
    }
    return revoked;
  }

  public createTestIdentity(principalType: PrincipalType): { accessToken: string; claims: SessionClaims } {
    const principalId = `${principalType}-test-${crypto.randomUUID()}`;
    const testPrincipal: PrincipalRecord = {
      id: principalId,
      principalType,
      externalSubject: `test-${principalType}@collaboration.local`,
      displayName: `Test ${principalType}`,
      metadata: { isTestIdentity: true },
    };
    this.registerPrincipal(testPrincipal);
    return this.issueSession(principalId, {
      ttlMs: 60_000,
      testIdentity: true,
      scope: "test",
    });
  }

  public createAuthorizationCode(
    clientId: string,
    redirectUri: string,
    userId: string,
    scope: string,
    codeChallenge: string,
    codeChallengeMethod: string = "S256"
  ): string {
    const client = this.clients.get(clientId);
    if (!client) {
      throw new Error("invalid_client: Unknown client_id");
    }
    if (!client.redirectUris.includes(redirectUri)) {
      throw new Error("invalid_request: Redirect URI not registered");
    }

    const code = `code_${crypto.randomBytes(16).toString("hex")}`;
    const expiresAt = Date.now() + 10 * 60 * 1000; // 10 minutes TTL

    const record: AuthCodeRecord = {
      code,
      clientId,
      redirectUri,
      userId,
      scope: scope || client.defaultScope,
      codeChallenge,
      codeChallengeMethod,
      used: false,
      expiresAt,
    };

    this.codes.set(code, record);
    return code;
  }

  public async handleAuthorizationCodeFlow(params: AuthorizationCodeParams): Promise<TokenResponse> {
    const record = this.codes.get(params.code);
    if (!record) {
      throw new Error("invalid_grant: Authorization code not found");
    }

    if (record.used) {
      throw new Error("invalid_grant: Authorization code has already been used");
    }

    if (Date.now() > record.expiresAt) {
      throw new Error("invalid_grant: Authorization code has expired");
    }

    if (record.clientId !== params.clientId) {
      throw new Error("invalid_grant: Client ID mismatch");
    }

    if (record.redirectUri !== params.redirectUri) {
      throw new Error("invalid_grant: Redirect URI mismatch");
    }

    // Verify PKCE code_verifier with S256 algorithm
    const computedHash = crypto.createHash("sha256").update(params.codeVerifier).digest();
    const computedChallenge = computedHash
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");

    if (computedChallenge !== record.codeChallenge) {
      throw new Error("invalid_grant: PKCE code_verifier verification failed");
    }

    // Mark single-use code as used
    record.used = true;

    // Issue tokens
    const accessToken = `limen_at_${crypto.randomBytes(24).toString("hex")}`;
    const refreshToken = `limen_rt_${crypto.randomBytes(24).toString("hex")}`;
    const ttlSeconds = 3600;

    this.tokens.set(accessToken, {
      principalId: record.userId,
      scope: record.scope,
      expiresAt: Date.now() + ttlSeconds * 1000,
      type: "access",
    });

    // Record active grant
    const grant: OAuthGrant = {
      id: `grant_${crypto.randomBytes(8).toString("hex")}`,
      principalId: record.userId,
      clientId: record.clientId,
      scope: record.scope,
      createdAt: new Date().toISOString(),
    };
    const existing = this.grants.get(record.userId) || [];
    this.grants.set(record.userId, [...existing, grant]);

    return {
      access_token: accessToken,
      token_type: "Bearer",
      expires_in: ttlSeconds,
      refresh_token: refreshToken,
      scope: record.scope,
    };
  }

  public async handleClientCredentialsFlow(params: ClientCredentialsParams): Promise<TokenResponse> {
    const client = this.clients.get(params.clientId);
    if (!client) {
      throw new Error("invalid_client: Client authentication failed");
    }

    // Constant-time client_secret verification
    const secretBuf = Buffer.from(client.clientSecret);
    const paramBuf = Buffer.from(params.clientSecret || "");

    if (secretBuf.length !== paramBuf.length || !crypto.timingSafeEqual(secretBuf, paramBuf)) {
      throw new Error("invalid_client: Client authentication failed");
    }

    const scope = params.scope || client.defaultScope;
    const accessToken = `limen_at_${crypto.randomBytes(24).toString("hex")}`;
    const ttlSeconds = 3600;

    this.tokens.set(accessToken, {
      principalId: params.clientId,
      scope,
      expiresAt: Date.now() + ttlSeconds * 1000,
      type: "access",
    });

    return {
      access_token: accessToken,
      token_type: "Bearer",
      expires_in: ttlSeconds,
      scope,
    };
  }

  public async getConsentScreen(clientId: string, scopes: string[]): Promise<ConsentScreenPayload> {
    const client = this.clients.get(clientId);
    if (!client) {
      throw new Error("invalid_client: Unknown client_id");
    }
    return {
      clientId,
      clientName: `App (${clientId})`,
      requestedScopes: scopes,
      requiresConsent: true,
    };
  }

  public async getActiveGrants(principalId: string): Promise<OAuthGrant[]> {
    return this.grants.get(principalId) || [];
  }

  public evaluateAuthorizationDecision(
    claims: SessionClaims,
    action: string,
    resource: string,
  ): { allowed: boolean; reason: string } {
    if (claims.testIdentity) {
      return { allowed: true, reason: "test identity short-circuit" };
    }
    if (claims.principalType === "owner") {
      return { allowed: true, reason: "owner principal override" };
    }
    if (claims.principalType === "agent" && action.startsWith("automation.")) {
      return { allowed: true, reason: "agent automation action allowed" };
    }
    if (claims.principalType === "service" && resource.startsWith("system.")) {
      return { allowed: true, reason: "service principal allowed on system-scoped resource" };
    }
    if (claims.principalType === "collaborator" && resource.startsWith("matter.")) {
      return { allowed: true, reason: "collaborator allowed on matter-scoped resource" };
    }
    return { allowed: false, reason: "default deny" };
  }

  public resolvePersona(authorizationHeader: string | undefined | null, tokens: PersonaTokens): Persona {
    if (!tokens.ownerTokens.size && !tokens.clientTokens.size) {
      return "owner";
    }
    if (!authorizationHeader) {
      return "public";
    }
    const [scheme, token] = authorizationHeader.split(" ");
    if (scheme?.toLowerCase() !== "bearer" || !token) {
      throw new Error("401: Invalid authorization scheme");
    }
    if (tokens.ownerTokens.has(token)) {
      return "owner";
    }
    if (tokens.clientTokens.has(token)) {
      return "client";
    }
    throw new Error("401: Invalid or unassigned token");
  }
}
