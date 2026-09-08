#!/usr/bin/env python3
"""Run notification producers under an authenticated, bounded conduct packet.

--apply requires the existing LIMEN_CONDUCT_URL/TOKEN, LIMEN_SESSION_ID,
LIMEN_RUN_ID and LIMEN_LEASE_ID/GENERATION/TOKEN runtime bindings. --fresh-lease
instead reserves, claims and reports one new packet for a pre-registered,
unprotected notification-one-shot executor session belonging to that principal.
The packet must authorize execute + notifications, the exact producer plan and
its live/state roots, and exclusively claim notifications:one-shot. Local flock
only prevents overlapping processes; it conveys no execution authority.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "cli" / "src"))

from limen.conduct.client import HttpConductClient  # noqa: E402
from limen.conduct.broker import ConductError  # noqa: E402
from limen.conduct.models import (  # noqa: E402
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    PredicateEvidenceV1,
    ResourceClaimV1,
    RunReceiptV1,
    SpendEnvelopeV1,
    WorkPacketV1,
)
from limen.work_loan import WorkLoanV1  # noqa: E402

LIVE_ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen")).expanduser()
STATE_ROOT = Path(os.environ.get("LIMEN_NOTIFICATION_STATE_DIR", Path.home() / ".local/state/limen")).expanduser()
RECEIPT = STATE_ROOT / "notification-one-shot.json"
LOCK = STATE_ROOT / "notification-one-shot.lock"
FAILURE_STATE = STATE_ROOT / "notification-one-shot-failures.json"
OUTPUT_LINES = 20
MAX_CONSECUTIVE_FAILURES = 3
CONDUCT_TIMEOUT_SECONDS = 10
EXECUTION_RESOURCE = "notifications:one-shot"


def _execution_plan(operation: str = "produce") -> dict[str, object]:
    return {
        "operation": operation,
        "source_root": str(SOURCE_ROOT.resolve()),
        "live_root": str(LIVE_ROOT.resolve()),
        "state_root": str(STATE_ROOT.resolve()),
        "steps": [
            {"name": name, "command": command, "timeout_seconds": timeout} for name, command, timeout in _steps()
        ],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "producer_sha256": {
            str(Path(command[1]).resolve()): hashlib.sha256(Path(command[1]).read_bytes()).hexdigest()
            for _name, command, _timeout in _steps()
        },
    }


def _predicate(work_id: str, operation: str) -> str:
    return shlex.join(
        (
            sys.executable,
            str(Path(__file__).resolve()),
            "--status",
            "--expected-work-id",
            work_id,
            "--expected-operation",
            operation,
        )
    )


def _conduct_client(environment: dict[str, str]) -> HttpConductClient:
    # Never select client_from_env's local SQLite development adapter for effects.
    return HttpConductClient(
        environment.get("LIMEN_CONDUCT_URL", ""),
        environment.get("LIMEN_CONDUCT_TOKEN", ""),
        timeout=CONDUCT_TIMEOUT_SECONDS,
    )


def _hydrate_conduct_environment(environment: dict[str, str], path: Path | None) -> None:
    if path is None:
        return
    info = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise ValueError("conduct environment cache must be a user-owned mode-600 regular file")
    # Read literal exports only: never execute an environment cache as shell code.
    for line in path.read_text(encoding="utf-8").splitlines():
        words = shlex.split(line, comments=True)
        if words[:1] == ["export"]:
            words = words[1:]
        if not words or "=" not in words[0]:
            continue
        key, value = words[0].split("=", 1)
        if key in {"LIMEN_CONDUCT_URL", "LIMEN_CONDUCT_TOKEN"}:
            if len(words) != 1 or not value or "$" in value or "`" in value:
                raise ValueError("conduct environment credentials must be literal assignments")
            environment[key] = value


class ExecutionContract:
    def __init__(self, client: HttpConductClient, environment: dict[str, str], operation: str = "produce"):
        if not isinstance(client, HttpConductClient):
            raise ValueError("notification execution requires the authenticated HTTP conduct client")
        self.client = client
        self.environment = dict(environment)
        self.operation = operation
        self.run_id = environment.get("LIMEN_RUN_ID", "")
        self.lease_id = environment.get("LIMEN_LEASE_ID", "")
        self.generation = int(environment.get("LIMEN_LEASE_GENERATION", "0"))
        self.token = environment.get("LIMEN_LEASE_TOKEN", "")  # allow-secret: environment lookup, no embedded credential
        session_id = environment.get("LIMEN_SESSION_ID", "")
        if not all((self.run_id, self.lease_id, self.token, session_id)) or self.generation < 1:
            raise ValueError("notification execution requires complete owning run, lease and session bindings")
        graph = client.graph(self.run_id)
        nodes = [node for node in graph.get("nodes", []) if node.get("run_id") == self.run_id]
        if len(nodes) != 1:
            raise ValueError("notification execution run is absent or ambiguous in the authenticated graph")
        node = nodes[0]
        self.packet = WorkPacketV1.model_validate(node.get("packet"))
        lease = node.get("lease", {})
        self.executor = AgentIdentityV1.model_validate(lease.get("executor"))
        if (
            node.get("executor_session_id") != session_id
            or self.executor.session_id != session_id
            or node.get("lease_id") != self.lease_id
            or lease.get("generation") != self.generation
            or lease.get("state") not in {"active", "reserved"}
            or node.get("status") not in {"running", "reserved"}
            or node.get("stop_requested")
        ):
            raise ValueError("notification execution is not owned by the current live executor lease")
        authority = self.packet.authority
        if (
            self.packet.effect != "external"
            or not ({"execute", "*"} & authority.actions)
            or not ({"notifications", "*"} & authority.external_effects)
            or self.packet.execution.get("notification_one_shot") != _execution_plan(operation)
            or self.packet.predicate != _predicate(self.packet.work_id, operation)
            or self.packet.execution.get("executor_session_id") != session_id
            or not any(
                claim.key == EXECUTION_RESOURCE and claim.mode == "exclusive" for claim in self.packet.resource_claims
            )
            or not any(
                row.get("key") == EXECUTION_RESOURCE and row.get("mode") == "exclusive"
                for row in lease.get("resources", [])
            )
        ):
            raise ValueError("owning packet does not authorize this exact notification producer plan")
        for target in (LIVE_ROOT.resolve(), STATE_ROOT.resolve()):
            if not any(
                target.is_relative_to(Path(prefix).expanduser().resolve()) for prefix in authority.path_prefixes
            ):
                raise ValueError("owning packet does not authorize notification state roots")
        self.observed_heads = lease.get("observed_heads") or {}
        if self.observed_heads:
            raise ValueError(
                "notification packet must bind its immutable producer plan, not unobserved repository heads"
            )

    def heartbeat(self, duration: int = 0) -> dict[str, object]:
        if self.packet.execution.get("notification_one_shot") != _execution_plan(self.operation):
            raise ValueError("notification producer sources changed after packet acceptance")
        response = self.client.heartbeat(self.lease_id, self.token, generation=self.generation)
        lease = response.get("lease", {})
        if (
            response.get("status") != "active"
            or lease.get("state") != "active"
            or lease.get("run_id") != self.run_id
            or lease.get("lease_id") != self.lease_id
            or lease.get("generation") != self.generation
            or lease.get("executor") != self.executor.model_dump(mode="json")
        ):
            raise ValueError("notification executor heartbeat was fenced or did not bind the exact lease")
        deadline = datetime.fromisoformat(str(lease.get("hard_deadline", "")).replace("Z", "+00:00"))
        if (
            deadline.tzinfo is None
            or (deadline - datetime.now(UTC)).total_seconds() <= duration + CONDUCT_TIMEOUT_SECONDS
        ):
            raise ValueError("notification executor lease has insufficient deadline for the next bounded step")
        return {"run_id": self.run_id, "lease_id": self.lease_id, "generation": self.generation}


def _fresh_contract(
    client: HttpConductClient, environment: dict[str, str], operation: str = "produce"
) -> ExecutionContract:
    capabilities = client.capabilities()
    session_id = environment.get("LIMEN_SESSION_ID", "")
    if session_id not in capabilities.get("authenticated_session_ids", []):
        raise ValueError("notification scheduler needs a registered session owned by its authenticated principal")
    rows = [row for row in capabilities.get("sessions", []) if row.get("session_id") == session_id]
    if (
        len(rows) != 1
        or rows[0].get("human_protected")
        or "notification-one-shot" not in rows[0].get("capabilities", [])
    ):
        raise ValueError("notification scheduler needs an unprotected notification-one-shot executor session")
    session = ConductorSessionV1.model_validate(
        {key: value for key, value in rows[0].items() if key in ConductorSessionV1.model_fields}
    )
    client.register(session)  # Refresh the same principal-owned native identity, without adopting a human lane.
    identifier = f"notification-one-shot-{uuid4().hex}"
    packet = WorkPacketV1(
        work_id=identifier,
        work_key=identifier,
        intent={"kind": "notification-one-shot"},
        execution={"executor_session_id": session_id, "notification_one_shot": _execution_plan(operation)},
        initiator=session.identity,
        conductor=session.identity,
        preferred_agent=session.identity.agent,
        required_capabilities=frozenset({"execute", "notification-one-shot"}),
        resource_claims=(ResourceClaimV1(key=EXECUTION_RESOURCE),),
        predicate=_predicate(identifier, operation),
        receipt_target=f"git:4444J99/limen:scripts/notification-one-shot.py#{identifier}",
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"execute"}),
            external_effects=frozenset({"notifications"}),
            path_prefixes=frozenset({str(LIVE_ROOT.resolve()), str(STATE_ROOT.resolve())}),
            may_delegate=False,
        ),
        deadline=datetime.now(UTC) + timedelta(seconds=sum(row[2] for row in _steps()) + 120),
        spend=SpendEnvelopeV1(limit=1, reserve=1),
        work_loan=WorkLoanV1(
            source_origin="obligation",
            horizon="present",
            value_case="Run one bounded notification refresh under its approved schedule",
            budget_cost=1,
            owner_surface="scripts/notification-one-shot.py",
        ),
        effect="external",
    )
    submitted = client.submit(packet)
    lease = submitted.get("lease", {})
    run_id = submitted.get("run_id", "")
    lease_id = lease.get("lease_id", "")
    generation = lease.get("generation", 0)
    try:
        if not run_id or not lease_id or not generation:
            raise ValueError("notification scheduler received an invalid reservation")
        claim = client.claim(lease_id, generation)
        if claim.get("run_id") != run_id or claim.get("lease_id") != lease_id or claim.get("generation") != generation:
            raise ValueError("notification scheduler received a mismatched lease claim")
        environment.update(
            {
                "LIMEN_RUN_ID": run_id,
                "LIMEN_LEASE_ID": lease_id,
                "LIMEN_LEASE_GENERATION": str(generation),
                "LIMEN_LEASE_TOKEN": str(claim.get("capability_token", "")),
            }
        )
        return ExecutionContract(client, environment, operation)
    except (ConductError, ValueError, TypeError):
        if run_id:
            client.cancel(run_id, session_id)
        raise


def _report_contract(contract: ExecutionContract, returncode: int) -> int:
    environment = dict(contract.environment)
    environment["LIMEN_NOTIFICATION_STATE_DIR"] = str(STATE_ROOT)
    environment["LIMEN_ROOT"] = str(LIVE_ROOT)
    # This is the exact validated packet predicate, evaluated against the durable
    # local receipt of this work ID and operation, never inferred from _apply.
    predicate = subprocess.run(
        shlex.split(contract.packet.predicate),
        env=environment,
        cwd=SOURCE_ROOT,
        capture_output=True,
        text=True,
        timeout=CONDUCT_TIMEOUT_SECONDS,
        check=False,
    )
    receipt = RunReceiptV1(
        receipt_id=f"notification-{uuid4().hex}",
        run_id=contract.run_id,
        lease_id=contract.lease_id,
        lease_generation=contract.generation,
        executor=contract.executor,
        predicate=PredicateEvidenceV1(
            command=contract.packet.predicate,
            exit_code=predicate.returncode,
            summary=f"{contract.operation} receipt checked for exact work identity; operation exit={returncode}",
        ),
        outcome="succeeded" if returncode == 0 and predicate.returncode == 0 else "failed",
        spend={"runs": 1},
    )
    result = contract.client.report(contract.lease_id, contract.token, receipt, generation=contract.generation)
    if (
        result.get("mutation_authorized") is not True
        or result.get("run_status") != receipt.outcome
        or result.get("run_id") != contract.run_id
    ):
        raise ValueError("notification scheduler run receipt was not accepted by the owning broker")
    return predicate.returncode


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _steps() -> list[tuple[str, list[str], int]]:
    python = sys.executable
    scripts = SOURCE_ROOT / "scripts"
    return [
        ("live-root", [python, str(scripts / "_root.py"), "--require-body"], 15),
        ("ships-24h", [python, str(scripts / "ships-24h-refresh.py")], 120),
        ("ci-observation", [python, str(scripts / "check-main-green.py"), "--dry-run"], 90),
        ("host-observation", [python, str(scripts / "host-relief.py"), "--check", "--no-notify", "--json"], 30),
        ("events", [python, str(scripts / "notify-events.py"), "--apply"], 30),
        ("diurnal", [python, str(scripts / "diurnal.py"), "--phase", "auto"], 240),
    ]


def _run_step(name: str, command: list[str], timeout: int, environment: dict[str, str]) -> dict[str, object]:
    started = _now()
    try:
        executable = Path(command[0]).resolve()
        script = Path(command[1]).resolve()
        script.relative_to((SOURCE_ROOT / "scripts").resolve())
        if executable != Path(sys.executable).resolve() or script.suffix not in {".py", ".sh"}:
            raise ValueError("command is outside the immutable notification producer allowlist")
    except (IndexError, OSError, ValueError) as exc:
        return {
            "name": name,
            "started_at": started,
            "finished_at": _now(),
            "returncode": 126,
            "output_tail": [str(exc)],
            "timed_out": False,
            "producer_complete": False,
        }
    try:
        completed = subprocess.run(
            command,
            cwd=SOURCE_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        output = [line for line in (completed.stdout + completed.stderr).splitlines() if line]
        return {
            "name": name,
            "started_at": started,
            "finished_at": _now(),
            "returncode": completed.returncode,
            "output_tail": output[-OUTPUT_LINES:],
            "timed_out": False,
            "producer_complete": _producer_complete(name, completed.returncode),
        }
    except subprocess.TimeoutExpired as exc:
        output = [line for line in str(exc.stdout or "").splitlines() if line]
        return {
            "name": name,
            "started_at": started,
            "finished_at": _now(),
            "returncode": 124,
            "output_tail": output[-OUTPUT_LINES:],
            "timed_out": True,
            "producer_complete": False,
        }


def _producer_complete(name: str, returncode: int) -> bool:
    if returncode != 0:
        return False
    if name != "ships-24h":
        return True
    cache = LIVE_ROOT / "logs" / "ships-24h.json"
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(str(payload["generated_at"]))
        if generated_at.tzinfo is None:
            generated_at = generated_at.astimezone()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    age_seconds = (datetime.now(UTC) - generated_at.astimezone(UTC)).total_seconds()
    return payload.get("complete") is True and payload.get("error") is None and 0 <= age_seconds <= 2400


def _load_failure_state() -> dict[str, object]:
    try:
        payload = json.loads(FAILURE_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"consecutive_failures": 0}
    count = payload.get("consecutive_failures") if isinstance(payload, dict) else 0
    return {"consecutive_failures": count if isinstance(count, int) and count >= 0 else 0}


def _status(expected_work_id: str | None = None, expected_operation: str | None = None) -> int:
    try:
        payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {"schema": "limen.notification_one_shot.v1", "status": "unavailable"}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return (
        0
        if (
            isinstance(payload, dict)
            and payload.get("status") == "complete"
            and (expected_work_id is None or payload.get("work_id") == expected_work_id)
            and (expected_operation is None or payload.get("operation") == expected_operation)
        )
        else 1
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="print the latest private run receipt")
    parser.add_argument("--expected-work-id", help="require this exact owning work ID in the status predicate")
    parser.add_argument(
        "--expected-operation",
        choices=("produce", "reset-failures"),
        help="require this operation in the status predicate",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the bounded execution plan")
    parser.add_argument(
        "--apply", action="store_true", help="validate the owning conduct lease and run producer effects"
    )
    parser.add_argument(
        "--fresh-lease", action="store_true", help="reserve and report a fresh owning packet for this invocation"
    )
    parser.add_argument(
        "--conduct-env-file",
        type=Path,
        help="private mode-600 literal conduct URL/token exports for scheduled execution",
    )
    parser.add_argument("--reset-failures", action="store_true", help="clear the consecutive-failure kill switch")
    arguments = parser.parse_args(argv)
    if arguments.status:
        return _status(arguments.expected_work_id, arguments.expected_operation)
    plan = [{"name": name, "command": command, "timeout_seconds": timeout} for name, command, timeout in _steps()]
    if arguments.dry_run or not arguments.apply:
        print(
            json.dumps(
                {
                    "schema": "limen.notification_one_shot_plan.v1",
                    "apply_required": True,
                    "conduct_required": True,
                    "fresh_lease": arguments.fresh_lease,
                    "steps": plan,
                },
                indent=2,
            )
        )
        return 0

    failure_state = _load_failure_state()
    prior_failures = int(failure_state["consecutive_failures"])
    if prior_failures >= MAX_CONSECUTIVE_FAILURES and not arguments.reset_failures:
        return 78
    environment = dict(os.environ)
    operation = "reset-failures" if arguments.reset_failures else "produce"
    contract = None
    try:
        _hydrate_conduct_environment(environment, arguments.conduct_env_file)
        client = _conduct_client(environment)
        contract = (
            _fresh_contract(client, environment, operation)
            if arguments.fresh_lease
            else ExecutionContract(client, environment, operation)
        )
        contract.heartbeat()
        returncode = _apply(contract, environment, prior_failures, reset_failures=arguments.reset_failures)
    except (ConductError, OSError, ValueError, TypeError) as exc:
        # Broker response bodies may contain private material; do not echo them.
        print(f"notification-one-shot: authenticated execution refused ({type(exc).__name__})", file=sys.stderr)
        returncode = 77
    if arguments.fresh_lease and contract is not None:
        try:
            predicate_returncode = _report_contract(contract, returncode)
            returncode = returncode or predicate_returncode
        except (ConductError, OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
            print(f"notification-one-shot: owning broker receipt not accepted ({type(exc).__name__})", file=sys.stderr)
            if RECEIPT.is_file():
                receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
                if receipt.get("execution_lease", {}).get("run_id") == contract.run_id:
                    receipt.update(status="report_failed", producer_returncode=returncode)
                    _atomic_json(RECEIPT, receipt)
            return 77
    return returncode


def _apply(
    contract: ExecutionContract, environment: dict[str, str], prior_failures: int, *, reset_failures: bool = False
) -> int:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 75
        lease_receipt = contract.heartbeat()
        if reset_failures:
            _atomic_json(FAILURE_STATE, {"consecutive_failures": 0, "reset_at": _now()})
            _atomic_json(
                RECEIPT,
                {
                    "schema": "limen.notification_one_shot.v1",
                    "status": "complete",
                    "observed_at": _now(),
                    "work_id": contract.packet.work_id,
                    "operation": "reset-failures",
                    "execution_lease": lease_receipt,
                    "local_overlap_guard": "exclusive-flock",
                    "consecutive_failures": 0,
                    "kill_switch_active": False,
                    "steps": [],
                },
            )
            return 0
        environment["LIMEN_ROOT"] = str(LIVE_ROOT)
        environment["LIMEN_DIURNAL_SHIP"] = "0"
        results: list[dict[str, object]] = []
        for name, command, timeout in _steps():
            try:
                contract.heartbeat(timeout)
            except (ConductError, ValueError, TypeError):
                results.append(
                    {"name": name, "returncode": 77, "producer_complete": False, "reason": "owning lease unavailable"}
                )
                break
            result = _run_step(name, command, timeout, environment)
            results.append(result)
            if name == "live-root" and result["returncode"] != 0:
                break
        complete = len(results) == len(_steps()) and all(
            row["returncode"] == 0 and row.get("producer_complete") is True for row in results
        )
        consecutive_failures = 0 if complete else prior_failures + 1
        kill_switch_active = consecutive_failures >= MAX_CONSECUTIVE_FAILURES
        _atomic_json(
            FAILURE_STATE,
            {
                "consecutive_failures": consecutive_failures,
                "kill_switch_active": kill_switch_active,
                "updated_at": _now(),
            },
        )
        runtime_sha = SOURCE_ROOT.parent.name if len(SOURCE_ROOT.parent.name) == 40 else None
        receipt = {
            "schema": "limen.notification_one_shot.v1",
            "observed_at": _now(),
            "status": "complete" if complete else "failed",
            "work_id": contract.packet.work_id,
            "operation": "produce",
            "execution_lease": lease_receipt,
            "local_overlap_guard": "exclusive-flock",
            "runtime_sha": runtime_sha,
            "source_root": str(SOURCE_ROOT),
            "live_root": str(LIVE_ROOT),
            "consecutive_failures": consecutive_failures,
            "kill_switch_active": kill_switch_active,
            "steps": results,
        }
        _atomic_json(RECEIPT, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
