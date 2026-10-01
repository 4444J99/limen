"""Derive individual transport contracts from Domus's existing MCP authority."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
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


def service_contracts(processes: dict[int, Process]) -> list[dict]:
    estate = load_estate()
    policy, policy_digest = estate.load_policy(estate.policy_path())
    settings = policy.get("process_ownership", {})
    if settings.get("schema") != "domus.process_contracts.v1":
        return []  # Missing authority cannot exempt any process.
    hosts = settings.get("hosts", [])
    contracts = []
    hashes = {}
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
            for command, parent_service in commands:
                files = [Path(word).resolve() for word in command if Path(word).is_absolute() and Path(word).is_file()]
                file_digests = {}
                for path in files:
                    key = str(path)
                    if key not in hashes:
                        with path.open("rb") as source:
                            hashes[key] = hashlib.file_digest(source, "sha256").hexdigest()
                    file_digests[key] = hashes[key]
                provenance = digest([policy_digest, record["fingerprint"], canonical_argv(command), file_digests])
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
    return contracts
