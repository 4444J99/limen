"""Derive individual transport contracts from Domus's existing MCP authority."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

from limen.process_ownership import Process, canonical_argv, digest


def load_estate():
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location("ownership_mcp_estate", scripts / "mcp_estate.py")
        if spec is None or spec.loader is None:
            raise ValueError("capability_protocol_unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts))


def _capability_commands(name: str) -> list[list[str]]:
    """Reuse the exact-SHA hydration receipt, never adopt a matching cache path."""
    runtime = Path.home() / ".local/share/organvm/capability_runtime.py"
    if not runtime.is_file():
        return []
    spec = importlib.util.spec_from_file_location("ownership_capability_runtime", runtime)
    if spec is None or spec.loader is None:
        raise ValueError("capability_protocol_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    registry = module.load_registry(module._default_registry())
    selected = module.resolve_spec(registry, name)
    cache = module._default_cache()
    state = module._read_json(module._state_path(cache / selected.name))
    sha = state.get("sha") if state else None
    if not isinstance(sha, str) or not module._SHA_RE.fullmatch(sha):
        return []
    if not module._receipt_valid(cache / selected.name, selected, sha):
        return []
    checkout = module._checkout_for(cache / selected.name, sha)
    return [module._process_argv(checkout, selected, [])]


def _cua_embedded_commands(
    helper: Path, processes: dict[int, Process], hosts: list[dict], byte_witnesses: dict[str, str] | None = None
) -> list[list[str]]:
    """Bind exact workers to the declared REPL's embedded vendor code.

    A temporary basename, app ancestry, or matching node binary alone proves
    nothing. The assessor still independently verifies each live parent service
    and its native host identity before any returned command can be shared.
    """
    if not helper.is_file() or helper.stat().st_size > 128 * 1024 * 1024:
        return []
    parent_argv = canonical_argv([str(helper)])
    node = helper.with_name("node")
    embedded = helper.read_bytes()
    if byte_witnesses is not None:
        byte_witnesses[str(helper.resolve())] = hashlib.sha256(embedded).hexdigest()
    commands = []
    for process in processes.values():
        parent = processes.get(process.parent)
        if not parent or parent.uid != process.uid or canonical_argv(parent.argv) != parent_argv:
            continue
        argv = process.argv
        if len(argv) == 4 and argv[1:] == ("app-server", "--listen", "stdio://"):
            if Path(argv[0]).is_file() and any(canonical_argv(argv) == canonical_argv(host["argv"]) for host in hosts):
                commands.append(list(argv))
            continue
        if not node.is_file() or not argv or canonical_argv([argv[0]]) != canonical_argv([str(node)]):
            continue
        if (
            len(argv) == 7
            and argv[1] == "--experimental-vm-modules"
            and argv[3] == "--session-id"
            and argv[5] == "--working-dir"
        ):
            script, directory = Path(argv[2]), Path(argv[6])
            if script.name != "kernel.js" or not re.fullmatch(r"[a-f0-9]{32}", argv[4]):
                continue
        elif len(argv) == 3:
            script, directory = Path(argv[1]), Path(argv[2])
            if script.name != "trusted-worker.js":
                continue
        else:
            continue
        if not directory.is_absolute() or process.cwd is None or directory.resolve() != process.cwd.resolve():
            continue
        if script.is_symlink() or not script.is_file() or not 1024 <= script.stat().st_size <= 2 * 1024 * 1024:
            continue
        source = script.read_bytes()
        if source not in embedded:
            continue
        if byte_witnesses is not None:
            byte_witnesses[str(script.resolve())] = hashlib.sha256(source).hexdigest()
        commands.append(list(argv))
    return commands


def _native_helper_contracts(host: dict, home: str, policy_digest: str) -> list[dict]:
    """Only source-declared sibling helpers of an exact native host are eligible."""
    commands = []
    executable = Path(host["argv"][0]).resolve()
    if not executable.is_file():
        return []
    for helper in host.get("helpers", []):
        relative = helper.get("executable_relative")
        args = helper.get("args")
        service = helper.get("service_id")
        if (
            not isinstance(relative, str)
            or Path(relative).name != relative
            or relative in {"", ".", ".."}
            or not isinstance(args, list)
            or not all(isinstance(arg, str) for arg in args)
            or not isinstance(service, str)
            or not service.startswith("codex/")
        ):
            continue
        binary = executable.with_name(relative)
        if binary.is_symlink() or not binary.is_file():
            continue
        argv = [str(binary), *args]
        files = {}
        for path in (executable, binary):
            with path.open("rb") as source:
                files[str(path)] = hashlib.file_digest(source, "sha256").hexdigest()
        commands.append(
            {
                "service_id": service,
                "argv": argv,
                "parent_service": None,
                "host_argv": host["argv"],
                "config_home": home,
                "contract_sha256": digest([policy_digest, host["argv"], argv, files]),
            }
        )
    return commands


def service_contracts(processes: dict[int, Process]) -> list[dict]:
    estate = load_estate()
    policy, policy_digest = estate.load_policy(estate.policy_path())
    settings = policy.get("process_ownership", {})
    if settings.get("schema") != "domus.process_contracts.v1":
        return []  # Missing authority cannot exempt any process.
    hosts = settings.get("hosts", [])
    contracts = []
    hashes = {}
    singleton_candidates = []
    homes = {p.env["CODEX_HOME"] for p in processes.values() if p.env.get("CODEX_HOME")}
    if not homes:
        homes.add(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    host_bin = str(Path.home() / "Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost")
    for home in sorted(homes):
        resolved_hosts = []
        for host in hosts:
            if "runtime_relative" in host:
                executable = Path(home) / host["runtime_relative"]
                if executable.is_file():
                    resolved_hosts.append({**host, "argv": [str(executable.resolve()), *host["args"]]})
            else:
                resolved_hosts.append(host)
        records, issues, _, configs = estate.inventory(policy, config_paths=[("codex", Path(home) / "config.toml")])
        ambiguous = {row["client"] for row in issues if row["reason"] == "ambiguous_registration"}
        if "codex" in ambiguous or not any(row["state"] == "valid" for row in configs):
            continue
        for host in resolved_hosts:
            if host.get("client") == "codex":
                contracts.extend(_native_helper_contracts(host, home, policy_digest))
        for record in records:
            spec, authority = record.get("spec"), record.get("policy")
            if (
                not authority
                or not spec
                or not record["active"]
                or spec["invalid"]
                or spec["disabled"]
                or not spec["command"]
            ):
                continue
            argv = [spec["command"], *spec["args"]]
            byte_witnesses: dict[str, str] = {}
            commands = [(argv, None)]
            if Path(argv[0]).name == "domus-agent-host" and argv[1:3] == ["ensure", "--"]:
                argv = argv[3:]
                commands.append(([host_bin, "run", "--", *argv], None))
                commands.append((argv, record["service"]))
                companion = str(Path.home() / ".local/bin/domus-process-ownership")
                commands.append(([host_bin, "run", "--", companion, "exec", "--", *argv], None))
                commands.append(
                    ([shutil.which("python3") or "python3", companion, "exec", "--", *argv], record["service"])
                )
            kind = authority.get("process_contract", {}).get("bootstrap")
            if kind == "npm" and Path(argv[0]).name == "npx" and len(argv) >= 3 and argv[1] == "-y":
                package, args = argv[2], argv[3:]
                # The declared npx script and the actual npm process-title representation.
                commands.append((["node", str(Path(argv[0]).resolve()), *argv[1:]], record["service"]))
                commands.append((["npm", "exec", package, *args], record["service"]))
                for process in processes.values():
                    if len(process.argv) < 2 or Path(process.argv[0]).name not in {"node", "npm"}:
                        continue
                    script = Path(process.argv[1])
                    if not script.exists() or list(process.argv[2:]) != args:
                        continue
                    for parent in script.resolve().parents:
                        manifest = parent / "package.json"
                        if manifest.is_file():
                            if json.loads(manifest.read_text()).get("name") == package:
                                commands.append((list(process.argv), record["service"]))
                            break
            elif kind == "uv" and Path(argv[0]).name == "uvx":
                commands.append(([str(Path(argv[0]).with_name("uv")), "tool", "uvx", *argv[1:]], record["service"]))
                if "--from" in argv:
                    source = argv[argv.index("--from") + 1]
                    tail = argv[argv.index("--from") + 2 :]
                    for process in processes.values():
                        if len(process.argv) < 2 or list(process.argv[2:]) != tail[1:]:
                            continue
                        script = Path(process.argv[1])
                        if script.name != tail[0] or not script.is_file():
                            continue
                        environment = script.parent.parent
                        for direct in environment.glob("lib/python*/site-packages/*.dist-info/direct_url.json"):
                            metadata = json.loads(direct.read_text())
                            vcs = metadata.get("vcs_info", {})
                            expected = "git+" + metadata.get("url", "") + "@" + vcs.get("commit_id", "")
                            if source == expected:
                                commands.append((list(process.argv), record["service"]))
                                if (
                                    record["service"] == "serena"
                                    and authority.get("process_contract", {}).get("detached_helper")
                                    == "serena-tray-manager"
                                    and re.fullmatch(r"git\+https://github\.com/oraios/serena@[a-f0-9]{40}", source)
                                ):
                                    singleton_candidates.append((process, direct, home))
            elif kind == "capability":
                name = authority["process_contract"]["capability"]
                commands.extend((command, record["service"]) for command in _capability_commands(name))
            elif kind == "exec-wrapper":
                # Explicit delegation belongs to the existing source-owned service contract.
                command = authority["process_contract"]["executable"]
                commands.append(([command, *argv[1:]], None))
            # App-owned CUA's node_repl is an explicit declared helper, not every child.
            if kind == "cua" and isinstance(spec.get("env"), dict):
                helper = spec["env"].get("CUA_REPL_NODE_REPL_PATH")
                if helper:
                    commands.append(([helper], record["service"]))
                    commands.extend(
                        (command, record["service"])
                        for command in _cua_embedded_commands(Path(helper), processes, resolved_hosts, byte_witnesses)
                    )
            for command, parent_service in commands:
                files = [Path(word).resolve() for word in command if Path(word).is_absolute() and Path(word).is_file()]
                if byte_witnesses and helper:
                    files.append(Path(helper).resolve())
                file_digests = {}
                for path in files:
                    key = str(path)
                    if key not in hashes:
                        with path.open("rb") as source:
                            hashes[key] = hashlib.file_digest(source, "sha256").hexdigest()
                    file_digests[key] = hashes[key]
                provenance = digest([policy_digest, record["fingerprint"], canonical_argv(command), file_digests])
                if any(
                    key in byte_witnesses and checksum != byte_witnesses[key] for key, checksum in file_digests.items()
                ):
                    continue  # Captured vendor bytes changed during contract derivation.
                for host in resolved_hosts:
                    if host.get("client") != record["client"]:
                        continue
                    contracts.append(
                        {
                            "service_id": record["service"],
                            "argv": command,
                            "parent_service": parent_service,
                            "host_argv": host["argv"],
                            "config_home": home,
                            "contract_sha256": provenance,
                        }
                    )
    contracts.extend(_serena_singleton_contracts(processes, contracts, singleton_candidates))
    contracts.extend(_responsible_host_contracts(processes, contracts, settings, policy_digest))
    return contracts


def _responsible_host_contracts(processes, contracts, settings, policy_digest):
    from limen.process_lifetime import find_lifetime_descriptors, signed_responsible_host
    from limen.process_singletons import vendor_files_unchanged

    authority = settings.get("responsible_host", {})
    if (
        authority.get("client") != "codex"
        or authority.get("launch_prefix") != ["run", "--"]
        or authority.get("lifetime_contract") != "pipe-handle-device-inode"
        or authority.get("peer_service_ids") != ["codex/code-mode-host"]
        or authority.get("require_signed_deployment") is not True
        or not isinstance(authority.get("descriptor_limit"), int)
        or not 1 <= authority["descriptor_limit"] <= 128
        or not isinstance(authority.get("executable"), str)
    ):
        return []
    executable = Path(authority["executable"])
    files = signed_responsible_host(executable)
    if not files:
        return []
    launcher = Path.home() / ".local/libexec/domus-agent-runtime.py"
    if launcher.is_symlink() or not launcher.is_file() or launcher.stat().st_size > 2 * 1024 * 1024:
        return []
    files[str(launcher)] = hashlib.sha256(launcher.read_bytes()).hexdigest()
    result = []
    for host in processes.values():
        if (
            not host.started
            or not host.readable
            or len(host.argv) < 9
            or host.argv[:3] != (str(executable), "run", "--")
            or Path(host.argv[4]).resolve() != launcher.resolve()
            or host.argv[5:9] != ("exec", "codex", "--", "codex")
        ):
            continue
        interpreter = Path(host.argv[3]).resolve()
        if (
            not interpreter.is_file()
            or not interpreter.name.lower().startswith("python")
            or interpreter.stat().st_size > 32 * 1024 * 1024
        ):
            continue
        captured = {**files, str(interpreter): hashlib.sha256(interpreter.read_bytes()).hexdigest()}
        for contract in contracts:
            if contract["service_id"] != "codex/code-mode-host":
                continue
            for peer in processes.values():
                if (
                    peer.uid != host.uid
                    or not peer.started
                    or not peer.readable
                    or canonical_argv(peer.argv) != canonical_argv(contract["argv"])
                ):
                    continue
                try:
                    pair = find_lifetime_descriptors(host.pid, peer.pid, host.uid, authority["descriptor_limit"])
                except (OSError, ValueError):
                    continue  # Kernel census failure cannot grant ownership.
                if pair is None or not vendor_files_unchanged(captured):
                    continue
                binding = {
                    "pid": peer.pid,
                    "identity": peer.started,
                    "argv": list(peer.argv),
                    "contract_sha256": contract["contract_sha256"],
                }
                result.append(
                    {
                        "service_id": "codex/responsible-host",
                        "argv": list(host.argv),
                        "host_argv": contract["host_argv"],
                        "config_home": contract.get("config_home"),
                        "singleton_peer": binding,
                        "singleton_pid": host.pid,
                        "singleton_identity": host.started,
                        "singleton_vendor_files": captured,
                        "lifetime_fds": list(pair),
                        "contract_sha256": digest(
                            [policy_digest, list(host.argv), host.pid, host.started, binding, list(pair), captured]
                        ),
                    }
                )
    return result


def _serena_singleton_contracts(processes, contracts, candidates):
    """Bind an explicit singleton candidate to one pinned backend contract.

    Candidate generation does not assert that the peer is shared. The assessor
    must classify that exact peer before using this detached contract.
    """
    from limen.process_singletons import SERENA_TRAY_COMMAND

    result = []
    for peer, metadata, home in candidates:
        environment = Path(peer.argv[1]).parent.parent
        package = metadata.parent.parent / "serena"
        dashboard, constants = package / "dashboard.py", package / "constants.py"
        files = (metadata, dashboard, constants, Path(peer.argv[1]), Path(peer.argv[0]).resolve())
        if any(
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size > (32 if index == len(files) - 1 else 2) * 1024 * 1024
            for index, path in enumerate(files)
        ):
            continue
        captured = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        source = dashboard.read_text()
        if (
            SERENA_TRAY_COMMAND not in source
            or 'HOST = "127.0.0.1"' not in source
            or "PORT = SerenaPorts.TRAY_MANAGER_PORT" not in source
            or "TRAY_MANAGER_PORT = 0x5EA0" not in constants.read_text()
        ):
            continue
        argv = (str(environment / "bin/python"), "-c", SERENA_TRAY_COMMAND)
        if peer.argv[0] != argv[0]:
            continue  # Canonical Python alone can alias another uv environment.
        for tray in processes.values():
            if tray.argv != argv or tray.uid != peer.uid or not tray.started or not peer.started:
                continue
            for contract in contracts:
                if (
                    contract["service_id"] != "serena"
                    or tuple(contract["argv"]) != peer.argv
                    or contract.get("config_home") != home
                ):
                    continue
                if any(
                    hashlib.sha256(path.read_bytes()).hexdigest() != captured[str(path.resolve())] for path in files
                ):
                    continue
                binding = {
                    "pid": peer.pid,
                    "identity": peer.started,
                    "argv": list(peer.argv),
                    "contract_sha256": contract["contract_sha256"],
                }
                result.append(
                    {
                        "service_id": "serena/tray-manager",
                        "argv": list(argv),
                        "host_argv": contract["host_argv"],
                        "config_home": home,
                        "parent_service": None,
                        "singleton_peer": binding,
                        "singleton_pid": tray.pid,
                        "singleton_identity": tray.started,
                        "singleton_vendor_files": captured,
                        "contract_sha256": digest(
                            [contract["contract_sha256"], binding, tray.pid, tray.started, list(argv), captured]
                        ),
                    }
                )
    return result
