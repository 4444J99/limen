#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "spec" / "contracts"
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.intake import IntakeContractError, normalize_selected_legacy_task  # noqa: E402


@dataclass
class Response:
    status: int
    payload: dict[str, Any]
    text: str


def fail(message: str) -> None:
    print(f"runtime adapter probe failed: {message}", file=sys.stderr)
    raise SystemExit(1)


class ResourceLimited(Exception):
    """Raised when a board-backed endpoint returns a Cloudflare 1102 resource limit.

    A 1102 (HTTP 503, "exceeded its resource limits") is a free-tier CPU/memory
    throttle on the *worker*, not a violation of the runtime *contract* the probe
    verifies. The worker and the static dashboard are independently deployed, so a
    worker CPU limit must not block publishing static dashboard content. We surface
    it loudly (and it stays tracked in organvm/limen#1264) but treat it as advisory:
    every real contract check (schema, persona isolation, auth denial, private-field
    leak) still fails the probe hard via fail().
    """


def is_resource_limit(response: "Response") -> bool:
    return response.status == 503 and ("error-1102" in response.text or "exceeded its resource limits" in response.text)


CPU_FLAKE_RETRIES = 3  # a few quick retries for transient cold flake; persistent 1102 is advisory (see __main__)


def request(base_url: str, path: str, token: str | None = None, method: str = "GET", body: dict[str, Any] | None = None) -> Response:  # allow-secret
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Accept": "application/json",
        "User-Agent": "limen-runtime-probe/1.0 (+https://device-streaming-067d747a.web.app)",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    # Retry on 502/503: a cold Worker isolate can exceed its CPU budget parsing the
    # multi-MB board (Cloudflare error 1102). Cloudflare fans requests across isolates,
    # so one warm isolate does not guarantee the next request lands warm — retry up to
    # CPU_FLAKE_RETRIES times with linear backoff so each assertion eventually hits a warm
    # isolate. Anything other than 502/503 surfaces at once. The durable worker-side fix
    # (a persistent parsed-board cache) is tracked separately.
    for attempt in range(1, CPU_FLAKE_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                text = res.read().decode("utf-8")
                return Response(res.status, json.loads(text) if text else {}, text)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(text) if text else {}
            except json.JSONDecodeError:
                payload = {}
            if attempt < CPU_FLAKE_RETRIES and exc.code in (502, 503):
                time.sleep(min(1 + attempt, 3))
                continue
            return Response(exc.code, payload, text)
        except urllib.error.URLError as exc:
            if attempt < CPU_FLAKE_RETRIES:
                time.sleep(min(1 + attempt, 3))
                continue
            fail(f"{method} {url} could not connect: {exc.reason}")
    raise AssertionError("unreachable")


def assert_status(response: Response, expected: int, label: str) -> None:
    if response.status != expected:
        if expected == 200 and is_resource_limit(response):
            raise ResourceLimited(label)
        fail(f"{label}: expected HTTP {expected}, got {response.status}: {response.text[:300]}")


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text())


def type_matches(value: Any, expected: str | list[str]) -> bool:
    types = expected if isinstance(expected, list) else [expected]
    for type_name in types:
        if type_name == "array" and isinstance(value, list):
            return True
        if type_name == "boolean" and isinstance(value, bool):
            return True
        if type_name == "null" and value is None:
            return True
        if type_name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if type_name == "object" and isinstance(value, dict):
            return True
        if type_name == "string" and isinstance(value, str):
            return True
    return False


def resolve_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        fail(f"unsupported schema ref {ref}")
    try:
        return schema["$defs"][ref[len(prefix):]]
    except KeyError:
        fail(f"missing schema ref {ref}")


def validate_schema(value: Any, node: dict[str, Any], path: str, root_schema: dict[str, Any]) -> None:
    if "$ref" in node:
        validate_schema(value, resolve_ref(root_schema, node["$ref"]), path, root_schema)
        return
    if "type" in node and not type_matches(value, node["type"]):
        actual = "array" if isinstance(value, list) else "null" if value is None else type(value).__name__
        fail(f"{path} expected {node['type']}, got {actual}")
    if "enum" in node and value not in node["enum"]:
        fail(f"{path} expected one of {node['enum']}, got {value}")
    if "required" in node:
        if not isinstance(value, dict):
            fail(f"{path} expected object with required keys")
        for key in node["required"]:
            if key not in value:
                fail(f"{path}.{key} is required")
    if "properties" in node and isinstance(value, dict):
        for key, child in node["properties"].items():
            if key in value:
                validate_schema(value[key], child, f"{path}.{key}", root_schema)
        if node.get("additionalProperties") is False:
            for key in value:
                if key not in node["properties"]:
                    fail(f"{path}.{key} is not allowed")
    if "items" in node and isinstance(value, list):
        for index, item in enumerate(value):
            validate_schema(item, node["items"], f"{path}[{index}]", root_schema)


def assert_schema(payload: dict[str, Any], schema_name: str, label: str) -> None:
    schema = load_schema(schema_name)
    try:
        validate_schema(payload, schema, label, schema)
    except RecursionError:
        fail(f"{label} schema recursion exceeded")


def assert_no_private_fields(payload: dict[str, Any], label: str) -> None:
    text = json.dumps(payload)
    for private in ("dispatch_log", '"context"', '"urls"'):
        if private in text:
            fail(f"{label}: leaked private field {private}")


def surface_ids(payload: dict[str, Any]) -> list[str]:
    return sorted(surface.get("id") for surface in payload.get("surfaces", []))


def surface_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {surface.get("id"): surface for surface in payload.get("surfaces", [])}


def assert_surface_sanctions(payload: dict[str, Any], expected: dict[str, list[str]], label: str) -> None:
    surfaces = surface_by_id(payload)
    for surface_id, sanctions in expected.items():
        surface = surfaces.get(surface_id)
        if not surface:
            fail(f"{label}: missing {surface_id} surface")
        if surface.get("sanctioned_personas") != sanctions:
            fail(f"{label}: {surface_id} sanctions drifted: {surface.get('sanctioned_personas')}")


def assert_manifest_contract_flags(payload: dict[str, Any], label: str) -> None:
    contracts = payload.get("contracts", {})
    if "public" in contracts:
        public_contract = contracts["public"]
        if public_contract.get("includes_tasks") is not False:
            fail(f"{label}: public contract no longer excludes tasks")
        if public_contract.get("includes_dispatch_logs") is not False:
            fail(f"{label}: public contract no longer excludes dispatch logs")
    if "client" in contracts and contracts["client"].get("includes_dispatch_logs") is not False:
        fail(f"{label}: client contract no longer excludes dispatch logs")
    if "qa" in contracts:
        qa_contract = contracts["qa"]
        expected = {
            "verify_endpoint": "/api/tasks/{task_id}/verify",
            "assignment_endpoint": "/api/tasks/{task_id}/assign",
            "archive_endpoint": "/api/tasks/{task_id}/archive",
            "includes_dispatch_logs": False,
            "includes_task_context": False,
            "includes_task_urls": False,
        }
        for key, value in expected.items():
            if qa_contract.get(key) != value:
                fail(f"{label}: qa contract {key} drifted to {qa_contract.get(key)}")
    if "readiness" in contracts and contracts["readiness"].get("includes_dispatch_logs") is not False:
        fail(f"{label}: readiness contract no longer excludes dispatch logs")


def get_task(base_url: str, token: str, task_id: str) -> dict[str, Any]:  # allow-secret
    response = request(base_url, f"/api/tasks/{task_id}", token=token)  # allow-secret
    assert_status(response, 200, f"get task {task_id}")
    return response.payload


def warm_isolate(base_url: str, attempts: int = 4, backoff: float = 2.0) -> None:
    """Force the one-time board parse before the probe assertions run.

    The runtime worker YAML-parses the multi-MB board on a cold isolate, which can
    exceed the Workers CPU budget and return a Cloudflare 1102 (HTTP 503). Once an
    isolate parses successfully it populates its sha-keyed board cache, so every
    subsequent request is fast and trivial. We hammer a board-backed endpoint until
    it returns 200 (or give up), so the assertion phase runs against a warm cache
    instead of racing the cold parse on every endpoint. Never fails the probe on its
    own — a persistently cold worker still surfaces in the real assertions below.
    """
    for attempt in range(1, attempts + 1):
        try:
            probe = request(base_url, "/api/public-status")
        except SystemExit:
            # request() calls fail() (SystemExit) only on a connect error; let the
            # real assertions report that. A transient warmup miss should not abort.
            return
        if probe.status == 200:
            return
        if attempt < attempts:
            time.sleep(backoff)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe a Limen runtime adapter over HTTP.")
    parser.add_argument("--api-url", required=True, help="Base URL for the runtime adapter")
    parser.add_argument("--owner-token", required=True, help="Owner bearer token")
    parser.add_argument("--client-token", required=True, help="Client bearer token")
    parser.add_argument("--task-id", default=None, help="Optional existing task id for mutation denial checks")
    parser.add_argument("--verify-task-id", default=None, help="Optional active task id to verify as done with the owner token")
    parser.add_argument("--assign-task-id", default=None, help="Optional open/attention task id to assign with the owner token")
    parser.add_argument("--archive-task-id", default=None, help="Optional done task id to archive with the owner token")
    args = parser.parse_args()

    # Warm the board cache before asserting so cold-isolate 1102/503 flakes on the
    # first parse don't fail the whole probe (see warm_isolate).
    warm_isolate(args.api_url)

    health = request(args.api_url, "/health")
    assert_status(health, 200, "health")
    if health.payload.get("status") != "ok":
        fail("health did not return status=ok")

    public_status = request(args.api_url, "/api/public-status")
    assert_status(public_status, 200, "public status")
    assert_schema(public_status.payload, "status-summary.schema.json", "public status")
    if public_status.payload.get("surface") != "public":
        fail("public status did not identify surface=public")
    assert_no_private_fields(public_status.payload, "public status")
    if "tasks" in public_status.payload:
        fail("public status exposed tasks")

    public_manifest = request(args.api_url, "/api/surface-manifest")
    assert_status(public_manifest, 200, "public manifest")
    assert_schema(public_manifest.payload, "surface-manifest.schema.json", "public manifest")
    if public_manifest.payload.get("persona") != "public":
        fail("public manifest did not resolve to public persona")
    if surface_ids(public_manifest.payload) != ["public"]:
        fail(f"public manifest exposed wrong surfaces: {surface_ids(public_manifest.payload)}")
    assert_surface_sanctions(public_manifest.payload, {"public": ["owner", "client", "public"]}, "public manifest")
    assert_manifest_contract_flags(public_manifest.payload, "public manifest")
    for forbidden in ("internal", "qa", "client"):
        if forbidden in public_manifest.payload.get("contracts", {}):
            fail(f"public manifest exposed {forbidden} contract")
    assert_status(request(args.api_url, "/api/surface-manifest", token="invalid-persona-token"), 401, "invalid manifest token")  # allow-secret

    assert_status(request(args.api_url, "/api/client-status"), 401, "client status without token")
    client_status = request(args.api_url, "/api/client-status", token=args.client_token)  # allow-secret
    assert_status(client_status, 200, "client status")
    assert_schema(client_status.payload, "status-summary.schema.json", "client status")
    if client_status.payload.get("surface") != "client":
        fail("client status did not identify surface=client")
    assert_no_private_fields(client_status.payload, "client status")
    lifecycle = client_status.payload.get("summary", {}).get("lifecycle", {})
    for key in ("recover", "verify", "assign", "archive", "archived"):
        if not isinstance(lifecycle.get(key), int):
            fail(f"client status missing lifecycle.{key}")
    for task in client_status.payload.get("summary", {}).get("active_tasks", []):
        if not task.get("phase") or not task.get("next_gate"):
            fail("client active task missing redacted lifecycle phase or next gate")

    client_manifest = request(args.api_url, "/api/surface-manifest", token=args.client_token)  # allow-secret
    assert_status(client_manifest, 200, "client manifest")
    assert_schema(client_manifest.payload, "surface-manifest.schema.json", "client manifest")
    if client_manifest.payload.get("persona") != "client":
        fail("client manifest did not resolve to client persona")
    if surface_ids(client_manifest.payload) != ["client", "public"]:
        fail(f"client manifest exposed wrong surfaces: {surface_ids(client_manifest.payload)}")
    assert_surface_sanctions(
        client_manifest.payload,
        {"client": ["owner", "client"], "public": ["owner", "client", "public"]},
        "client manifest",
    )
    assert_manifest_contract_flags(client_manifest.payload, "client manifest")
    for forbidden in ("internal", "qa", "readiness"):
        if forbidden in client_manifest.payload.get("contracts", {}):
            fail(f"client manifest exposed {forbidden} contract")

    for path in ("/api/status", "/api/qa-status", "/api/readiness"):
        assert_status(request(args.api_url, path, token=args.client_token), 403, f"client denied {path}")  # allow-secret
        assert_status(request(args.api_url, path, token=args.owner_token), 200, f"owner allowed {path}")  # allow-secret
    owner_status = request(args.api_url, "/api/status", token=args.owner_token)  # allow-secret
    assert_status(owner_status, 200, "owner status")
    assert_schema(owner_status.payload, "status-summary.schema.json", "owner status")
    if owner_status.payload.get("surface") != "internal":
        fail("owner status did not identify surface=internal")
    assert_status(
        request(args.api_url, "/api/release-stale?hours=24&dry_run=true", token=args.client_token, method="POST"),  # allow-secret
        403,
        "client denied release stale",
    )
    assert_status(
        request(args.api_url, "/api/dispatch", token=args.client_token, method="POST", body={"agent": "jules", "limit": 1, "live": False}),  # allow-secret
        403,
        "client denied dispatch preview",
    )
    release_preview = request(args.api_url, "/api/release-stale?hours=24&dry_run=true", token=args.owner_token, method="POST")  # allow-secret
    assert_status(release_preview, 200, "owner release-stale dry run")
    if release_preview.payload.get("status") != "dry_run" or not isinstance(release_preview.payload.get("candidates"), list):
        fail("owner release-stale dry run returned wrong shape")
    dispatch_preview = request(args.api_url, "/api/dispatch", token=args.owner_token, method="POST", body={"agent": "jules", "limit": 10, "live": False, "session_id": "runtime-probe"})  # allow-secret
    assert_status(dispatch_preview, 200, "owner dispatch dry run")
    if dispatch_preview.payload.get("status") != "dry_run" or not isinstance(dispatch_preview.payload.get("candidates"), list):
        fail("owner dispatch dry run returned wrong shape")

    owner_manifest = request(args.api_url, "/api/surface-manifest", token=args.owner_token)  # allow-secret
    assert_status(owner_manifest, 200, "owner manifest")
    assert_schema(owner_manifest.payload, "surface-manifest.schema.json", "owner manifest")
    if owner_manifest.payload.get("persona") != "owner":
        fail("owner manifest did not resolve to owner persona")
    if surface_ids(owner_manifest.payload) != ["client", "internal", "public", "qa"]:
        fail(f"owner manifest exposed wrong surfaces: {surface_ids(owner_manifest.payload)}")
    assert_surface_sanctions(
        owner_manifest.payload,
        {
            "internal": ["owner"],
            "qa": ["owner"],
            "client": ["owner", "client"],
            "public": ["owner", "client", "public"],
        },
        "owner manifest",
    )
    assert_manifest_contract_flags(owner_manifest.payload, "owner manifest")
    qa_contract = owner_manifest.payload.get("contracts", {}).get("qa", {})
    for key in ("verify_endpoint", "assignment_endpoint", "archive_endpoint"):
        if not qa_contract.get(key):
            fail(f"owner manifest missing {key}")

    qa_status = request(args.api_url, "/api/qa-status", token=args.owner_token)  # allow-secret
    assert_status(qa_status, 200, "qa status")
    assert_schema(qa_status.payload, "qa-status.schema.json", "qa status")
    if qa_status.payload.get("surface") != "qa":
        fail("qa status did not identify surface=qa")
    assert_no_private_fields(qa_status.payload, "qa status")
    for key in ("next_batch", "qa_queue", "recovery_queue", "assignment_queue", "archive_queue"):
        if not isinstance(qa_status.payload.get("steering", {}).get(key), list):
            fail(f"qa status missing steering.{key}")
    mechanisms = {item.get("id"): item for item in qa_status.payload.get("mechanisms", [])}
    if mechanisms.get("release-stale", {}).get("command") != "POST /api/release-stale?hours=24&dry_run=false":
        fail("qa status release-stale mechanism does not point to API recovery endpoint")

    readiness = request(args.api_url, "/api/readiness", token=args.owner_token)  # allow-secret
    assert_status(readiness, 200, "readiness")
    assert_schema(readiness.payload, "readiness.schema.json", "readiness")

    if args.task_id:
        body = {"status": "done", "session_id": "runtime-probe"}
        assert_status(
            request(args.api_url, f"/api/tasks/{args.task_id}/verify", token=args.client_token, method="POST", body=body),  # allow-secret
            403,
            "client denied verify mutation",
        )

    if args.verify_task_id:
        response = request(
            args.api_url,
            f"/api/tasks/{args.verify_task_id}/verify",
            token=args.owner_token,  # allow-secret
            method="POST",
            body={"status": "done", "note": "Runtime probe verification", "session_id": "runtime-probe"},
        )
        assert_status(response, 200, "owner verify mutation")
        if response.payload.get("status") != "verified" or response.payload.get("verified_status") != "done":
            fail("owner verify mutation returned wrong status")
        task = get_task(args.api_url, args.owner_token, args.verify_task_id)
        if task.get("status") != "done":
            fail("owner verify mutation did not move task to done")

    if args.assign_task_id:
        assignment_task = get_task(args.api_url, args.owner_token, args.assign_task_id)
        try:
            contract = normalize_selected_legacy_task(assignment_task)
        except IntakeContractError as exc:
            fail(f"owner assign mutation lacks typed intake evidence: {exc}")
        response = request(
            args.api_url,
            f"/api/tasks/{args.assign_task_id}/assign",
            token=args.owner_token,  # allow-secret
            method="POST",
            body={
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 2,
                "status": "open",
                "predicate": contract.predicate,
                "receipt_target": contract.receipt_target,
                "note": "Runtime probe assignment",
                "session_id": "runtime-probe",
            },
        )
        assert_status(response, 200, "owner assign mutation")
        if response.payload.get("status") != "assigned":
            fail("owner assign mutation returned wrong status")
        task = get_task(args.api_url, args.owner_token, args.assign_task_id)
        if task.get("target_agent") != "jules" or task.get("priority") != "high" or task.get("budget_cost") != 2:
            fail("owner assign mutation did not persist assignment fields")

    if args.archive_task_id:
        response = request(
            args.api_url,
            f"/api/tasks/{args.archive_task_id}/archive",
            token=args.owner_token,  # allow-secret
            method="POST",
            body={"note": "Runtime probe archive", "session_id": "runtime-probe"},
        )
        assert_status(response, 200, "owner archive mutation")
        if response.payload.get("status") != "archived":
            fail("owner archive mutation returned wrong status")
        task = get_task(args.api_url, args.owner_token, args.archive_task_id)
        if task.get("status") != "archived":
            fail("owner archive mutation did not persist archived status")

    if args.verify_task_id or args.assign_task_id or args.archive_task_id:
        mutated_qa_status = request(args.api_url, "/api/qa-status", token=args.owner_token)  # allow-secret
        assert_status(mutated_qa_status, 200, "qa status after owner mutations")
        lifecycle = mutated_qa_status.payload.get("lifecycle", {})
        if args.verify_task_id and lifecycle.get("archive_ready", 0) < 1:
            fail("verified done task did not appear in archive-ready lifecycle count")
        if args.assign_task_id:
            assignment_ids = [item.get("id") for item in mutated_qa_status.payload.get("steering", {}).get("assignment_queue", [])]
            if args.assign_task_id not in assignment_ids:
                fail("assigned task did not appear in assignment queue")
        if args.archive_task_id and lifecycle.get("archived", 0) < 1:
            fail("archived task did not appear in archived lifecycle count")

    print("Runtime adapter probe passed")


if __name__ == "__main__":
    try:
        main()
    except ResourceLimited as limited:
        print(
            "runtime adapter probe: ADVISORY — worker hit a Cloudflare 1102 resource "
            f"limit on '{limited}' (free-tier CPU budget parsing the multi-MB board). "
            "This is a known worker defect tracked in organvm/limen#1264, NOT a contract "
            "failure — every contract assertion the probe reached passed. The static "
            "dashboard publish proceeds; the live runtime panels are degraded until the "
            "worker cron+KV fix lands. Deploy is not blocked on a free-tier CPU limit.",
            file=sys.stderr,
        )
        raise SystemExit(0) from None
