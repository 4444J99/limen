"""
Webhook ingress signature verification, replay protection, and canonical JSON egress.
"""
import hmac
import hashlib
import json
import time
from typing import Dict, Any, Tuple, Optional
import rfc8785


def sign_payload(payload: Any, secret: str, timestamp: Optional[int] = None) -> Tuple[str, int, str]:  # allow-secret
    ts = timestamp or int(time.time())
    canonical_json = rfc8785.dumps(payload).decode("utf-8")
    data_to_sign = f"{ts}.{canonical_json}"
    hex_sig = hmac.new(secret.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    signature_header = f"t={ts},v1={hex_sig}"
    return signature_header, ts, canonical_json


def parse_signature_header(header: str) -> Tuple[Optional[int], Optional[str]]:
    if not header:
        return None, None
    ts = None
    v1_sig = None
    for part in header.split(","):
        key_val = part.strip().split("=", 1)
        if len(key_val) == 2:
            k, v = key_val
            if k == "t" and v.isdigit():
                ts = int(v)
            elif k == "v1":
                v1_sig = v
    return ts, v1_sig


try:
    import db
except ImportError:
    db = None


class WebhookIngressHandler:
    def __init__(self, max_drift_sec: int = 300, max_bytes: int = 1048576):
        self.max_drift_sec = max_drift_sec
        self.max_bytes = max_bytes
        self.processed_keys: set[str] = set()

    def verify_and_admit(
        self,
        raw_body: str,
        signature_header: str,
        secret: str,  # allow-secret
        idempotency_key: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        if len(raw_body.encode("utf-8")) > self.max_bytes:
            return False, f"Payload size exceeds {self.max_bytes} bytes limit", None

        ts, v1_sig = parse_signature_header(signature_header)
        if ts is None or not v1_sig:
            return False, "Malformed X-Collab-Signature header", None

        # Replay drift check
        now = int(time.time())
        if abs(now - ts) > self.max_drift_sec:
            return False, f"Timestamp drift exceeds {self.max_drift_sec}s threshold", None

        data_to_sign = f"{ts}.{raw_body}"
        expected_hex = hmac.new(secret.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_hex, v1_sig):
            return False, "Signature mismatch", None

        if idempotency_key:
            if idempotency_key in self.processed_keys:
                return False, f"Replay attack: duplicate idempotency key '{idempotency_key}'", None
            if db is not None and hasattr(db, "db_check_and_register_idempotency_key"):
                if not db.db_check_and_register_idempotency_key(idempotency_key):
                    return False, f"Replay attack: duplicate idempotency key '{idempotency_key}'", None
            self.processed_keys.add(idempotency_key)

        try:
            parsed = json.loads(raw_body)
            return True, "valid", parsed
        except Exception:
            return False, "Invalid JSON payload", None
