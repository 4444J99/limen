"""Bind a recovered Jules key through CLAVIS; never invent its source or mint keys.

Run on the existing credential runtime with promptless op and authorized gh.
The default is a names-only plan. --apply validates actual provider reads before
writing the one declared CI sink. It does not arm dispatch or prove CI consumption.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any

from limen.jules_api import JulesApiClient, JulesApiError, observe

SINK = {"repo": "4444J99/limen", "name": "JULES_API_KEY"}


def _source_reference(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    decoded = urllib.parse.unquote(value)
    parts = urllib.parse.unquote(parsed.path).split("/")[1:]
    if (
        parsed.scheme != "op"
        or not parsed.netloc
        or any(char in parsed.netloc for char in "@:")
        or parsed.query
        or parsed.fragment
        or len(parts) not in {2, 3}
        or any(part in {"", ".", ".."} for part in parts)
        or any(ord(char) < 32 or ord(char) == 127 for char in decoded)
    ):
        raise ValueError("credential_source_reference_invalid")
    return value


def _resolve_source(clavis: Any, source_ref: str | None) -> str:
    if source_ref is not None:
        return _source_reference(source_ref)
    refs = {
        row.get("ref")
        for row in clavis.load_map()
        if row.get("enabled", True) and "JULES_API_KEY" in row.get("env", [])
    }
    if len(refs) != 1 or not isinstance(next(iter(refs), None), str):
        raise ValueError("credential_source_unresolved")
    return _source_reference(next(iter(refs)))


def bind_ci_credential(clavis: Any, source_ref: str | None, *, apply: bool, client_factory=JulesApiClient) -> dict:
    receipt = {
        "schema_version": "limen.jules_credential_binding.v1",
        "status": "blocked",
        "sink": dict(SINK),
        "provider_mutations": 0,
        "ci_secret_written": False,
        "ci_presence_verified": False,
        "executor_readback_verified": False,
        "activation_verified": False,
    }
    try:
        ref = _resolve_source(clavis, source_ref)
        receipt["source_reference_sha256"] = hashlib.sha256(ref.encode()).hexdigest()
        if not apply:
            return {**receipt, "status": "planned"}
        clavis.load_service_account_token()
        if not clavis.have_op() or not clavis.op_can_read_silently() or not clavis.have_gh():
            return {**receipt, "error_code": "credential_runtime_unavailable"}
        key = clavis.op_read(ref)
        if not key:
            return {**receipt, "error_code": "credential_source_unreadable"}
        client = client_factory(key)
        sources = client.sources()
        observation = observe(client.sessions(observation_only=True))
        observation["sources_observed"] = len(sources.items)
        receipt["provider_observation"] = observation
        # CLAVIS pipes the value through gh's stdin. No literal key enters argv,
        # a temporary map, an environment file, source, output, or an artifact.
        if not clavis.gh_sink_set(dict(SINK), key):
            return {**receipt, "error_code": "ci_credential_delivery_failed"}
        receipt["ci_secret_written"] = True
        if clavis.gh_sink_present(dict(SINK)) is not True:
            return {**receipt, "error_code": "ci_credential_presence_unverified"}
        receipt["ci_presence_verified"] = True
        return {**receipt, "status": "delivered_pending_executor_readback"}
    except JulesApiError as exc:
        return {**receipt, "error_code": exc.code, "http_status": exc.status}
    except ValueError as exc:
        code = str(exc)
        return {
            **receipt,
            "error_code": code
            if code in {"credential_source_reference_invalid", "credential_source_unresolved"}
            else "credential_binding_invalid",
        }
    except Exception:
        # Exception messages can carry provider bodies, source names, or values.
        return {**receipt, "error_code": "credential_binding_unavailable"}


def _clavis() -> Any:
    path = Path(__file__).resolve().parents[3] / "scripts/creds-hydrate.py"
    spec = importlib.util.spec_from_file_location("limen_jules_clavis", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("credential_runtime_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", help="An op:// reference discovered in the canonical vault; never a key value")
    parser.add_argument("--apply", action="store_true", help="Validate the recovered key and bind the exact CI sink")
    args = parser.parse_args(argv)
    try:
        result = bind_ci_credential(_clavis(), args.source_ref, apply=args.apply)
    except Exception:
        result = {"status": "blocked", "error_code": "credential_runtime_unavailable", "activation_verified": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"planned", "delivered_pending_executor_readback"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
