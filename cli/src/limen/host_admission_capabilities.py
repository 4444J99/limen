"""Versioned compatibility document for immutable host-admission consumers."""

from __future__ import annotations

from typing import Any

CAPABILITY_SCHEMA = "limen.codex_host_admission_capabilities.v1"
READER_PROTOCOL = "limen.host_admission_reader.v2"
POLICY_REVISION = "2026-07-23.shared-action-admission.v1"
LEGACY_STATE_SCHEMA = "limen.host_admission_state.v1"
SCOPED_STATE_SCHEMA = "limen.host_admission_scoped_state.v1"


def host_admission_capabilities() -> dict[str, Any]:
    """Return a fresh compatibility document without reading or writing host state."""

    return {
        "schema": CAPABILITY_SCHEMA,
        "reader_protocol": READER_PROTOCOL,
        "policy_revision": POLICY_REVISION,
        "state_schemas": {
            "legacy": LEGACY_STATE_SCHEMA,
            "scoped": SCOPED_STATE_SCHEMA,
        },
        "lease_kinds": [
            "execution",
            "heavy",
            "execution:<sha256>",
        ],
        "stable_action_denial": True,
        "single_rejection_channel": True,
        "migration": "scoped-leases-move-out-of-legacy-under-shared-lock",
    }


__all__ = [
    "CAPABILITY_SCHEMA",
    "LEGACY_STATE_SCHEMA",
    "POLICY_REVISION",
    "READER_PROTOCOL",
    "SCOPED_STATE_SCHEMA",
    "host_admission_capabilities",
]
