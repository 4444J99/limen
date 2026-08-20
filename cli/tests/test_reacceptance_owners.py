"""Focused adversarial tests for recovery owner-attestation contracts."""

from __future__ import annotations

import base64
import copy
import hashlib

from limen.reacceptance_contract import COMPLETION_GATE_KEYS
from limen.reacceptance_owners import (
    CUTOFF_EVENT_OFFSET_ANCHOR_SCHEMA,
    EFFECT_OWNER_ATTESTATION_SCHEMA,
    EFFECT_OUTCOME_SCHEMA,
    OWNER_ATTESTATION_REQUIREMENTS_SCHEMA,
    OWNER_ATTESTATION_SCHEMA,
    PRIVACY_FROZEN_MANIFEST_SCHEMA,
    RSA_SHA256_PKCS1_V1_5,
    canonical_effect_owner_attestation_payload,
    canonical_owner_attestation_payload,
    cutoff_event_offset_anchor_errors,
    cutoff_event_offset_digest,
    effect_owner_attestation_errors,
    effect_owner_attestation_payload,
    effect_owner_outcome_errors,
    effect_owner_outcomes_digest,
    owner_attestation_payload,
    owner_attestation_provisioning_blockers,
    owner_attestation_requirements_digest,
    owner_attestation_scope_errors,
    owner_binding_digest,
    owner_gate_attestation_errors,
    privacy_frozen_manifest,
    privacy_frozen_manifest_digest,
    privacy_manifest_binding_errors,
)


# Static test-only 2048-bit key.  No production secret or external crypto
# package is involved; the matching private exponent is used only by _sign().
_N = int(
    "cc49694593909de5169e2f49d17060c394c998e8d60711aeaeae2538db5581dd"
    "612d0d7eea124476ac210ae0bcb777748e34abca6388d033a62e969a23ecdcc3"
    "66f189d676a34daf8b71b165aed88ee06fc8323c3bfe53ef141180641257c7e22"
    "cd178481704e1821a26bff894218d357ea198e2719b3ec7ebc40a5a2790b723b4"
    "62d1fec279e1291d304d7a55106a581a0fb343032cdf01a3b8340196520c935e1"
    "8a11fdea718593e2873df3250db36ce4ea06681095bb54cb3d30483c89b5d222"
    "1eb792272934996d28e25023491b9b99e7a711f77fcd863a31a9e8a13f00f363"
    "de814d809f97a820621dc01701a40a930337d04013d1a6892e27adf451a83",
    16,
)
_D = int(
    "47fb05f0d211fed09dab9715f78a154e54bac3fa268fcf1731cd82a80a009305"
    "a21bf1c96a488d7f131f8169b6951eae1efd481ac3ff8cfce5ed3c7b8b750644"
    "839d4fe8155d6d1e119039e58e3a17fdd4e5416e1fe57945a0589a58a86dedac"
    "30068ecf37ed2c585f469015d27c0ff96d691b298ec618d4f0a9decbed6cfc5a"
    "22a64cc029f5d8e669886143930373d00d4a942d16cf9b08987cf4f56d660b1a"
    "79da121d9070165a99c1bf7a8d0046b7613755f8abfb3901afb5c204466f8187"
    "d3da4dac8bd0a184a0872d8e0d83c03d3ededd30ddffae84db2119862d301685"
    "007ff150a2fb3de7aaef03d7a4db864469638670d1bf33007a7d026354e560e1",
    16,
)
_EFFECT_N = int(
    "b697c42fe40eecf4357373e46ba1212ca93709d039664869cbd43040dc931e5e"
    "58ed991a55139925eda5e5c7b4a07584c10704d677bcd8ce2a7c5d35056c7707"
    "4894748c5b638959d4451ff42ac57267de9e1c93aa6d59ec4ef035644f176682"
    "397b569a85e9ae954109c2153b3a0b9f17cdb3d51d0160102e6c018d2642aec3"
    "18010a9672b4a385cb66500583432a739ced1fc158498f19e970ea5fa3dfca339"
    "69b55c553ff71a837feb1e3f47a55260225b6a0d916794a81cb33dcb01b6a0f2"
    "6a05d243c50f67f2f5455b366837db0f0a23c262177d5ea7faee29e7f81cfa7"
    "d1820e0e807dee267578c4c7cc0e184843c395f5d3f249a71e1c06f7e4e1f08d",
    16,
)
_EFFECT_D = int(
    "90468b366c357ef5d7e64a048b26de57b3bd517bbe5f1b88bd0e04b2bb9763bf"
    "98f4e4acf1dc727e8db13047046a657168346b962b3684f92288f1fd1b340139"
    "3818559f31f70c687659c84dde1df5b02d2f31d55c2cdb88e536d87952256352"
    "32a94a5cfec30eb7d0942d4f29654c19816d80533c8001afc77e801b4fc810dd"
    "af8b690dba0c2536131f9354d5c5f7ec748ba2c10bfabec3efb757dcee7e0529"
    "c35241b3ef78c7a0e6744bd1da79a2220a09b7f5cc53aa47f8d9d07744fd7bd"
    "43347375bbfacd19492046cd4acf3a88350761f28c10048c75857b075dc056b3a"
    "894ced1873a69847892cb19ef09e3867d5d840e1ee11cf1f7caec6447efcd201",
    16,
)
_E = 65537
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _integer_b64url(value: int) -> str:
    return _b64url(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def _sign(message: bytes) -> str:
    width = (_N.bit_length() + 7) // 8
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(message).digest()
    encoded = b"\x00\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), _D, _N)
    return _b64url(signature.to_bytes(width, "big"))


def _effect_sign(message: bytes) -> str:
    width = (_EFFECT_N.bit_length() + 7) // 8
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(message).digest()
    encoded = b"\x00\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), _EFFECT_D, _EFFECT_N)
    return _b64url(signature.to_bytes(width, "big"))


def _public_key() -> dict[str, object]:
    return {
        "key_id": "fixture-owner-key-2026",
        "algorithm": RSA_SHA256_PKCS1_V1_5,
        "modulus": _integer_b64url(_N),
        "exponent": _E,
    }


def _effect_public_key() -> dict[str, object]:
    return {
        "key_id": "fixture-effect-owner-key-2026",
        "algorithm": RSA_SHA256_PKCS1_V1_5,
        "modulus": _integer_b64url(_EFFECT_N),
        "exponent": _E,
    }


def _scope(*, provisioned: bool = True) -> dict[str, object]:
    gates = {}
    for gate_key in sorted(COMPLETION_GATE_KEYS):
        gates[gate_key] = {
            "owner": "fixture-gate-owner",
            "predicate_command": f"scripts/verify-owner.py --gate {gate_key}",
            "keys": [_public_key()] if provisioned else [],
        }
    return {
        "known_side_effect_owners": {
            "pull_request:example/public#7": {
                "privacy_material_publicly_reachable": "private_privacy_custody_owner",
            }
        },
        "owner_attestation_requirements": {
            "schema": OWNER_ATTESTATION_REQUIREMENTS_SCHEMA,
            "gates": gates,
            "effect_owners": {
                "private_privacy_custody_owner": {
                    "keys": [_effect_public_key()] if provisioned else [],
                }
            },
        },
    }


def _attested_evidence(
    scope: dict[str, object],
    gate_key: str,
    binding_value: object,
) -> dict[str, object]:
    requirement = scope["owner_attestation_requirements"]["gates"][gate_key]  # type: ignore[index]
    evidence: dict[str, object] = {
        "owner": requirement["owner"],
        "predicate": {
            "schema": "limen.fixture.owner_predicate.v1",
            "status": "verified",
            "result": "passed",
            "command": requirement["predicate_command"],
            "verified_at": "2026-07-17T04:00:00Z",
        },
        "receipt": {
            "schema": "limen.fixture.owner_receipt.v1",
            "status": "verified",
            "url": f"https://receipts.example.invalid/{gate_key}",
            "verified_at": "2026-07-17T04:00:00Z",
        },
    }
    payload = owner_attestation_payload(
        gate_key=gate_key,
        owner=str(evidence["owner"]),
        binding_digest=owner_binding_digest(binding_value),
        predicate=evidence["predicate"],
        receipt=evidence["receipt"],
    )
    evidence["attestation"] = {
        "schema": OWNER_ATTESTATION_SCHEMA,
        "algorithm": RSA_SHA256_PKCS1_V1_5,
        "key_id": "fixture-owner-key-2026",
        "payload": payload,
        "signature": _sign(canonical_owner_attestation_payload(payload)),
    }
    return evidence


def _attested_effect_outcome(
    scope: dict[str, object],
    *,
    subject_id: str = "attempt:fixture-001",
) -> dict[str, object]:
    outcome: dict[str, object] = {
        "effect": "privacy_material_publicly_reachable",
        "historical_row_ids": ["pull_request:example/public#7"],
        "owner_surface": "private_privacy_custody_owner",
        "status": "terminal",
        "outcome": "contained",
        "predicate": {
            "status": "verified",
            "result": "passed",
            "command": "scripts/verify-private-custody.py --effect privacy",
            "verified_at": "2026-07-17T04:00:00Z",
        },
        "receipt": {
            "status": "verified",
            "url": "https://receipts.example.invalid/effects/privacy-contained",
            "verified_at": "2026-07-17T04:00:00Z",
        },
    }
    payload = effect_owner_attestation_payload(
        subject_id=subject_id,
        historical_row_ids=outcome["historical_row_ids"],
        effect=str(outcome["effect"]),
        owner_surface=str(outcome["owner_surface"]),
        status=str(outcome["status"]),
        outcome=str(outcome["outcome"]),
        predicate=outcome["predicate"],
        receipt=outcome["receipt"],
    )
    outcome["owner_attestation"] = {
        "schema": EFFECT_OWNER_ATTESTATION_SCHEMA,
        "algorithm": RSA_SHA256_PKCS1_V1_5,
        "key_id": "fixture-effect-owner-key-2026",
        "payload": payload,
        "signature": _effect_sign(canonical_effect_owner_attestation_payload(payload)),
    }
    return outcome


def test_null_or_empty_keys_are_structurally_valid_but_release_fails_closed():
    null_scope = {"owner_attestation_requirements": None}
    assert owner_attestation_scope_errors(null_scope) == []
    assert owner_attestation_requirements_digest(null_scope) is None
    assert owner_attestation_provisioning_blockers(null_scope) == ["owner_attestation_requirements_unprovisioned"]
    assert owner_gate_attestation_errors(
        scope=null_scope,
        gate_key="session_value_verified",
        owner_evidence={},
        binding_value={},
    ) == ["owner attestation requirements are unprovisioned"]

    empty_scope = _scope(provisioned=False)
    assert owner_attestation_scope_errors(empty_scope) == []
    blockers = owner_attestation_provisioning_blockers(empty_scope)
    assert len(blockers) == 6
    assert "session_value_verified:owner_public_key_unprovisioned" in blockers
    assert "effect_owner:private_privacy_custody_owner:public_key_unprovisioned" in blockers


def test_valid_scope_pinned_owner_signature_authenticates_exact_evidence():
    scope = _scope()
    gate_key = "open_prs_closed_or_reaccepted"
    binding_value = {
        "baseline_row_ids": ["pull_request:example/repo#1"],
        "terminal_row_ids": ["pull_request:example/repo#1"],
    }
    evidence = _attested_evidence(scope, gate_key, binding_value)

    assert owner_attestation_scope_errors(scope) == []
    assert owner_attestation_provisioning_blockers(scope) == []
    assert owner_attestation_requirements_digest(scope) is not None
    assert (
        owner_gate_attestation_errors(
            scope=scope,
            gate_key=gate_key,
            owner_evidence=evidence,
            binding_value=binding_value,
        )
        == []
    )


def test_receipt_url_and_predicate_command_tampering_invalidate_attestation():
    scope = _scope()
    gate_key = "session_value_verified"
    binding_value = {"attempt_ids": ["attempt:1"], "durable_value": ["attempt:1"]}
    evidence = _attested_evidence(scope, gate_key, binding_value)

    fake_url = copy.deepcopy(evidence)
    fake_url["receipt"]["url"] = "https://attacker.example.invalid/fake"  # type: ignore[index]
    errors = owner_gate_attestation_errors(
        scope=scope,
        gate_key=gate_key,
        owner_evidence=fake_url,
        binding_value=binding_value,
    )
    assert any("payload does not match current evidence" in error for error in errors)

    fake_command = copy.deepcopy(evidence)
    fake_command["predicate"]["command"] = "true"  # type: ignore[index]
    errors = owner_gate_attestation_errors(
        scope=scope,
        gate_key=gate_key,
        owner_evidence=fake_command,
        binding_value=binding_value,
    )
    assert any("predicate command does not match" in error for error in errors)
    assert any("payload does not match current evidence" in error for error in errors)


def test_predicate_and_receipt_metadata_tampering_invalidates_attestation():
    scope = _scope()
    gate_key = "session_value_verified"
    binding_value = {"attempt_ids": ["attempt:1"], "durable_value": ["attempt:1"]}
    evidence = _attested_evidence(scope, gate_key, binding_value)
    mutations = [
        ("predicate", "status", "failed"),
        ("predicate", "result", "failed"),
        ("predicate", "schema", "limen.attacker.predicate.v1"),
        ("predicate", "verified_at", "2026-07-17T05:00:00Z"),
        ("receipt", "status", "failed"),
        ("receipt", "schema", "limen.attacker.receipt.v1"),
        ("receipt", "verified_at", "2026-07-17T05:00:00Z"),
    ]

    for section, field, value in mutations:
        tampered = copy.deepcopy(evidence)
        tampered[section][field] = value  # type: ignore[index]
        errors = owner_gate_attestation_errors(
            scope=scope,
            gate_key=gate_key,
            owner_evidence=tampered,
            binding_value=binding_value,
        )
        assert any("payload does not match current evidence" in error for error in errors), (section, field, errors)


def test_fake_signature_and_binding_value_are_rejected():
    scope = _scope()
    gate_key = "no_stale_inflight_custody"
    binding_value = {"attempt_ids": ["attempt:1"], "stale_ids": []}
    evidence = _attested_evidence(scope, gate_key, binding_value)

    forged = copy.deepcopy(evidence)
    forged["attestation"]["signature"] = "A" * 342  # type: ignore[index]
    errors = owner_gate_attestation_errors(
        scope=scope,
        gate_key=gate_key,
        owner_evidence=forged,
        binding_value=binding_value,
    )
    assert any("signature is invalid" in error for error in errors)

    errors = owner_gate_attestation_errors(
        scope=scope,
        gate_key=gate_key,
        owner_evidence=evidence,
        binding_value={"attempt_ids": ["attempt:1"], "stale_ids": ["attempt:1"]},
    )
    assert any("payload does not match current evidence" in error for error in errors)


def test_effect_owner_signature_authenticates_exact_outcome():
    scope = _scope()
    outcome = _attested_effect_outcome(scope)

    assert (
        effect_owner_attestation_errors(
            scope=scope,
            subject_id="attempt:fixture-001",
            outcome=outcome,
        )
        == []
    )


def test_effect_owner_command_url_and_row_tampering_are_rejected():
    scope = _scope()
    outcome = _attested_effect_outcome(scope)

    fake_command = copy.deepcopy(outcome)
    fake_command["predicate"]["command"] = "false"  # type: ignore[index]
    errors = effect_owner_attestation_errors(
        scope=scope,
        subject_id="attempt:fixture-001",
        outcome=fake_command,
    )
    assert any("payload does not match current outcome" in error for error in errors)

    fake_url = copy.deepcopy(outcome)
    fake_url["receipt"]["url"] = "https://attacker.example.invalid/nonexistent"  # type: ignore[index]
    errors = effect_owner_attestation_errors(
        scope=scope,
        subject_id="attempt:fixture-001",
        outcome=fake_url,
    )
    assert any("payload does not match current outcome" in error for error in errors)

    wrong_rows = copy.deepcopy(outcome)
    wrong_rows["historical_row_ids"] = ["pull_request:example/public#8"]
    errors = effect_owner_attestation_errors(
        scope=scope,
        subject_id="attempt:fixture-001",
        outcome=wrong_rows,
    )
    assert any("payload does not match current outcome" in error for error in errors)


def test_execution_owner_key_cannot_forge_effect_owner_outcome():
    scope = _scope()
    outcome = _attested_effect_outcome(scope)
    attestation = outcome["owner_attestation"]
    attestation["signature"] = _sign(  # type: ignore[index]
        canonical_effect_owner_attestation_payload(attestation["payload"])  # type: ignore[index]
    )

    errors = effect_owner_attestation_errors(
        scope=scope,
        subject_id="attempt:fixture-001",
        outcome=outcome,
    )

    assert errors == ["effect owner attestation signature is invalid"]


def test_one_public_key_cannot_claim_distinct_owner_principals():
    scope = _scope()
    scope["owner_attestation_requirements"]["effect_owners"][  # type: ignore[index]
        "private_privacy_custody_owner"
    ]["keys"] = [_public_key()]

    errors = owner_attestation_scope_errors(scope)

    assert any("cannot authenticate distinct owner principals" in error for error in errors)


def test_cutoff_offsets_are_ordered_unique_and_digest_anchored():
    offsets = ["event:private-corpus:000001", "event:private-corpus:000002"]
    digest = cutoff_event_offset_digest(offsets)
    cutoff = {
        "schema": CUTOFF_EVENT_OFFSET_ANCHOR_SCHEMA,
        "status": "verified",
        "event_offsets": offsets,
        "event_offset_digest": digest,
    }
    assert cutoff_event_offset_anchor_errors(cutoff) == []

    reversed_cutoff = copy.deepcopy(cutoff)
    reversed_cutoff["event_offsets"].reverse()
    assert cutoff_event_offset_anchor_errors(reversed_cutoff) == [
        "cutoff event_offset_digest does not match the immutable offsets"
    ]

    duplicate = copy.deepcopy(cutoff)
    duplicate["event_offsets"] = [offsets[0], offsets[0]]
    assert "unique non-empty strings" in cutoff_event_offset_anchor_errors(duplicate)[0]


def test_privacy_manifest_and_effect_outcomes_bind_the_frozen_denominator():
    scope = {
        "privacy_affected_row_ids": ["pull_request:example/public#7"],
        "known_side_effects": {
            "pull_request:example/public#7": [
                "private_material_committed_to_public_history",
                "privacy_material_publicly_reachable",
            ],
        },
        "source_reference_manifest_digest": "sha256:" + "a" * 64,
    }
    manifest = privacy_frozen_manifest(scope)
    assert manifest["schema"] == PRIVACY_FROZEN_MANIFEST_SCHEMA
    manifest_digest = privacy_frozen_manifest_digest(scope)
    privacy_evidence = {"frozen_manifest_digest": manifest_digest}
    assert privacy_manifest_binding_errors(privacy_evidence, scope) == []

    changed_scope = copy.deepcopy(scope)
    changed_scope["known_side_effects"]["pull_request:example/public#7"].append("public_cache_reference")
    assert privacy_manifest_binding_errors(privacy_evidence, changed_scope) == [
        "privacy frozen_manifest_digest does not match the scope"
    ]

    outcomes = [
        {
            "schema": EFFECT_OUTCOME_SCHEMA,
            "row_id": "pull_request:example/public#7",
            "effect": effect,
            "status": "verified",
            "outcome": "contained",
            "owner": "private_privacy_custody_owner",
            "replay_authorized": False,
            "receipt": {
                "url": f"https://receipts.example.invalid/effects/{index}",
            },
        }
        for index, effect in enumerate(scope["known_side_effects"]["pull_request:example/public#7"])
    ]
    assert effect_owner_outcome_errors(scope, outcomes) == []
    assert effect_owner_outcomes_digest(outcomes).startswith("sha256:")

    missing = outcomes[:-1]
    assert effect_owner_outcome_errors(scope, missing) == [
        "effect owner outcomes do not match the frozen row/effect denominator"
    ]
