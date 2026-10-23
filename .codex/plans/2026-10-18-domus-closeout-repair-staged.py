#!/usr/bin/env python3
"""Staged Domus repair. Preview by default; never applies dotfiles or deletes worktrees."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import difflib
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

TARGET = Path("/Users/4jp/Workspace/domus-genoma/.worktrees/codex-doctor-heal-20261017")
BASE = "8498484e512fa8c20c575af48d1b029fb8f612db"
BRANCH = "fix/closeout-discovery-heal-20261018"
PRESERVED = "docs/codex-doctor-acceptance-20261017"
PRESERVED_SHA = "2722a33bd967a3a5d5836ff892feca6a94394ff7"
REPO = "4444J99/domus-genoma-private"
PLAN = ".codex/plans/2026-10-18-closeout-discovery-heal.md"
LIMEN = Path("/Users/4jp/Workspace/limen")
DATA = json.loads("{\"edits\":{\"tests/check_closeout_discovery.py\":[[\"import sys\\n\",\"import sys\\n\\nfrom closeout_discovery_support import (\\n    DiscoveryError, codex_observations, opencode_discovery,\\n    provider_readiness, resolve_limen,\\n)\\n\"],[\"def main() -> None:\",\"def main(argv: list[str] | None = None) -> int:\"],[\"    args = parser.parse_args()\\n\",\"    parser.add_argument(\\\"--limen-provider\\\", action=\\\"store_true\\\", help=\\\"Also measure Limen-provider readiness\\\")\\n    args = parser.parse_args(argv)\\n\"],[\"    assert installed.read_bytes() == rendered, \\\"deployed skill differs from Domus source\\\"\\n\",\"    if installed.read_bytes() != rendered:\\n        raise DiscoveryError(\\\"deployed skill differs from Domus source\\\")\\n\"],[\"    command = [str(Path.home() / \\\".local/bin/domus-limen-runtime\\\"), \\\"protocol-root\\\"]\\n    if os.environ.get(\\\"LIMEN_ROOT\\\"):\\n        command.extend([\\\"--checkout\\\", os.environ[\\\"LIMEN_ROOT\\\"]])\\n    resolved = json.loads(subprocess.run(command, capture_output=True, text=True,\\n                                         timeout=15, check=True).stdout)\\n    assert resolved[\\\"status\\\"] == \\\"ready\\\", \\\"closeout protocol is not ready\\\"\\n    limen = Path(resolved[\\\"protocol_root\\\"])\\n\",\"\"],[\"    if args.codex_only:\\n\",\"    if args.codex_only:\\n        resolved = resolve_limen()\\n        limen = Path(resolved[\\\"protocol_root\\\"])\\n\"],[\"                    assert len(result[\\\"data\\\"]) == len(locations), \\\"missing native skill groups\\\"\\n                    for group in result[\\\"data\\\"]:\\n                        matches = [s for s in group[\\\"skills\\\"] if s[\\\"name\\\"] == \\\"closeout\\\" and s[\\\"enabled\\\"]]\\n                        assert len(matches) == 1 and Path(matches[0][\\\"path\\\"]).resolve() == installed.resolve(), \\\"global skill not discovered\\\"\\n                        observations.append({\\\"cwd\\\": group[\\\"cwd\\\"], \\\"skill\\\": str(installed), \\\"status\\\": \\\"PASS\\\"})\\n\",\"                    observations.extend(codex_observations(result, locations, installed))\\n\"],[\"        print(json.dumps({\\\"status\\\": \\\"PASS\\\", \\\"codex_native_discovery\\\": observations, \\\"model_turns\\\": 0}, indent=2))\\n        return\\n\",\"        print(json.dumps({\\n            \\\"status\\\": \\\"PASS\\\", \\\"generic_discovery\\\": \\\"PASS\\\",\\n            \\\"codex_native_discovery\\\": observations, \\\"model_turns\\\": 0,\\n            \\\"limen_provider\\\": ({**resolved, \\\"status\\\": \\\"READY\\\"} if args.limen_provider\\n                               else {\\\"status\\\": \\\"NOT_REQUESTED\\\"}),\\n        }, indent=2))\\n        return 0\\n\"],[\"    for cwd in locations:\\n        result = subprocess.run(\\n            [str(wrapper), \\\"exec\\\", \\\"opencode\\\", \\\"--\\\", \\\"opencode\\\", \\\"debug\\\", \\\"skill\\\"],\\n            cwd=cwd, capture_output=True, text=True, timeout=30, check=True,\\n        )\\n        skills = json.loads(result.stdout)\\n        matches = [row for row in skills if row.get(\\\"name\\\") == \\\"closeout\\\"]\\n        assert len(matches) == 1, f\\\"expected one closeout skill from {cwd}\\\"\\n        assert Path(matches[0][\\\"location\\\"]).resolve() == installed.resolve(), f\\\"wrong skill from {cwd}\\\"\\n        observations.append({\\\"cwd\\\": str(cwd), \\\"skill\\\": str(installed), \\\"status\\\": \\\"PASS\\\"})\\n\",\"    for cwd in locations:\\n        observations.append(opencode_discovery(wrapper, cwd, installed))\\n    provider = provider_readiness(args.limen_provider)\\n    ready = provider[\\\"status\\\"] in {\\\"READY\\\", \\\"NOT_REQUESTED\\\"}\\n\"],[\"        \\\"status\\\": \\\"PASS\\\",\\n        \\\"rendered_sha256\\\": hashlib.sha256(rendered).hexdigest(),\\n        \\\"canonical_skill\\\": str(limen / \\\".agents/skills/closeout/SKILL.md\\\"),\\n\",\"        \\\"status\\\": \\\"PASS\\\" if ready else \\\"UNMEASURED\\\",\\n        \\\"generic_discovery\\\": \\\"PASS\\\",\\n        \\\"rendered_sha256\\\": hashlib.sha256(rendered).hexdigest(),\\n        \\\"installed_skill\\\": str(installed),\\n        \\\"limen_provider\\\": provider,\\n\"],[\"    }, indent=2))\\n\\n\\nif __name__ == \\\"__main__\\\":\\n    main()\\n\",\"    }, indent=2))\\n    return 0 if ready else 77\\n\\n\\ndef cli(argv: list[str] | None = None) -> int:\\n    try:\\n        return main(argv)\\n    except (DiscoveryError, OSError, ImportError,\\n            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:\\n        unmeasured = not isinstance(exc, DiscoveryError) or exc.unmeasured\\n        print(json.dumps({\\n            \\\"status\\\": \\\"UNMEASURED\\\" if unmeasured else \\\"FAIL\\\",\\n            \\\"reason\\\": str(exc), \\\"model_turns\\\": 0,\\n        }))\\n        return 77 if unmeasured else 1\\n\\n\\nif __name__ == \\\"__main__\\\":\\n    raise SystemExit(cli())\\n\"]],\"dot_agents/skills/closeout/SKILL.md.tmpl\":[[\"   `.agents/skills/closeout/SKILL.md` in the repo (when it is not this skill) →\\n   `.claude/skills/closeout/SKILL.md` → a Closeout section in the repo's `AGENTS.md` or\\n\",\"   `.agents/skills/closeout/SKILL.md` → `.codex/skills/closeout/SKILL.md` →\\n   `.claude/skills/closeout/SKILL.md` → a Closeout section in the repo's `AGENTS.md` or\\n\"],[\"   predicate. With none, the floor in this contract stands alone.\\n\",\"   predicate. Skip only the invoked entry itself or a byte-identical generic copy;\\n   similar wording, a familiar name, or another agent's directory does not justify a skip.\\n   With no repository predicate, delegate the bundled canonical helper below.\\n\"],[\"   tracker, or one explicit `BLOCKED: <atom>` stated once. \\\"On disk\\\" is not a form.\\n\",\"   tracker, or one explicit `BLOCKED: <atom>` stated once and filed in an existing\\n   remote owner with responsibility and a next condition. A local plan must be committed\\n   and pushed. A blocker statement alone and \\\"on disk\\\" are not durable forms.\\n\"],[\"5. **Status words are evidence-bound and reported separately.** *merged*: the commit is an\\n   ancestor of the fetched default branch. *live*: the running checkout or installed\\n\",\"5. **Status words are evidence-bound and reported separately.** *merged*: verify the\\n   remote PR is merged and its actual merge or squash commit is an ancestor of the fetched\\n   default branch. Do not require the original topic SHA to survive a squash. *live*:\\n   the running checkout or installed\\n\"],[\"Detailed procedure, inventory commands, and the opt-in ORGANVM plan-ledger overlay live in\\nthe `closeout` skill from the ai-skills distribution when it is installed. The contract\\nabove is sufficient without it.\\n\",\"Detailed procedure and the opt-in ORGANVM plan-ledger overlay live in the canonical\\n`closeout` skill from the ai-skills distribution. When no repository predicate exists,\\ndelegate its bundled helper at\\n`{{ .chezmoi.homeDir }}/.local/share/ai-skills/current/distributions/claude/skills/closeout/scripts/closeout_check.py`.\\nRun `inventory --evidence PATH` to collect the session record and\\n`check --evidence PATH --twice` to verify closure and the fixed point. Follow the\\ncanonical skill's evidence schema; successful inventory collection is not closure.\\nIf the helper or canonical skill is missing, record an explicit `UNMEASURED` result\\nwith its existing remote owner. Do not substitute a local fallback inventory or claim\\nthe terminal fixed point without an executable predicate.\\n\"]],\"dot_local/bin/executable_domus-limen-runtime\":[[\"        source = Path(args.checkout).expanduser().resolve(strict=True)\\n\",\"        try:\\n            source = Path(args.checkout).expanduser().resolve(strict=True)\\n        except (OSError, RuntimeError) as exc:\\n            raise InstallError(f\\\"explicit closeout checkout is unavailable: {args.checkout}\\\") from exc\\n        if not source.is_dir():\\n            raise InstallError(f\\\"explicit closeout checkout is not a directory: {source}\\\")\\n\"]],\"tests/test_closeout_protocol_bundle.py\":[[\"def test_protocol_symlink_cannot_escape_bundle(tmp_path):\\n    runtime = tmp_path / \\\"runtime\\\"\\n    _protocol_fixture(runtime)\\n    target = runtime / \\\"source/AGENTS.md\\\"\\n    target.unlink()\\n    target.symlink_to(Path(__file__))\\n    with pytest.raises(module.InstallError, match=\\\"unsafe\\\"):\\n        module._closeout_protocol_digest(runtime)\\n\",\"def test_protocol_symlink_cannot_escape_bundle(tmp_path):\\n    runtime = tmp_path / \\\"runtime\\\"\\n    _protocol_fixture(runtime)\\n    target = runtime / \\\"source/AGENTS.md\\\"\\n    target.unlink()\\n    target.symlink_to(Path(__file__))\\n    with pytest.raises(module.InstallError, match=\\\"unsafe\\\"):\\n        module._closeout_protocol_digest(runtime)\\n\\n\\n@pytest.mark.parametrize(\\\"kind\\\", [\\\"missing\\\", \\\"file\\\"])\\ndef test_explicit_override_bad_path_is_structured(tmp_path, capsys, kind):\\n    checkout = tmp_path / kind\\n    if kind == \\\"file\\\":\\n        checkout.write_text(\\\"not a checkout\\\\n\\\")\\n    result = module.main([\\\"protocol-root\\\", \\\"--checkout\\\", str(checkout)])\\n    captured = capsys.readouterr()\\n    assert result == 1\\n    payload = json.loads(captured.out)\\n    assert payload[\\\"status\\\"] == \\\"blocked\\\"\\n    assert \\\"explicit closeout checkout\\\" in payload[\\\"error\\\"]\\n    assert \\\"Traceback\\\" not in captured.out + captured.err\\n\"]]},\"newFiles\":{\"tests/closeout_discovery_support.py\":\"\\\"\\\"\\\"Bounded native closeout discovery; inventory is independent of provider readiness.\\\"\\\"\\\"\\nfrom __future__ import annotations\\n\\nimport json\\nimport os\\nfrom pathlib import Path\\nimport subprocess\\n\\n\\nclass DiscoveryError(RuntimeError):\\n    \\\"\\\"\\\"A measured discovery defect or unavailable observation.\\\"\\\"\\\"\\n\\n    def __init__(self, message: str, *, unmeasured: bool = False):\\n        super().__init__(message)\\n        self.unmeasured = unmeasured\\n\\n\\ndef run_json(command: list[str], *, cwd: Path | None = None, timeout: int = 30):\\n    try:\\n        result = subprocess.run(\\n            command, cwd=cwd, capture_output=True, text=True,\\n            timeout=timeout, check=True,\\n        )\\n    except (OSError, subprocess.TimeoutExpired) as exc:\\n        raise DiscoveryError(f\\\"native observation unavailable: {exc}\\\", unmeasured=True) from exc\\n    except subprocess.CalledProcessError as exc:\\n        detail = str(exc.stderr or exc.stdout or \\\"\\\").strip()[:800]\\n        raise DiscoveryError(f\\\"native observation failed: {detail}\\\", unmeasured=True) from exc\\n    try:\\n        return json.loads(result.stdout)\\n    except (TypeError, json.JSONDecodeError) as exc:\\n        raise DiscoveryError(\\\"native observation returned invalid JSON\\\") from exc\\n\\n\\ndef resolve_limen() -> dict:\\n    command = [str(Path.home() / \\\".local/bin/domus-limen-runtime\\\"), \\\"protocol-root\\\"]\\n    if os.environ.get(\\\"LIMEN_ROOT\\\"):\\n        command.extend([\\\"--checkout\\\", os.environ[\\\"LIMEN_ROOT\\\"]])\\n    result = run_json(command, timeout=15)\\n    if not isinstance(result, dict) or result.get(\\\"status\\\") != \\\"ready\\\":\\n        raise DiscoveryError(\\\"Limen provider protocol is not ready\\\", unmeasured=True)\\n    root = result.get(\\\"protocol_root\\\")\\n    if not isinstance(root, str) or not Path(root).is_dir():\\n        raise DiscoveryError(\\\"Limen provider returned an unavailable protocol root\\\", unmeasured=True)\\n    return result\\n\\n\\ndef provider_readiness(requested: bool) -> dict:\\n    if not requested:\\n        return {\\\"status\\\": \\\"NOT_REQUESTED\\\"}\\n    try:\\n        return {**resolve_limen(), \\\"status\\\": \\\"READY\\\"}\\n    except DiscoveryError as exc:\\n        return {\\\"status\\\": \\\"UNMEASURED\\\", \\\"reason\\\": str(exc)}\\n\\n\\ndef opencode_discovery(wrapper: Path, cwd: Path, installed: Path) -> dict:\\n    # V2 reports the actual location. Do not trust a directory query alone:\\n    # the observed CLI ignored it and returned the caller's current directory.\\n    result = run_json(\\n        [str(wrapper), \\\"exec\\\", \\\"opencode\\\", \\\"--\\\", \\\"opencode\\\", \\\"api\\\",\\n         \\\"--standalone\\\", \\\"skill.list\\\", \\\"--param\\\", f\\\"directory={cwd}\\\"],\\n        cwd=cwd, timeout=30,\\n    )\\n    location = result.get(\\\"location\\\") if isinstance(result, dict) else None\\n    actual = location.get(\\\"directory\\\") if isinstance(location, dict) else None\\n    if not isinstance(actual, str) or Path(actual).resolve() != cwd.resolve():\\n        raise DiscoveryError(f\\\"OpenCode directory mismatch: requested {cwd}, observed {actual}\\\")\\n    skills = result.get(\\\"data\\\")\\n    if not isinstance(skills, list):\\n        raise DiscoveryError(\\\"OpenCode skill.list returned no skill array\\\")\\n    matches = [row for row in skills if isinstance(row, dict) and row.get(\\\"name\\\") == \\\"closeout\\\"]\\n    if len(matches) != 1:\\n        raise DiscoveryError(f\\\"expected one closeout skill from {cwd}; observed {len(matches)}\\\")\\n    location = matches[0].get(\\\"location\\\")\\n    if not isinstance(location, str) or Path(location).resolve() != installed.resolve():\\n        raise DiscoveryError(f\\\"wrong closeout skill path from {cwd}: {location}\\\")\\n    return {\\\"cwd\\\": str(cwd), \\\"skill\\\": str(installed), \\\"status\\\": \\\"PASS\\\"}\\n\\n\\ndef codex_observations(result: dict, locations: list[Path], installed: Path) -> list[dict]:\\n    groups = result.get(\\\"data\\\") if isinstance(result, dict) else None\\n    expected = {str(path.resolve()) for path in locations}\\n    if not isinstance(groups, list) or len(groups) != len(expected):\\n        raise DiscoveryError(\\\"missing native Codex skill groups\\\")\\n    seen = set()\\n    observations = []\\n    for group in groups:\\n        raw_cwd = group.get(\\\"cwd\\\") if isinstance(group, dict) else None\\n        if not isinstance(raw_cwd, str):\\n            raise DiscoveryError(\\\"Codex returned a group without a directory\\\")\\n        cwd = str(Path(raw_cwd).resolve())\\n        if cwd not in expected or cwd in seen:\\n            raise DiscoveryError(f\\\"unexpected or duplicate Codex directory: {raw_cwd}\\\")\\n        seen.add(cwd)\\n        skills = group.get(\\\"skills\\\")\\n        if group.get(\\\"errors\\\") or not isinstance(skills, list):\\n            raise DiscoveryError(f\\\"Codex catalog is incomplete from {raw_cwd}\\\")\\n        matches = [\\n            row for row in skills\\n            if isinstance(row, dict) and row.get(\\\"name\\\") == \\\"closeout\\\" and row.get(\\\"enabled\\\")\\n        ]\\n        if len(matches) != 1:\\n            raise DiscoveryError(f\\\"expected one enabled Codex closeout skill from {raw_cwd}\\\")\\n        path = matches[0].get(\\\"path\\\")\\n        if not isinstance(path, str) or Path(path).resolve() != installed.resolve():\\n            raise DiscoveryError(f\\\"wrong Codex closeout skill path from {raw_cwd}: {path}\\\")\\n        observations.append({\\\"cwd\\\": raw_cwd, \\\"skill\\\": str(installed), \\\"status\\\": \\\"PASS\\\"})\\n    return observations\\n\",\"tests/test_closeout_discovery.py\":\"\\\"\\\"\\\"Exercise discovery behavior without provider/model turns or host mutation.\\\"\\\"\\\"\\nfrom __future__ import annotations\\n\\nimport importlib.util\\nimport json\\nfrom pathlib import Path\\nimport subprocess\\nfrom types import SimpleNamespace\\n\\nimport pytest\\n\\nSCRIPT = Path(__file__).with_name(\\\"check_closeout_discovery.py\\\")\\n\\n\\ndef _load():\\n    spec = importlib.util.spec_from_file_location(\\\"closeout_discovery_check\\\", SCRIPT)\\n    module = importlib.util.module_from_spec(spec)\\n    spec.loader.exec_module(module)\\n    return module\\n\\n\\ndef _environment(tmp_path, monkeypatch, *, reply=None, fail_provider=False):\\n    module = _load()\\n    home = tmp_path / \\\"home\\\"\\n    installed = home / \\\".agents/skills/closeout/SKILL.md\\\"\\n    installed.parent.mkdir(parents=True)\\n    installed.write_text(\\\"rendered skill\\\\n\\\")\\n    monkeypatch.setattr(Path, \\\"home\\\", classmethod(lambda cls: home))\\n    calls = []\\n\\n    def run(command, **kwargs):\\n        calls.append((command, kwargs))\\n        if command[0] == \\\"chezmoi\\\":\\n            return SimpleNamespace(stdout=installed.read_bytes())\\n        if command[0].endswith(\\\"domus-limen-runtime\\\"):\\n            if fail_provider:\\n                raise subprocess.CalledProcessError(1, command, stderr=\\\"invalid explicit checkout\\\")\\n            pytest.fail(\\\"generic discovery must not resolve Limen\\\")\\n        assert command[1:8] == [\\n            \\\"exec\\\", \\\"opencode\\\", \\\"--\\\", \\\"opencode\\\", \\\"api\\\", \\\"--standalone\\\", \\\"skill.list\\\"\\n        ], \\\"discovery must use OpenCode V2 skill.list\\\"\\n        assert kwargs[\\\"timeout\\\"] == 30\\n        assert kwargs[\\\"check\\\"] is True\\n        cwd = kwargs[\\\"cwd\\\"]\\n        payload = {\\\"location\\\": {\\\"directory\\\": str(cwd)},\\n                   \\\"data\\\": [{\\\"name\\\": \\\"closeout\\\", \\\"location\\\": str(installed)}]}\\n        if reply is not None:\\n            payload = reply(payload)\\n        return SimpleNamespace(stdout=json.dumps(payload))\\n\\n    monkeypatch.setattr(module.subprocess, \\\"run\\\", run)\\n    return module, calls, installed\\n\\n\\ndef test_generic_discovery_without_limen(tmp_path, monkeypatch, capsys):\\n    module, calls, _ = _environment(tmp_path, monkeypatch)\\n    monkeypatch.setenv(\\\"LIMEN_ROOT\\\", str(tmp_path / \\\"missing\\\"))\\n    assert module.main([]) == 0\\n    payload = json.loads(capsys.readouterr().out)\\n    assert payload[\\\"generic_discovery\\\"] == \\\"PASS\\\"\\n    assert payload[\\\"limen_provider\\\"] == {\\\"status\\\": \\\"NOT_REQUESTED\\\"}\\n    assert len(payload[\\\"opencode_native_discovery\\\"]) == 3\\n    assert payload[\\\"model_turns\\\"] == 0\\n    assert not any(\\\"protocol-root\\\" in command for command, _ in calls)\\n\\n\\n@pytest.mark.parametrize(\\n    \\\"reply,reason\\\",\\n    [\\n        (lambda p: {**p, \\\"location\\\": {\\\"directory\\\": \\\"/unexpected\\\"}}, \\\"directory mismatch\\\"),\\n        (lambda p: {**p, \\\"data\\\": []}, \\\"expected one closeout\\\"),\\n        (lambda p: {**p, \\\"data\\\": p[\\\"data\\\"] * 2}, \\\"expected one closeout\\\"),\\n        (lambda p: {**p, \\\"data\\\": [{\\\"name\\\": \\\"closeout\\\", \\\"location\\\": \\\"/wrong\\\"}]}, \\\"wrong closeout\\\"),\\n        (lambda p: {**p, \\\"data\\\": None}, \\\"no skill array\\\"),\\n    ],\\n)\\ndef test_opencode_rejects_wrong_catalog(tmp_path, monkeypatch, capsys, reply, reason):\\n    module, _, _ = _environment(tmp_path, monkeypatch, reply=reply)\\n    assert module.cli([]) == 1\\n    payload = json.loads(capsys.readouterr().out)\\n    assert payload[\\\"status\\\"] == \\\"FAIL\\\"\\n    assert reason in payload[\\\"reason\\\"]\\n\\n\\ndef test_requested_limen_failure_keeps_generic_observation(tmp_path, monkeypatch, capsys):\\n    module, _, _ = _environment(tmp_path, monkeypatch, fail_provider=True)\\n    assert module.main([\\\"--limen-provider\\\"]) == 77\\n    payload = json.loads(capsys.readouterr().out)\\n    assert payload[\\\"generic_discovery\\\"] == \\\"PASS\\\"\\n    assert payload[\\\"limen_provider\\\"][\\\"status\\\"] == \\\"UNMEASURED\\\"\\n    assert \\\"invalid explicit checkout\\\" in payload[\\\"limen_provider\\\"][\\\"reason\\\"]\\n\\n\\ndef test_source_drift_is_clear(tmp_path, monkeypatch, capsys):\\n    module, _, installed = _environment(tmp_path, monkeypatch)\\n    original = module.subprocess.run\\n\\n    def run(command, **kwargs):\\n        if command[0] == \\\"chezmoi\\\":\\n            return SimpleNamespace(stdout=b\\\"different source\\\\n\\\")\\n        return original(command, **kwargs)\\n\\n    monkeypatch.setattr(module.subprocess, \\\"run\\\", run)\\n    assert module.cli([]) == 1\\n    assert \\\"differs from Domus source\\\" in json.loads(capsys.readouterr().out)[\\\"reason\\\"]\\n    assert installed.read_text() == \\\"rendered skill\\\\n\\\"\\n\\n\\ndef test_timeout_is_unmeasured(tmp_path, monkeypatch, capsys):\\n    module, _, _ = _environment(tmp_path, monkeypatch)\\n    original = module.subprocess.run\\n\\n    def run(command, **kwargs):\\n        if command[0] != \\\"chezmoi\\\":\\n            raise subprocess.TimeoutExpired(command, kwargs[\\\"timeout\\\"])\\n        return original(command, **kwargs)\\n\\n    monkeypatch.setattr(module.subprocess, \\\"run\\\", run)\\n    assert module.cli([]) == 77\\n    assert json.loads(capsys.readouterr().out)[\\\"status\\\"] == \\\"UNMEASURED\\\"\\n\\n\\ndef test_codex_catalog_requires_exact_directories(tmp_path):\\n    from closeout_discovery_support import DiscoveryError, codex_observations\\n\\n    installed = tmp_path / \\\"SKILL.md\\\"\\n    locations = [tmp_path / \\\"a\\\", tmp_path / \\\"b\\\"]\\n    rows = [{\\\"cwd\\\": str(path), \\\"skills\\\": [\\n        {\\\"name\\\": \\\"closeout\\\", \\\"enabled\\\": True, \\\"path\\\": str(installed)}\\n    ]} for path in locations]\\n    assert len(codex_observations({\\\"data\\\": rows}, locations, installed)) == 2\\n    with pytest.raises(DiscoveryError, match=\\\"duplicate\\\"):\\n        codex_observations({\\\"data\\\": [rows[0], rows[0]]}, locations, installed)\\n    rows[0][\\\"skills\\\"][0][\\\"path\\\"] = str(tmp_path / \\\"wrong\\\")\\n    with pytest.raises(DiscoveryError, match=\\\"wrong Codex\\\"):\\n        codex_observations({\\\"data\\\": rows}, locations, installed)\\n\\n\\ndef test_codex_admission_denial_remains_zero_turns(tmp_path, monkeypatch, capsys):\\n    import sys\\n    import types\\n\\n    module, _, _ = _environment(tmp_path, monkeypatch)\\n\\n    class Denied(RuntimeError):\\n        pass\\n\\n    def hold(*args, **kwargs):\\n        raise Denied(\\\"lease denied\\\")\\n\\n    class Wire:\\n        def __init__(self, *args):\\n            pass\\n\\n        def start(self):\\n            pytest.fail(\\\"admission denial must precede native launch\\\")\\n\\n    package = types.ModuleType(\\\"limen\\\")\\n    package.__path__ = []\\n    admission = types.ModuleType(\\\"limen.host_admission\\\")\\n    admission.AdmissionDenied, admission.hold_lease = Denied, hold\\n    observer = types.ModuleType(\\\"mcp_native_observer\\\")\\n    observer.NativeWire = Wire\\n    monkeypatch.setitem(sys.modules, \\\"limen\\\", package)\\n    monkeypatch.setitem(sys.modules, \\\"limen.host_admission\\\", admission)\\n    monkeypatch.setitem(sys.modules, \\\"mcp_native_observer\\\", observer)\\n    monkeypatch.setattr(module, \\\"resolve_limen\\\", lambda: {\\n        \\\"status\\\": \\\"ready\\\", \\\"protocol_root\\\": str(tmp_path)\\n    })\\n    with pytest.raises(SystemExit) as exc:\\n        module.main([\\\"--codex-only\\\"])\\n    assert exc.value.code == 77\\n    assert json.loads(capsys.readouterr().out)[\\\"status\\\"] == \\\"BLOCKED\\\"\\n\"},\"plan\":\"# Repository-agnostic closeout discovery repair\\n\\nAuthorized continuation; dependency: a-i--skills plan commit fd38ddb.\\nOwners: Domus #505, Limen #2999/#2995. References do not close issues.\\n\\nRepair ordered .agents/.codex/.claude discovery, byte-identical entry exclusion,\\nremote blocker ownership, actual squash evidence, and canonical helper delegation.\\nUse managed OpenCode V2 skill.list with observed directory and path validation.\\nKeep Codex admission, deadlines and zero model turns. Separate generic discovery\\nfrom optional Limen readiness; invalid explicit roots return structured errors.\\n\\nPreserve the original Codex Doctor branch and every Claude checkout. Work only on\\nfix/closeout-discovery-heal-20261018, starting at fetched origin/main 8498484e.\\nDo not apply chezmoi from this feature checkout. Inventory is not closure.\\n\\nValidate failing invalid-root behavior first, then focused resolver/discovery/\\nprotocol tests and chezmoi rendering. Publish source and submit one exact head\\nthrough merge-drain, without polling. Live discovery awaits installation of the\\naccepted source; unavailable admission or helpers remain explicitly unmeasured.\\n\",\"rootTests\":\"\\n\\n@pytest.mark.parametrize(\\\"kind\\\", [\\\"missing\\\", \\\"file\\\"])\\ndef test_explicit_override_bad_path_is_structured(tmp_path, capsys, kind):\\n    checkout = tmp_path / kind\\n    if kind == \\\"file\\\":\\n        checkout.write_text(\\\"not a checkout\\\\n\\\")\\n    result = module.main([\\\"protocol-root\\\", \\\"--checkout\\\", str(checkout)])\\n    captured = capsys.readouterr()\\n    assert result == 1\\n    payload = json.loads(captured.out)\\n    assert payload[\\\"status\\\"] == \\\"blocked\\\"\\n    assert \\\"explicit closeout checkout\\\" in payload[\\\"error\\\"]\\n    assert \\\"Traceback\\\" not in captured.out + captured.err\\n\"}")


def run(command, *, cwd=TARGET, check=True, timeout=120):
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                          check=check, timeout=timeout)


def git(*args, check=True):
    return run(["git", *args], check=check, timeout=120)


def original(path):
    return git("show", f"{BASE}:{path}").stdout


def contents():
    outputs = {}
    for path, edits in DATA["edits"].items():
        text = original(path)
        for before, after in edits:
            if max(len(before.splitlines()), len(after.splitlines())) > 50:
                raise RuntimeError(f"refusing oversized targeted edit: {path}")
            if text.count(before) != 1:
                raise RuntimeError(f"patch anchor changed: {path}")
            text = text.replace(before, after, 1)
        outputs[path] = text
    outputs.update(DATA["newFiles"])
    outputs[PLAN] = DATA["plan"]
    for path, text in outputs.items():
        if path.endswith(".py") or path.endswith("executable_domus-limen-runtime"):
            compile(text, path, "exec")
    return outputs


def target_guard(expected_owner):
    if git("branch", "--show-current").stdout.strip() != BRANCH:
        raise RuntimeError("target branch changed; refusing mutation")
    if git("rev-parse", "HEAD").stdout.strip() != BASE:
        raise RuntimeError("target head changed; refusing mutation")
    if git("status", "--porcelain").stdout.strip():
        raise RuntimeError("target is dirty; refusing mutation")
    if git("rev-parse", f"refs/heads/{PRESERVED}").stdout.strip() != PRESERVED_SHA:
        raise RuntimeError("preserved branch changed; refusing mutation")
    process = run(["lsof", "-a", "-d", "cwd", "+D", str(TARGET)],
                  cwd=Path.home(), check=False, timeout=30)
    if process.stdout.strip():
        raise RuntimeError("target has an active cwd owner: " + process.stdout.strip())
    if process.returncode not in (0, 1):
        raise RuntimeError("could not establish target process inactivity")
    sys.path.insert(0, str(LIMEN / "cli/src"))
    from limen.host_admission import worktree_scope
    scope = worktree_scope(TARGET).lease_kind
    status = json.loads(run(
        [sys.executable, str(LIMEN / "scripts/host-work-admission.py"),
         "status", "--no-probe"], cwd=LIMEN, timeout=30,
    ).stdout)
    for lease in status.get("leases", []):
        if lease.get("kind") in {"execution", scope}:
            if not expected_owner or lease.get("owner") != expected_owner:
                raise RuntimeError("conflicting or unacknowledged writer lease: " + json.dumps(lease))


@contextmanager
def verification_lease():
    sys.path.insert(0, str(LIMEN / "cli/src"))
    from limen.host_admission import hold_lease
    with hold_lease("heavy", owner=f"domus-closeout-staged-{os.getpid()}",
                    surface="closeout-discovery-scoped-verification"):
        yield


def write_targeted(path, text):
    target = TARGET / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise RuntimeError(f"refusing symlink target: {path}")
    target.write_text(text)


def pytest(*args, check=True):
    interpreter = LIMEN / "cli/.venv/bin/python"
    if not interpreter.is_file():
        raise RuntimeError("approved PyYAML-capable Limen venv is unavailable")
    return run([str(interpreter), "-m", "pytest", *args, "-q"], check=check, timeout=180)


def verify():
    result = pytest("tests/test_closeout_protocol_bundle.py",
                    "tests/test_closeout_discovery.py",
                    "tests/test_domus_limen_runtime.py")
    print(result.stdout)
    rendered = run(["chezmoi", "--source", str(TARGET), "cat",
                    str(Path.home() / ".agents/skills/closeout/SKILL.md")], timeout=30)
    if "closeout_check.py" not in rendered.stdout or ".codex/skills/closeout/SKILL.md" not in rendered.stdout:
        raise RuntimeError("rendered entry lost canonical helper or discovery coverage")
    run(["git", "diff", "--check"], timeout=30)
    print("PASS: scoped regressions, template rendering, and diff check")


def preview(outputs):
    for path, text in outputs.items():
        old = original(path) if path in DATA["edits"] else ""
        print("".join(difflib.unified_diff(
            old.splitlines(True), text.splitlines(True), fromfile=path, tofile=path,
        )), end="")


def apply(args, outputs):
    target_guard(args.expected_lease_owner)
    with verification_lease():
        # Publish the authorized plan before producing implementation artifacts.
        write_targeted(PLAN, DATA["plan"])
        git("add", PLAN)
        git("commit", "-m", "docs: plan closeout discovery repairs")
        git("push", "-u", "origin", BRANCH)
        # Reproduce the explicit-root defect before modifying production code.
        path = "tests/test_closeout_protocol_bundle.py"
        write_targeted(path, original(path) + DATA["rootTests"])
        red = pytest(path, "-k", "explicit_override_bad_path_is_structured", check=False)
        print(red.stdout)
        if red.returncode != 1 or "FileNotFoundError" not in red.stdout:
            raise RuntimeError("expected invalid-root regression was not reproduced")
        # Apply exact bounded edit spans, preserving all unrelated source bytes.
        for path, text in outputs.items():
            if path != PLAN:
                write_targeted(path, text)
        verify()
        paths = [*DATA["edits"], *DATA["newFiles"]]
        git("add", *paths)
        git("commit", "-m", "fix: repair repository-agnostic closeout discovery")
        git("push", "origin", BRANCH)
        head = git("rev-parse", "HEAD").stdout.strip()
    body = TARGET / ".codex/plans/2026-10-18-closeout-discovery-heal-validation.md"
    body.write_text(
        "Generic closeout discovery currently requires Limen readiness and invokes "
        "the retired OpenCode debug interface. Use V2 standalone skill.list, validate "
        "actual directories and skill paths, preserve Codex admission, and separate "
        "optional provider readiness. Repair explicit-root errors and global entry "
        "delegation to the canonical helper.\n\n"
        "Validation: focused discovery, protocol and runtime regressions; chezmoi "
        "rendering; git diff --check. Native installed discovery remains unmeasured "
        "until accepted-source installation; no model turns or feature-source "
        "chezmoi apply occurred.\n\nRefs #505; 4444J99/limen#2999; 4444J99/limen#2995.\n"
    )
    git("add", str(body.relative_to(TARGET)))
    git("commit", "-m", "docs: record closeout discovery validation")
    git("push", "origin", BRANCH)
    head = git("rev-parse", "HEAD").stdout.strip()
    existing = json.loads(run([
        "gh", "pr", "list", "--repo", REPO, "--head", BRANCH, "--state", "open",
        "--json", "number,url",
    ], timeout=30).stdout)
    if existing:
        number = existing[0]["number"]
    else:
        created = run([
            "gh", "pr", "create", "--repo", REPO, "--base", "main", "--head", BRANCH,
            "--title", "Repair repository-agnostic closeout discovery",
            "--body-file", str(body),
        ], timeout=60)
        print(created.stdout)
        number = int(created.stdout.strip().rstrip("/").rsplit("/", 1)[-1])
    submitted = run([
        str(LIMEN / "cli/.venv/bin/python"), str(LIMEN / "scripts/merge-drain.py"),
        "--repo", REPO, "--pr", str(number), "--expected-head", head,
    ], cwd=LIMEN, check=False, timeout=120)
    print(submitted.stdout)
    print(submitted.stderr, file=sys.stderr)
    print(json.dumps({
        "status": "PUBLISHED_SUBMITTED", "head": head, "pr": number,
        "merge_submission_exit": submitted.returncode,
        "installed_discovery": "UNMEASURED",
        "note": "Submission is not proof of merge, installation, or live discovery.",
    }, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--dry-run", action="store_true")
    actions.add_argument("--apply", action="store_true")
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--syntax-check", action="store_true")
    parser.add_argument("--expected-lease-owner")
    args = parser.parse_args()
    signal.alarm(1800)
    os.nice(10)
    outputs = contents()
    if args.syntax_check:
        print("PASS: staged script and all Python implementation/test payloads compile")
    elif args.check:
        for path, text in outputs.items():
            if (TARGET / path).read_text() != text:
                raise RuntimeError(f"staged source is not applied exactly: {path}")
        with verification_lease():
            verify()
    elif args.apply:
        preview(outputs)
        apply(args, outputs)
    else:
        target_guard(args.expected_lease_owner)
        preview(outputs)
        print("DRY RUN ONLY: no repository files changed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from None
