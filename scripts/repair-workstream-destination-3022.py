#!/usr/bin/env python3
"""One operator-applied R1 source patch after two tool-bridge denials."""

from __future__ import annotations

import argparse
import ast
import difflib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = "d8703e0796c9d3938c76d2bff1f8162d8e4da8f9"
BRANCH = "work/unblock-3022-r5-r1-20261018"
VALIDATOR = '"""Validate an explicit workstream destination without creating or reserving it."""\nfrom __future__ import annotations\n\nimport argparse\nimport subprocess\nfrom pathlib import Path\n\nfrom limen.storage_headroom import _existing_volume_path\n\n\ndef validate_destination(repository: Path, branch: str, destination: Path) -> None:\n    if (not destination.is_absolute() or ".." in destination.parts\n            or any(path.is_symlink() for path in (destination, *destination.parents))):\n        raise ValueError("destination must be absolute without symlinks or parent traversal")\n    _existing_volume_path(destination)\n    if not destination.exists():\n        return\n    def git(path: Path, *args: str) -> str:\n        return subprocess.run(["git", "-C", str(path), *args], capture_output=True,\n                              text=True, check=True, timeout=5).stdout.strip()\n    if (git(destination, "rev-parse", "--show-toplevel") != str(destination)\n            or git(destination, "rev-parse", "--path-format=absolute", "--git-common-dir")\n               != git(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")\n            or git(destination, "branch", "--show-current") != branch):\n        raise ValueError("destination is not this repository\'s exact worktree and branch")\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument("--repository", type=Path, required=True)\n    parser.add_argument("--branch", required=True)\n    parser.add_argument("--destination", type=Path, required=True)\n    args = parser.parse_args()\n    try:\n        validate_destination(args.repository, args.branch, args.destination)\n    except (ValueError, OSError, subprocess.SubprocessError) as exc:\n        parser.exit(2, "destination refused: " + type(exc).__name__ + "\\n")\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
TESTS = '\ndef _destination_repo(tmp_path):\n    repo = tmp_path / "destination-repo"\n    repo.mkdir()\n    _git("init", "-q", "-b", "main", cwd=repo)\n    _git("config", "user.email", "fixture@example.invalid", cwd=repo)\n    _git("config", "user.name", "Fixture", cwd=repo)\n    (repo / "README.md").write_text("fixture\\n")\n    _git("add", "README.md", cwd=repo)\n    _git("commit", "-qm", "fixture", cwd=repo)\n    return repo\n\n\ndef test_explicit_destination_uses_same_admission_and_reuses_exact_worktree(tmp_path, monkeypatch):\n    repo = _destination_repo(tmp_path)\n    destination = tmp_path / "external" / "worktree"\n    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))\n    args = ["workstream", "--no-readme", "--destination", str(destination), str(repo), "external-route"]\n    result = CliRunner().invoke(main, args)\n    assert result.exit_code == 0, result.output\n    assert "created worktree: " + str(destination) in result.output\n    assert not (repo / ".worktrees").exists()\n    assert _git("branch", "--show-current", cwd=destination).stdout.strip() == "work/external-route"\n    second = CliRunner().invoke(main, args)\n    assert second.exit_code == 0, second.output\n    assert "reused worktree: " + str(destination) in second.output\n\n\n@pytest.mark.parametrize("kind", ["relative", "symlink", "foreign"])\ndef test_explicit_destination_refuses_ambiguous_targets(tmp_path, monkeypatch, kind):\n    repo = _destination_repo(tmp_path)\n    if kind == "relative":\n        destination = Path("relative-target")\n    elif kind == "symlink":\n        real = tmp_path / "real"\n        real.mkdir()\n        link = tmp_path / "link"\n        link.symlink_to(real, target_is_directory=True)\n        destination = link / "target"\n    else:\n        foreign = tmp_path / "foreign"\n        foreign.mkdir()\n        _git("init", "-q", "-b", "main", cwd=foreign)\n        destination = foreign\n    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))\n    result = CliRunner().invoke(main, ["workstream", "--no-readme", "--destination",\n                                     str(destination), str(repo), "bad-route"])\n    assert result.exit_code != 0\n    assert not (repo / ".worktrees").exists()\n    assert not _git("branch", "--list", "work/bad-route", cwd=repo).stdout.strip()\n'


def original(path):
    return subprocess.run(
        ["git", "show", BASE + ":" + path], cwd=ROOT, capture_output=True, text=True, check=True, timeout=10
    ).stdout


def build():
    launcher = original("scripts/start-worktree-session.sh")
    launcher = launcher.replace(
        "[--from <branch-or-ref>]", "[--destination <absolute-worktree-path>] [--from <branch-or-ref>]", 1
    )
    launcher = launcher.replace('from_ref=""\n', 'from_ref=""\ndestination=""\n', 1)
    launcher = launcher.replace(
        "    --from)\n",
        """    --destination)
      if [[ $# -lt 2 || -z "$2" ]]; then
        echo "missing value for --destination" >&2
        exit 2
      fi
      destination="$2"
      shift 2
      ;;
    --from)
""",
        1,
    )
    launcher = launcher.replace(
        'wt="$repo/.worktrees/$slug"\n',
        """wt="$repo/.worktrees/$slug"
if [[ -n "$destination" ]]; then
  if [[ -n "$campaign_relay" ]]; then
    echo "internal campaign relay does not accept --destination" >&2
    exit 2
  fi
  PYTHONPATH="$script_dir/../cli/src" python3 -m limen.worktree_destination \\
    --repository "$repo" --branch "$branch" --destination "$destination"
  wt="$destination"
fi
""",
        1,
    )
    cli = original("cli/src/limen/cli.py")
    cli = cli.replace(
        '@click.option(\n    "--from",',
        """@click.option(
    "--destination",
    type=click.Path(path_type=Path),
    default=None,
    help="Absolute worktree path; preserves target-volume admission.",
)
@click.option(
    "--from",""",
        1,
    )
    cli = cli.replace("    launch_shell,\n    from_ref,\n", "    launch_shell,\n    destination,\n    from_ref,\n", 1)
    cli = cli.replace(
        '    if from_ref:\n        args.extend(["--from", from_ref])\n',
        '    if destination is not None:\n        args.extend(["--destination", str(destination)])\n    if from_ref:\n        args.extend(["--from", from_ref])\n',
        1,
    )
    assert 'destination=""' in launcher
    assert "limen.worktree_destination" in launcher
    assert "    destination," in cli
    tests = original("cli/tests/test_workstream_command.py") + TESTS
    proposed = {
        "scripts/start-worktree-session.sh": launcher,
        "cli/src/limen/cli.py": cli,
        "cli/src/limen/worktree_destination.py": VALIDATOR,
        "cli/tests/test_workstream_command.py": tests,
    }
    for name, content in proposed.items():
        if name.endswith(".py"):
            proposed[name] = subprocess.run(
                [sys.executable, "-m", "ruff", "format", "--stdin-filename", str(ROOT / name), "-"],
                input=content,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout
    return proposed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    if branch != BRANCH:
        parser.exit(2, "wrong owner branch; no writes\n")
    proposed = build()
    for name, content in proposed.items():
        path = ROOT / name
        before = path.read_text() if path.exists() else ""
        expected = "" if name == "cli/src/limen/worktree_destination.py" else original(name)
        if before == content:
            continue
        if path.is_symlink() or before != expected:
            parser.exit(2, "source generation changed: " + name + "; no writes\n")
        if name.endswith(".py"):
            ast.parse(content)
        if name.endswith(".sh"):
            subprocess.run(["bash", "-n"], input=content, text=True, check=True)
        print(
            "".join(
                difflib.unified_diff(before.splitlines(True), content.splitlines(True), fromfile=name, tofile=name)
            ),
            end="",
        )
    if args.apply:
        for name, content in proposed.items():
            path = ROOT / name
            path.write_text(content)
        print("APPLIED: run the implicated hermetic tests and scoped gate before publication.")
    else:
        print("CHECK-PASS: source unchanged; proposed patch shown above.")


if __name__ == "__main__":
    main()
