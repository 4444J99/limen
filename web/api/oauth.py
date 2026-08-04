"""
OAuth2 Provider & Token Authority for FastAPI.
Supports Authorization Code Grant with PKCE (S256), Client Credentials Grant, and Persona Resolution.
"""
import base64
import hmac
import hashlib
import os
import secrets
import time
from typing import Dict, Any, Optional, Set, Tuple


class OAuthError(Exception):
    def __init__(self, error: str, description: str, status_code: int = 400):
        self.error = error
        self.description = description
        self.status_code = status_code
        super().__init__(f"{error}: {description}")


class OAuth2Provider:
    def __init__(self):
        self.clients: Dict[str, Dict[str, Any]] = {
            "client-id-01": {
                "client_id": "client-id-01",
                "client_secret": "client-secret-01-super-secret-value-24-chars",
                "redirect_uris": ["http://localhost:3000/callback", "https://example.com/oauth/callback"],
                "default_scope": "read write",
            }
        }
        self.auth_codes: Dict[str, Dict[str, Any]] = {}
        self.tokens: Dict[str, Dict[str, Any]] = {}

    def register_client(self, client_id: str, client_secret: str, redirect_uris: list[str], default_scope: str = "read"):
        self.clients[client_id] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": redirect_uris,
            "default_scope": default_scope,
        }

    def create_authorization_code(
        self,
        client_id: str,
        redirect_uri: str,
        user_id: str,
        scope: str,
        code_challenge: str,
        code_challenge_method: str = "S256",
    ) -> str:
        client = self.clients.get(client_id)
        if not client:
            raise OAuthError("invalid_client", "Unknown client_id")
        if redirect_uri not in client["redirect_uris"]:
            raise OAuthError("invalid_request", "Redirect URI not registered")

        code = f"code_{secrets.token_hex(16)}"
        expires_at = time.time() + 600  # 10m TTL

        self.auth_codes[code] = {
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "user_id": user_id,
            "scope": scope or client["default_scope"],
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "used": False,
            "expires_at": expires_at,
        }
        return code

    def handle_authorization_code_flow(
        self,
        client_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> Dict[str, Any]:
        record = self.auth_codes.get(code)
        if not record:
            raise OAuthError("invalid_grant", "Authorization code not found")

        if record["used"]:
            raise OAuthError("invalid_grant", "Authorization code has already been used")

        if time.time() > record["expires_at"]:
            raise OAuthError("invalid_grant", "Authorization code has expired")

        if record["client_id"] != client_id:
            raise OAuthError("invalid_grant", "Client ID mismatch")

        if record["redirect_uri"] != redirect_uri:
            raise OAuthError("invalid_grant", "Redirect URI mismatch")

        # Verify PKCE S256 code verifier
        hashed = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        computed_challenge = base64.urlsafe_b64encode(hashed).decode("utf-8").rstrip("=")

        if not hmac.compare_digest(computed_challenge, record["code_challenge"]):
            raise OAuthError("invalid_grant", "PKCE code_verifier verification failed")

        # Single-use enforcement
        record["used"] = True

        access_token = f"limen_at_{secrets.token_hex(24)}"
        refresh_token = f"limen_rt_{secrets.token_hex(24)}"
        ttl = 3600

        self.tokens[access_token] = {
            "principal_id": record["user_id"],
            "scope": record["scope"],
            "expires_at": time.time() + ttl,
        }

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "refresh_token": refresh_token,
            "scope": record["scope"],
        }

    def handle_client_credentials_flow(
        self,
        client_id: str,
        client_secret: str,
        scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self.clients.get(client_id)
        if not client:
            raise OAuthError("invalid_client", "Client authentication failed", status_code=401)

        if not hmac.compare_digest(client["client_secret"], client_secret):
            raise OAuthError("invalid_client", "Client authentication failed", status_code=401)

        granted_scope = scope or client["default_scope"]
        access_token = f"limen_at_{secrets.token_hex(24)}"
        ttl = 3600

        self.tokens[access_token] = {
            "principal_id": client_id,
            "scope": granted_scope,
            "expires_at": time.time() + ttl,
        }

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "scope": granted_scope,
        }


def resolve_persona(authorization: Optional[str], owner_tokens: Set[str], client_tokens: Set[str]) -> str:
    if not owner_tokens and not client_tokens:
        return "owner"
    if not authorization:
        return "public"
    scheme, _, token = authorization.partition(" ")  # allow-secret
    if scheme.lower() != "bearer" or not token:
        raise OAuthError("invalid_token", "Invalid authorization scheme", status_code=401)
    if token in owner_tokens:
        return "owner"
    if token in client_tokens:
        return "client"
    raise OAuthError("invalid_token", "Invalid or unassigned token", status_code=401)
