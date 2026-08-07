"""The disposability predicate's own court — scripts/verify-hot-cache.sh, driven as the real script.

Every test here runs the SHIPPED file (`bash scripts/verify-hot-cache.sh`) with `$LIMEN_ROOT` pointed
at a fixture floor and `$PATH` rebuilt from exactly the tools the predicate shells. Nothing is
extracted, re-declared, or re-implemented: a rung that regresses in the file regresses here. That is
the point. A prior session "proved" a rung by sourcing an extracted COPY of it — a unit test in
disguise, green against a file it had already diverged from — and this file exists so the claim and
the artifact cannot drift apart again.

The predicate is read-only by construction, so pointing its root at a tmp dir is the whole isolation:
it walks $LIMEN_WORKDIR (an empty tmp dir), shells three child scripts and a census (all fixture
stubs), asks `mise` (a stub), and touches nothing else on this machine.

The defects these pin (2026-08-07):

R6 derived its VERDICT from parsing. `residue-census.py --check` exiting non-zero entered a loop that
called `fail` once per line containing BREACH — so a census that failed any OTHER way (a traceback,
an import error, a timeout kill) matched zero lines, called `fail` zero times, and the rung PASSED.
An unrunnable census read as a clean one, in the predicate whose whole job is to be un-foolable.
`test_r6_nonzero_exit_naming_no_breach_is_red` is the guard; its siblings hold what the fix must not
cost — per-BREACH naming, the green on exit 0, the advisory skip when the census is absent.

R5 was the same defect in different clothes: `find`'s status is unreadable through a process
substitution, so a wrong `$LIMEN_WORKDIR` enumerated nothing and printed "✓ 0 clone(s) clean, pushed,
stash-free" — a verification claim for a walk that never happened.

R4 could not tell WHOSE toolchain resolved. Every mise query answers for the config merged from the
CWD upward, so an ancestor mise.toml satisfies `mise ls --missing` as readily as $ROOT/mise.toml.
`test_r4_declared_tool_absent_from_resolved_toolchain_is_red` holds the assertion that this repo's
own declaration is in force, and `test_r4_extra_ancestor_tools_are_not_a_red` holds the matching
non-claim — coverage of the declaration, not equality with the merged config.

Bidirectional check, manual and deliberately not automated: revert one fix and re-run; the named test
above goes red. Automating that would require an extracted copy of the rung, which is precisely the
unit-test-in-disguise this file exists to avoid.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify-hot-cache.sh"
REAL_MISE_TOML = REPO_ROOT / "mise.toml"

# The predicate's entire external surface. $PATH is rebuilt from exactly this list, so no host tool —
# above all a real `mise` — can reach the fixture and decide a rung behind the test's back.
REQUIRED_TOOLS = ("bash", "git", "find", "grep", "sort", "awk", "tr", "cut", "head")

GREEN_CHILD = "raise SystemExit(0)\n"

# One stub driven by env, so R4's two questions (installed? declared by THIS repo?) stay separable.
# POSIX sh with an absolute shebang: the narrowed $PATH must not have to carry the stub's interpreter.
MISE_STUB = """#!/bin/sh
case "${1-}" in
  ls)      printf '%s' "${MISE_STUB_MISSING-}" ;;
  current) printf '%s' "${MISE_STUB_CURRENT-}" ;;
esac
exit 0
"""

# The repo's shape: a [tools] table of RANGES, quoted values, a trailing comment, and a following
# table the parser must stop at.
FIXTURE_MISE_TOML = """# fixture toolchain declaration
[tools]
python = "3.12"   # a RANGE, never a pin
node = "22"
uv = "latest"

[env]
_.file = ".env"
"""

RESOLVED = "python 3.12.13\nnode 22.23.2\nuv 0.12.2\n"

CENSUS_TRACEBACK = """import sys
print("Traceback (most recent call last):", file=sys.stderr)
print("ModuleNotFoundError: No module named 'yaml'", file=sys.stderr)
raise SystemExit(1)
"""

CENSUS_BREACHES = """print("residue-census: breaches=2")
print(" BREACH worktrees  37 / 8  count git worktrees beyond the live checkout")
print(" BREACH agent_runtime_mib  11974 / 2048  MiB harness runtime state")
raise SystemExit(1)
"""

CENSUS_GREEN = "raise SystemExit(0)\n"


def _write(path: Path, body: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if executable:
        path.chmod(0o755)


@pytest.fixture()
def floor(tmp_path):
    """A fixture ROOT on which R1-R4 are green, so any red below belongs to the rung under test."""
    absent = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if absent:
        pytest.skip(f"host lacks {absent}")
    root = tmp_path / "root"
    for child in ("cartridge-connected.py", "chezmoi-drift.py", "creds-hydrate.py"):
        _write(root / "scripts" / child, GREEN_CHILD)
    _write(root / "mise.toml", FIXTURE_MISE_TOML)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    binpath = tmp_path / "bin"
    binpath.mkdir()
    for tool in REQUIRED_TOOLS:
        (binpath / tool).symlink_to(shutil.which(tool))
    # sys.executable, never `which python3`: a host python3 may be a mise shim, which would re-enter
    # the stub below and decide R1-R3 behind the test's back.
    (binpath / "python3").symlink_to(sys.executable)
    _write(binpath / "mise", MISE_STUB, executable=True)
    return {"root": root, "workdir": workdir, "home": home, "bin": binpath}


def _run(floor, *, census=None, resolved=RESOLVED, uninstalled="", mise=True):
    if census is not None:
        _write(floor["root"] / "scripts" / "residue-census.py", census)
    if not mise and (floor["bin"] / "mise").exists():
        (floor["bin"] / "mise").unlink()
    env = {
        "PATH": str(floor["bin"]),
        "HOME": str(floor["home"]),
        "LIMEN_ROOT": str(floor["root"]),
        "LIMEN_WORKDIR": str(floor["workdir"]),
        "MISE_STUB_CURRENT": resolved,
        "MISE_STUB_MISSING": uninstalled,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(
        [shutil.which("bash"), str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def _rung(result, name):
    return [line.strip() for line in result.stdout.splitlines() if name in line]


# --- the fixture floor itself is honest ------------------------------------------------------------
def test_the_fixture_floor_is_green_end_to_end(floor):
    """A control. If R1-R4 were not green here, every red below would be unattributable."""
    result = _run(floor, census=CENSUS_GREEN)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HOT-CACHE: DISPOSABLE" in result.stdout
    assert "✗" not in result.stdout, result.stdout


def test_unreachable_root_cannot_report_disposable(floor):
    """R0: every rung resolves against the CWD, so a failed `cd` would answer for the wrong tree."""
    floor["root"].rename(floor["root"].with_name("moved-away"))
    result = _run(floor)
    assert result.returncode == 1
    assert "LIMEN_ROOT unreachable" in result.stdout, result.stdout
    assert "HOT-CACHE: DISPOSABLE" not in result.stdout


# --- R6: the verdict is the exit code; the BREACH lines are only the detail -------------------------
def test_r6_nonzero_exit_naming_no_breach_is_red(floor):
    """THE regression. A census that dies before it can name a breach must not read as a clean one."""
    result = _run(floor, census=CENSUS_TRACEBACK)
    r6 = _rung(result, "R6 residue")
    assert r6, result.stdout
    assert all(line.startswith("✗") for line in r6), f"R6 went green on an unrunnable census:\n{result.stdout}"
    joined = "\n".join(r6)
    assert "exited 1" in joined, joined
    assert "Traceback" in joined, f"the red must carry the child's own words:\n{joined}"
    assert result.returncode == 1
    assert "HOT-CACHE: NOT DISPOSABLE" in result.stdout


def test_r6_breach_lines_are_still_named_one_red_each(floor):
    """What the fix must not cost: the generic red is a FLOOR, never a replacement for the detail."""
    result = _run(floor, census=CENSUS_BREACHES)
    r6 = _rung(result, "R6 residue")
    assert len(r6) == 2, f"expected one red per BREACH line:\n{result.stdout}"
    assert all(line.startswith("✗") for line in r6)
    assert "worktrees" in r6[0] and "agent_runtime_mib" in r6[1], r6
    assert not any("UNRUNNABLE" in line for line in r6), result.stdout
    assert result.returncode == 1


def test_r6_clean_census_is_green(floor):
    result = _run(floor, census=CENSUS_GREEN)
    assert _rung(result, "R6 residue") == ["✓ R6 residue — every declared cap holds (nothing sprawling)"]
    assert result.returncode == 0, result.stdout


def test_r6_absent_census_is_an_advisory_skip(floor):
    """Fail-open where an ORGAN is absent: a missing census is a gap in the court, not local state."""
    result = _run(floor, census=None)
    r6 = _rung(result, "R6 residue")
    assert r6 and r6[0].startswith("·"), result.stdout
    assert result.returncode == 0, result.stdout


# --- R5: an empty walk is not a clean floor --------------------------------------------------------
def test_r5_empty_enumeration_does_not_claim_clean(floor):
    """R6's defect in R5's clothes — `find`'s status is unreadable through a process substitution, so
    a wrong $LIMEN_WORKDIR printed a verification claim for a walk that never happened."""
    result = _run(floor, census=CENSUS_GREEN)
    r5 = _rung(result, "R5 repos")
    assert r5 and r5[0].startswith("·"), result.stdout
    assert "0 clones" in r5[0], r5
    assert "clean, pushed, stash-free" not in r5[0], f"an empty walk must not claim verification: {r5}"


def test_r5_counts_a_real_clone(floor):
    """The matching positive: a clean, pushed, stash-free clone under $WS is a genuine green."""
    clone = floor["workdir"] / "clone"
    clone.mkdir()
    subprocess.run(["git", "init", "-q", str(clone)], check=True, capture_output=True)
    result = _run(floor, census=CENSUS_GREEN)
    r5 = _rung(result, "R5 repos")
    assert r5 and r5[0].startswith("✓"), result.stdout
    assert "1 clone(s)" in r5[0], r5


# --- R4: installed, and it is THIS repo's declaration that is in force ------------------------------
def test_r4_is_green_when_every_declared_tool_is_installed_and_in_force(floor):
    result = _run(floor, census=CENSUS_GREEN)
    r4 = _rung(result, "R4 toolchain")
    assert r4 and r4[0].startswith("✓"), result.stdout
    for tool in ("python", "node", "uv"):
        assert tool in r4[0], r4


def test_r4_declared_tool_absent_from_resolved_toolchain_is_red(floor):
    """mise resolves against the CWD, so an ANCESTOR mise.toml satisfies it just as readily. Here the
    resolved toolchain covers python and node but not the `uv` $ROOT/mise.toml declares — the rung
    must say so instead of reporting somebody else's toolchain as this repo's."""
    result = _run(floor, census=CENSUS_GREEN, resolved="python 3.12.13\nnode 22.23.2\nruby 3.3.0\n")
    r4 = _rung(result, "R4 toolchain")
    assert r4 and r4[0].startswith("✗"), result.stdout
    assert "uv" in r4[0], r4
    assert result.returncode == 1


def test_r4_extra_ancestor_tools_are_not_a_red(floor):
    """The matching non-claim: R4 asserts COVERAGE of $ROOT/mise.toml, not equality with the merged
    config. A tool an ancestor contributes is not this repo's declaration to hold."""
    result = _run(floor, census=CENSUS_GREEN, resolved=RESOLVED + "ruby 3.3.0\n")
    r4 = _rung(result, "R4 toolchain")
    assert r4 and r4[0].startswith("✓"), result.stdout


def test_r4_uninstalled_tool_is_red(floor):
    result = _run(floor, census=CENSUS_GREEN, uninstalled="node 22.23.2 mise.toml 22\n")
    r4 = _rung(result, "R4 toolchain")
    assert r4 and r4[0].startswith("✗"), result.stdout
    assert "node@22.23.2" in r4[0], r4
    assert result.returncode == 1


def test_r4_declaration_without_tools_is_red(floor):
    _write(floor["root"] / "mise.toml", "[env]\n_.file = '.env'\n")
    result = _run(floor, census=CENSUS_GREEN)
    r4 = _rung(result, "R4 toolchain")
    assert r4 and r4[0].startswith("✗"), result.stdout
    assert "[tools]" in r4[0], r4


def test_r4_missing_mise_stays_an_advisory_skip(floor):
    """Organ-absent is fail-open by doctrine: the jack-in installs mise, so its absence on a working
    floor is a gap, not un-summonable state."""
    result = _run(floor, census=CENSUS_GREEN, mise=False)
    r4 = _rung(result, "R4 toolchain")
    assert r4 and r4[0].startswith("·"), result.stdout
    assert result.returncode == 0, result.stdout


def test_r4_parses_the_repos_real_declaration(floor):
    """Bind the rung's awk to the file it must actually parse. tomllib is an INDEPENDENT parser here —
    a cross-check, not a second copy of the awk."""
    shutil.copyfile(REAL_MISE_TOML, floor["root"] / "mise.toml")
    declared = list(tomllib.loads(REAL_MISE_TOML.read_text(encoding="utf-8"))["tools"])
    assert declared, "mise.toml declares no [tools]"

    everything = "".join(f"{tool} 0.0.0\n" for tool in declared)
    green = _run(floor, census=CENSUS_GREEN, resolved=everything)
    r4 = _rung(green, "R4 toolchain")
    assert r4 and r4[0].startswith("✓"), green.stdout
    for tool in declared:
        assert tool in r4[0], r4

    for dropped in declared:
        thin = "".join(f"{tool} 0.0.0\n" for tool in declared if tool != dropped)
        red = _rung(_run(floor, census=CENSUS_GREEN, resolved=thin), "R4 toolchain")
        assert red and red[0].startswith("✗"), (dropped, red)
        assert dropped in red[0], (dropped, red)
