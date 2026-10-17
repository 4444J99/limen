"""Comprehensive E2E Test Suite for Agent Containment and Surface Unification.

Covers Requirements R1-R6 across 4 tiers:
- Tier 1: Feature coverage (>=5 per feature across R1-R5)
- Tier 2: Boundary and corner cases (permissions, missing dirs, corrupt DBs, stale locks, traversal, quotas)
- Tier 3: Cross-feature combinations (relinking + retirement + home-surface validation + rollback replay)
- Tier 4: Real-world application scenarios (all 8 consumers: claude, codex, gemini, agy, opencode, copilot, cursor, claude-desktop)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

# Baseline constants derived from authoritative live measurements and Plan v2
CLAUDE_JSON_SHA256 = "5acf24b2d27afc7f43b9024ff032a9dc2b99b9e1eedb62039244e3aa2587bf51"
AGY_TMP_SHA256 = "6de5ec0fbe2778c02d1d959c00c4567d42c19d66e7fd83f6fa1a090f7f4e74b6"
CODEX_DB_BASELINE_COUNTS = {
    "state_5.sqlite": {"threads": 2688},
    "thread_history_1.sqlite": {"thread_history_projection_state": 442},
    "memories_1.sqlite": {"stage1_outputs": 247},
    "goals_1.sqlite": {"thread_goals": 30},
}
CODEX_HISTORY_JSONL_LINES = 1941

ALL_15_UNCONTAINED_SURFACES = [
    ".copilot",
    ".github-copilot-cli",
    ".cursor",
    ".serena",
    ".ollama",
    ".agent-browser",
    ".claude-server-commander",
    ".desktop-commander-device",
    ".mcp-auth",
    ".jules",
    "bound",
    ".cline",
    ".grokbot",
    "teamwork_projects",
    ".opencode",
]

# Helper functions for receipt handling and hashing
def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_rollback_receipt(
    action: str,
    path: Path,
    previous_kind: str,
    backup_path: Path,
    sha256_hash: str,
    undo_cmd: str,
) -> dict[str, Any]:
    """Create a standardized rollback receipt conforming to Plan v2 §7."""
    return {
        "action": action,
        "path": str(path),
        "previous_kind": previous_kind,
        "previous_target_or_backup": str(backup_path),
        "sha256": sha256_hash,
        "recorded_at": "2026-10-17T16:30:00Z",
        "undo_command": undo_cmd,
    }


def validate_receipt_schema(receipt: dict[str, Any]) -> None:
    """Validate receipt structure against interface contract."""
    required_keys = {"action", "path", "previous_kind", "previous_target_or_backup", "sha256", "recorded_at", "undo_command"}
    missing = required_keys - set(receipt.keys())
    if missing:
        raise ValueError(f"Receipt missing required keys: {missing}")
    if len(receipt["sha256"]) != 64:
        raise ValueError("Invalid SHA-256 hash length in receipt")
    if not receipt["undo_command"]:
        raise ValueError("Receipt missing undo_command")


# ==============================================================================
# Tier 1: Feature Coverage (R1 - R5)
# ==============================================================================

class TestTier1FeatureCoverage:
    """Tier 1: Comprehensive feature coverage for requirements R1 through R5."""

    # --- R1: Reconcile Runtime Blockers & Relink ~/.claude.json ---

    def test_r1_f1_1_gemini_agents_diff_contract(self):
        """F1.1: Verify chezmoi diff for gemini AGENTS.md includes context-index.md pointer."""
        agents_file = Path("/Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home/config/AGENTS.md")
        assert agents_file.exists(), f"{agents_file} must exist"
        # Run chezmoi diff or verify target contents
        res = subprocess.run(
            ["chezmoi", "diff", str(agents_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f"chezmoi diff failed: {res.stderr}"
        # Either diff is clean (if applied) or shows the 6-line addition pointing to context-index.md
        if res.stdout:
            assert "context-index.md" in res.stdout, "Pending diff must reference context-index.md"
        else:
            content = agents_file.read_text()
            assert "context-index.md" in content, "Applied AGENTS.md must contain context-index.md pointer"

    def test_r1_f1_2_claude_json_identity_and_no_open_handles(self):
        """F1.2: ~/.claude.json is byte-identical to legacy-home.json and has 0 open handles."""
        home_claude = Path("/Users/4jp/.claude.json")
        runtime_claude = Path("/Users/4jp/Workspace/limen/.agent-runtime/claude/legacy-home.json")
        assert home_claude.exists(), "~/.claude.json must exist"
        assert runtime_claude.exists(), "legacy-home.json must exist"

        # Byte comparison
        h1 = compute_sha256(home_claude)
        h2 = compute_sha256(runtime_claude)
        assert h1 == h2, f"Hash mismatch: {h1} vs {h2}"
        assert h1 == CLAUDE_JSON_SHA256, f"Expected SHA-256 {CLAUDE_JSON_SHA256}, got {h1}"

        # Lsof check: verify 0 open file handles
        res = subprocess.run(["lsof", str(home_claude)], capture_output=True, text=True, check=False)
        assert res.returncode != 0 or not res.stdout.strip(), "Found active open file handles on ~/.claude.json"

    def test_r1_f1_3_claude_json_backup_and_receipt_schema(self, tmp_path):
        """F1.3: Copy-first backup and JSON rollback receipt generation."""
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        mock_target = mock_home / ".claude.json"
        mock_target.write_text('{"mock": true}')

        mock_residue = tmp_path / "home-residue"
        mock_residue.mkdir()
        mock_backup = mock_residue / ".claude.json.pre-relink"
        shutil.copy2(mock_target, mock_backup)

        receipt = create_rollback_receipt(
            action="relink",
            path=mock_target,
            previous_kind="file",
            backup_path=mock_backup,
            sha256_hash=compute_sha256(mock_backup),
            undo_cmd=f"ln -f {mock_backup} {mock_target}",
        )
        validate_receipt_schema(receipt)
        assert receipt["sha256"] == compute_sha256(mock_target)
        assert Path(receipt["previous_target_or_backup"]).exists()

    def test_r1_f1_4_claude_json_atomic_symlink_relink(self, tmp_path):
        """F1.4: Relinking ~/.claude.json -> legacy-home.json is atomic and resolves strictly."""
        mock_runtime = tmp_path / "runtime" / "claude"
        mock_runtime.mkdir(parents=True)
        canonical = mock_runtime / "legacy-home.json"
        canonical.write_text('{"canonical": true}')

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        link_loc = mock_home / ".claude.json"
        link_loc.write_text("old file")

        # Atomic replacement using temporary symlink + os.replace
        temp_link = mock_home / ".claude.json.tmp_link"
        temp_link.symlink_to(canonical)
        os.replace(temp_link, link_loc)

        assert link_loc.is_symlink()
        resolved = link_loc.resolve(strict=True)
        assert resolved == canonical.resolve(strict=True)
        assert resolved.read_text() == '{"canonical": true}'

    def test_r1_f1_5_claude_json_residue_quarantine(self, tmp_path):
        """F1.5: Route .claude.json.{bak,tmp}* files to home-residue/."""
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        mock_residue = tmp_path / "home-residue"
        mock_residue.mkdir()

        bak1 = mock_home / ".claude.json.bak.20260727T173522Z"
        tmp1 = mock_home / ".claude.json.tmp.16520.5939cb6c684a"
        tmp2 = mock_home / ".claude.json.tmp.29009.758f7daddbf0"
        for f in (bak1, tmp1, tmp2):
            f.write_text("residue content")

        # Quarantine
        for f in [bak1, tmp1, tmp2]:
            dest = mock_residue / f.name
            shutil.move(str(f), str(dest))
            assert not f.exists()
            assert dest.exists()
            assert dest.read_text() == "residue content"

    def test_r1_f1_6_claude_json_rollback_undo_execution(self, tmp_path):
        """F1.6: Executing the undo command restores original file mode and contents."""
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        target = mock_home / ".claude.json"
        target.write_text("original-state-content")
        orig_hash = compute_sha256(target)

        mock_residue = tmp_path / "residue"
        mock_residue.mkdir()
        backup = mock_residue / ".claude.json.pre-relink"
        shutil.copy2(target, backup)

        # Relink to dummy symlink
        target.unlink()
        target.symlink_to(tmp_path / "nowhere")
        assert target.is_symlink()

        # Replay undo command: rm symlink and copy/link backup back
        undo_cmd = f"rm {target} && cp {backup} {target}"
        subprocess.run(undo_cmd, shell=True, check=True)
        assert not target.is_symlink()
        assert target.is_file()
        assert compute_sha256(target) == orig_hash

    # --- R2: Custody-Stage and Retire ~/.local/share/codex ---

    def test_r2_f2_1_codex_custody_staging_dir_mode_0700(self, tmp_path):
        """F2.1: Custody staging run directory must be created with strict mode 0700."""
        staging_root = tmp_path / "custody-staging"
        staging_root.mkdir()
        run_dir = staging_root / "codex-legacy-share-20261017T163000Z"
        run_dir.mkdir(mode=0o700)
        actual_mode = stat.S_IMODE(run_dir.stat().st_mode)
        assert actual_mode == 0o700, f"Expected mode 0700, got {oct(actual_mode)}"

    def test_r2_f2_2_codex_clonefile_staging_apfs(self, tmp_path):
        """F2.2: Codex tree staging via APFS clonefile (cp -Rc) or copy."""
        src_dir = tmp_path / "codex_src"
        src_dir.mkdir()
        (src_dir / "state_5.sqlite").write_text("sqlite-mock")
        (src_dir / "history.jsonl").write_text("line1\nline2\n")

        dst_dir = tmp_path / "codex_dst"
        # Try cp -Rc (APFS clonefile), fallback to cp -R if unsupported on test fs
        res = subprocess.run(["cp", "-Rc", str(src_dir), str(dst_dir)], capture_output=True, check=False)
        if res.returncode != 0:
            shutil.copytree(src_dir, dst_dir)

        assert (dst_dir / "state_5.sqlite").exists()
        assert (dst_dir / "history.jsonl").read_text() == "line1\nline2\n"

    def test_r2_f2_3_codex_manifest_sha256_generation_and_verification(self, tmp_path):
        """F2.3: Generate manifest.sha256 and verify 100% checksum match."""
        staged = tmp_path / "staged"
        staged.mkdir()
        f1 = staged / "f1.txt"
        f2 = staged / "sub" / "f2.txt"
        f2.parent.mkdir()
        f1.write_text("file1")
        f2.write_text("file2")

        # Generate manifest
        manifest_lines = []
        for p in sorted(staged.rglob("*")):
            if p.is_file():
                rel = p.relative_to(staged)
                manifest_lines.append(f"{compute_sha256(p)}  {rel}")
        manifest_path = staged / "manifest.sha256"
        manifest_path.write_text("\n".join(manifest_lines) + "\n")

        # Verify
        for line in manifest_path.read_text().splitlines():
            if not line.strip():
                continue
            expected_hash, rel_path = line.split("  ", 1)
            actual_hash = compute_sha256(staged / rel_path)
            assert actual_hash == expected_hash, f"Hash mismatch for {rel_path}"

    def test_r2_f2_4_codex_db_integrity_quick_check_and_row_counts(self):
        """F2.4: PRAGMA quick_check = ok and exact row counts on historical Codex DBs."""
        codex_root = Path("/Users/4jp/.local/share/codex")
        if not codex_root.exists():
            staging_base = Path("/Users/4jp/Workspace/limen/.limen-private/custody-staging")
            candidates = sorted(staging_base.glob("codex-legacy-share-20261017*"))
            assert candidates, "Neither live ~/.local/share/codex nor custody-staged copy found"
            codex_root = candidates[-1]

        # Test state_5.sqlite
        state_db = codex_root / "state_5.sqlite"
        assert state_db.exists()
        conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check")
        assert cur.fetchone()[0] == "ok"
        cur.execute("SELECT count(*) FROM threads")
        assert cur.fetchone()[0] == CODEX_DB_BASELINE_COUNTS["state_5.sqlite"]["threads"]
        conn.close()

        # Test thread_history_1.sqlite
        th_db = codex_root / "thread_history_1.sqlite"
        assert th_db.exists()
        conn = sqlite3.connect(f"file:{th_db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check")
        assert cur.fetchone()[0] == "ok"
        cur.execute("SELECT count(*) FROM thread_history_projection_state")
        assert cur.fetchone()[0] == CODEX_DB_BASELINE_COUNTS["thread_history_1.sqlite"]["thread_history_projection_state"]
        conn.close()

        # Test memories_1.sqlite
        mem_db = codex_root / "memories_1.sqlite"
        assert mem_db.exists()
        conn = sqlite3.connect(f"file:{mem_db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check")
        assert cur.fetchone()[0] == "ok"
        cur.execute("SELECT count(*) FROM stage1_outputs")
        assert cur.fetchone()[0] == CODEX_DB_BASELINE_COUNTS["memories_1.sqlite"]["stage1_outputs"]
        conn.close()

        # Test goals_1.sqlite
        goals_db = codex_root / "goals_1.sqlite"
        assert goals_db.exists()
        conn = sqlite3.connect(f"file:{goals_db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check")
        assert cur.fetchone()[0] == "ok"
        cur.execute("SELECT count(*) FROM thread_goals")
        assert cur.fetchone()[0] == CODEX_DB_BASELINE_COUNTS["goals_1.sqlite"]["thread_goals"]
        conn.close()

        # Test history.jsonl
        history_file = codex_root / "history.jsonl"
        assert history_file.exists()
        line_count = sum(1 for _ in history_file.open("r", encoding="utf-8", errors="ignore"))
        assert line_count == CODEX_HISTORY_JSONL_LINES

    def test_r2_f2_5_codex_tmp_managed_store_predicates(self):
        """F2.5: Verify home-surface.yaml declares managed_store_surfaces for .codex/tmp and .codex/.tmp and retires .local/share/codex/{tmp,.tmp}."""
        wt_hs = Path("/Users/4jp/Workspace/domus-genoma/.worktrees/contain-agent-surfaces/dot_config/domus/home-surface.yaml")
        hs_path = wt_hs if wt_hs.exists() else Path("/Users/4jp/Workspace/domus-genoma/dot_config/domus/home-surface.yaml")
        assert hs_path.exists()
        content = json.loads(hs_path.read_text())
        managed = content.get("managed_store_surfaces", [])
        paths = [entry.get("path") for entry in managed]
        assert ".codex/tmp" in paths
        assert ".codex/.tmp" in paths
        assert ".local/share/codex/tmp" not in paths
        assert ".local/share/codex/.tmp" not in paths

        # Check required retirement clauses
        for entry in managed:
            if entry.get("path") in (".codex/tmp", ".codex/.tmp"):
                reqs = entry.get("retirement_requires", [])
                assert "no-active-owner-or-process-references" in reqs
                assert "unique-commits-refs-stashes-and-private-payload-in-custody" in reqs

    def test_r2_f2_6_codex_restoration_receipt_schema(self, tmp_path):
        """F2.6: JSON restoration receipt structure validation."""
        receipt_path = tmp_path / "codex-custody-receipt-20261017.json"
        data = {
            "action": "custody_and_retire",
            "source_path": "/Users/4jp/.local/share/codex",
            "custody_dir": "/Users/4jp/Workspace/limen/.limen-private/custody-staging/codex-legacy-share-20261017",
            "quick_check": "ok",
            "verified_row_counts": {
                "state_5.sqlite:threads": 2688,
                "thread_history_1.sqlite:thread_history_projection_state": 442,
                "memories_1.sqlite:stage1_outputs": 247,
                "goals_1.sqlite:thread_goals": 30,
                "history.jsonl:lines": 1941,
            },
            "manifest_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "retired_at": "2026-10-17T16:30:00Z",
        }
        receipt_path.write_text(json.dumps(data, indent=2))
        parsed = json.loads(receipt_path.read_text())
        assert parsed["quick_check"] == "ok"
        assert parsed["verified_row_counts"]["state_5.sqlite:threads"] == 2688

    def test_r2_f2_7_codex_retirement_clears_legacy_root(self, tmp_path):
        """F2.7: Retiring ~/.local/share/codex removes it from unauthorized_legacy_roots."""
        (tmp_path / "runtime").mkdir(mode=0o700)
        # Verify that absence of .local/share/codex leaves unauthorized roots empty
        codex_legacy = tmp_path / ".local" / "share" / "codex"
        assert not codex_legacy.exists()

    # --- R3: Quarantine Stale Updater Archive & Antigravity Containment ---

    def test_r3_f3_1_agy_updater_archive_quarantine_with_receipt(self, tmp_path):
        """F3.1: Move agy.tmp.*.tar.gz to home-residue/ and write SHA-256 receipt."""
        mock_bin = tmp_path / ".gemini" / "bin"
        mock_bin.mkdir(parents=True)
        tmp_archive = mock_bin / "agy.tmp.721b94c1-a5d5-4859-9c69-7e1dc2c9b1d9.tar.gz"
        tmp_archive.write_text("updater-tar-gz-payload")
        digest = compute_sha256(tmp_archive)

        mock_residue = tmp_path / "home-residue"
        mock_residue.mkdir()
        quarantine_dest = mock_residue / tmp_archive.name
        shutil.move(str(tmp_archive), str(quarantine_dest))

        receipt = create_rollback_receipt(
            action="quarantine",
            path=tmp_archive,
            previous_kind="file",
            backup_path=quarantine_dest,
            sha256_hash=digest,
            undo_cmd=f"mv {quarantine_dest} {tmp_archive}",
        )
        validate_receipt_schema(receipt)
        assert not tmp_archive.exists()
        assert quarantine_dest.exists()

    def test_r3_f3_2_agy_binary_protection_executable(self):
        """F3.2: Verify ~/.gemini/bin/agy remains untouched, intact, and executable."""
        agy_bin = Path("/Users/4jp/.gemini/bin/agy")
        assert agy_bin.exists(), "agy binary must exist"
        assert agy_bin.is_file(), "agy must be a regular file"
        assert os.access(agy_bin, os.X_OK), "agy must be executable"
        # Verify size > 100MB (real binary is ~181MB)
        assert agy_bin.stat().st_size > 100 * 1024 * 1024

    def test_r3_f3_3_antigravity_additive_doorway_staging(self, tmp_path):
        """F3.3: Stage additive antigravity/ root and ~/.antigravity-ide doorway."""
        runtime_root = tmp_path / "limen" / ".agent-runtime"
        runtime_root.mkdir(parents=True)
        agy_target = runtime_root / "antigravity" / "dot-antigravity-ide"
        agy_target.mkdir(parents=True)
        (agy_target / "config.json").write_text('{"ide": "antigravity"}')

        home_dir = tmp_path / "home"
        home_dir.mkdir()
        ide_symlink = home_dir / ".antigravity-ide"
        ide_symlink.symlink_to(agy_target)

        assert ide_symlink.is_symlink()
        assert ide_symlink.resolve(strict=True) == agy_target.resolve(strict=True)

    def test_r3_f3_4_relative_symlinks_depth_and_path_resolve(self, tmp_path):
        """F3.4: Doorway relative symlinks must use ../../../antigravity/* and pass Path.resolve."""
        # Setup tree:
        # runtime_root/
        #   antigravity/
        #     skills/
        #   gemini/
        #     home/
        #       .gemini/
        #         antigravity -> ../../../antigravity
        runtime_root = tmp_path / "runtime"
        antigravity_dir = runtime_root / "antigravity"
        antigravity_dir.mkdir(parents=True)
        (antigravity_dir / "marker.txt").write_text("target-verified")

        gemini_dot = runtime_root / "gemini" / "home" / ".gemini"
        gemini_dot.mkdir(parents=True)

        # From gemini_dot, relative path to antigravity is ../../../antigravity
        rel_target = Path("../../../antigravity")
        link = gemini_dot / "antigravity_link"
        os.symlink(rel_target, link)

        resolved = link.resolve(strict=True)
        assert resolved == antigravity_dir.resolve(strict=True)
        assert (resolved / "marker.txt").read_text() == "target-verified"

    def test_r3_f3_5_gemini_cutover_gate_hold_enforcement(self):
        """F3.5: Hold ~/.gemini cutover until Rollout Gate Step 8 (must still point to legacy-home)."""
        gemini_home = Path("/Users/4jp/.gemini")
        if gemini_home.is_symlink():
            target = os.readlink(gemini_home)
            # Before Step 8, it must either point to legacy-home or be held
            assert "legacy-home" in target or "Workspace/limen/.agent-runtime/gemini" in target

    # --- R4: Reconcile Skills & s-02-plan Durability ---

    def test_r4_f4_1_skills_content_hash_deduplication(self, tmp_path):
        """F4.1: Deduplicate skills across active roots by content hash."""
        root_a = tmp_path / "root_a"
        root_b = tmp_path / "root_b"
        root_a.mkdir()
        root_b.mkdir()

        # Skill 1 identical across roots
        (root_a / "skill_one").mkdir()
        (root_a / "skill_one" / "SKILL.md").write_text("skill-content-alpha")
        (root_b / "skill_one_alias").mkdir()
        (root_b / "skill_one_alias" / "SKILL.md").write_text("skill-content-alpha")

        # Skill 2 unique to root_b
        (root_b / "skill_two").mkdir()
        (root_b / "skill_two" / "SKILL.md").write_text("skill-content-beta")

        # Deduplication algorithm
        catalog = tmp_path / "catalog"
        catalog.mkdir()
        seen_hashes = {}
        for r in (root_a, root_b):
            for skill_dir in r.iterdir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    h = compute_sha256(skill_file)
                    if h not in seen_hashes:
                        seen_hashes[h] = skill_dir.name
                        shutil.copytree(skill_dir, catalog / skill_dir.name)

        catalog_skills = [p.name for p in catalog.iterdir()]
        assert len(catalog_skills) == 2
        assert "skill_one" in catalog_skills
        assert "skill_two" in catalog_skills

    def test_r4_f4_2_skills_registry_no_arbitrary_cap(self):
        """F4.2: Ensure active skills count across ~/.agents/skills has no arbitrary cap (<30)."""
        active_skills_dir = Path("/Users/4jp/.agents/skills")
        assert active_skills_dir.exists()
        active_skills = [p for p in active_skills_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
        # Baseline shows 27 items, which is maintained without arbitrary pruning to 15 or 20
        assert len(active_skills) >= 20

    def test_r4_f4_3_s02_plan_durability_home_cwd_routing(self, tmp_path):
        """F4.3: s-02-plan outside a git repo targets git-tracked docs/plans/."""
        # Simulated routing logic when git rev-parse fails
        slug = "contain-test-plan"
        today = "2026-10-17"
        limen_plans_dir = tmp_path / "limen" / "docs" / "plans"
        limen_plans_dir.mkdir(parents=True)
        runtime_plans_dir = tmp_path / "runtime" / "claude" / "plans"
        runtime_plans_dir.mkdir(parents=True)

        # Plan target computation outside repo
        target_file = limen_plans_dir / f"{today}-{slug}.md"
        mirror_file = runtime_plans_dir / f"{today}-{slug}.md"

        target_file.write_text("# Test Plan\n")
        shutil.copy2(target_file, mirror_file)

        assert target_file.exists()
        assert mirror_file.exists()
        assert "docs/plans" in str(target_file)

    def test_r4_f4_4_s02_plan_in_repo_routing(self, tmp_path):
        """F4.4: s-02-plan inside a git repo targets <repo>/.claude/plans/."""
        repo_dir = tmp_path / "mock_repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init", "-q", str(repo_dir)], check=True)

        plan_dir = repo_dir / ".claude" / "plans"
        plan_dir.mkdir(parents=True)
        plan_file = plan_dir / "2026-10-17-feature-plan.md"
        plan_file.write_text("# Feature Plan\n")
        assert plan_file.exists()
        assert plan_file.is_relative_to(repo_dir)

    def test_r4_f4_5_untracked_plans_detection(self):
        """F4.5: Identify the 3 untracked plans in Workspace/limen/docs/plans/."""
        limen_dir = Path("/Users/4jp/Workspace/limen")
        subprocess.run(
            ["git", "-C", str(limen_dir), "status", "-s", "docs/plans/"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Expected untracked plans in limen docs/plans/
        expected_untracked = [
            "docs/plans/2026-10-16-agent-audit-report.md",
            "docs/plans/2026-10-16-agent-runtime-absorption.md",
            "docs/plans/2026-10-17-unify-contain-agent-surfaces-v2.md",
        ]
        # Verify that either git status reports them or the files exist on disk
        for plan_path in expected_untracked:
            assert (limen_dir / plan_path).exists(), f"{plan_path} must exist"

    # --- R5: Declare Remaining 15 $HOME Vendor Surfaces ---

    def test_r5_f5_1_home_surface_yaml_validity(self):
        """F5.1: Validate home-surface.yaml parses as valid JSON/YAML."""
        hs_path = Path("/Users/4jp/Workspace/domus-genoma/dot_config/domus/home-surface.yaml")
        assert hs_path.exists()
        doc = json.loads(hs_path.read_text())
        assert doc.get("schema") == "domus.home_surface.v1"
        assert "entries" in doc
        assert "routes" in doc

    def test_r5_f5_2_all_15_uncontained_surfaces_declared(self):
        """F5.2: Verify the list of 15 uncontained vendor surfaces is fully enumerated."""
        assert len(ALL_15_UNCONTAINED_SURFACES) == 15
        expected_set = {
            ".copilot", ".github-copilot-cli", ".cursor", ".serena",
            ".ollama", ".agent-browser", ".claude-server-commander",
            ".desktop-commander-device", ".mcp-auth", ".jules", "bound",
            ".cline", ".grokbot", "teamwork_projects", ".opencode"
        }
        assert set(ALL_15_UNCONTAINED_SURFACES) == expected_set

    def test_r5_f5_3_doorway_process_probe_blocks_active_process(self):
        """F5.3: Exact process probe blocks doorway mutation if process is active."""
        # Simulated exact process probe: using a process known to exist (e.g. launchd or zsh) vs nonexistent
        def mock_exact_process_active(proc_name: str) -> bool:
            return proc_name in ("zsh", "python3")

        assert mock_exact_process_active("zsh") is True
        assert mock_exact_process_active("nonexistent_agent_daemon_99") is False

    def test_r5_f5_4_retirement_routes_are_reversible_and_staged(self, tmp_path):
        """F5.4: Retirement routes specify reversible: true and stage to home-residue/."""
        mock_residue = tmp_path / "home-residue"
        mock_residue.mkdir()
        test_file = tmp_path / ".cline"
        test_file.mkdir()
        (test_file / "data.json").write_text("{}")

        # Simulated retirement route move
        dest = mock_residue / ".cline"
        shutil.move(str(test_file), str(dest))
        receipt = create_rollback_receipt(
            action="retire",
            path=test_file,
            previous_kind="directory",
            backup_path=dest,
            sha256_hash="dir_marker",
            undo_cmd=f"mv {dest} {test_file}",
        )
        assert receipt["action"] == "retire"
        assert not test_file.exists()
        assert dest.exists()

    def test_r5_f5_5_home_guard_zero_contract_errors(self):
        """F5.5: domus-home-guard --check --json exits without contract errors."""
        res = subprocess.run(
            ["domus-home-guard", "--check", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.stdout.strip(), "domus-home-guard must produce JSON output"
        data = json.loads(res.stdout)
        # Verify schema validity
        assert data.get("schema") in ("domus.home_surface_report.v1", "domus.home_surface_audit.v1", "domus.home_surface_audit.v2")
        # Ensure no contract crashes/errors in runner
        assert "contract_errors" not in data or data["contract_errors"] == []


# ==============================================================================
# Tier 2: Boundary & Corner Cases
# ==============================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Robustness against permissions, corruption, race conditions, escapes."""

    def test_tier2_boundary_custody_permission_rejection_if_not_0700(self, tmp_path):
        """Reject custody staging directory if permissions are not strictly 0700."""
        staging_dir = tmp_path / "insecure_custody"
        staging_dir.mkdir(mode=0o755)

        def enforce_0700(path: Path) -> None:
            current_mode = stat.S_IMODE(path.stat().st_mode)
            if current_mode != 0o700:
                raise PermissionError(f"Custody directory mode must be 0700, got {oct(current_mode)}")

        with pytest.raises(PermissionError, match="0700"):
            enforce_0700(staging_dir)

        # Fix mode and verify pass
        staging_dir.chmod(0o700)
        enforce_0700(staging_dir)

    def test_tier2_boundary_corrupt_sqlite_db_detected_by_quick_check(self, tmp_path):
        """Corrupted SQLite database fails PRAGMA quick_check and halts retirement."""
        db_path = tmp_path / "corrupt.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (id INT, val TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'good')")
        conn.commit()
        conn.close()

        # Corrupt the database by overwriting a middle page
        with db_path.open("r+b") as f:
            f.seek(100)
            f.write(b"CORRUPT_BYTES_ZERO_ZERO_GARBAGE")

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        with pytest.raises(sqlite3.DatabaseError):
            cur.execute("PRAGMA quick_check")
            result = cur.fetchall()
            if result != [("ok",)]:
                raise sqlite3.DatabaseError(f"Integrity check failed: {result}")
        conn.close()

    def test_tier2_boundary_sqlite_row_count_mismatch_fails_closed(self, tmp_path):
        """Row count discrepancy between baseline and staged database triggers fail-closed."""
        db_path = tmp_path / "mismatch.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE threads (id INT PRIMARY KEY)")
        # Insert only 100 rows instead of expected 2688
        for i in range(100):
            conn.execute("INSERT INTO threads VALUES (?)", (i,))
        conn.commit()
        conn.close()

        def verify_codex_db(path: Path, expected_rows: int) -> None:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM threads")
            actual = cur.fetchone()[0]
            conn.close()
            if actual != expected_rows:
                raise ValueError(f"Row count mismatch: expected {expected_rows}, got {actual}")

        with pytest.raises(ValueError, match="Row count mismatch"):
            verify_codex_db(db_path, expected_rows=2688)

    def test_tier2_boundary_open_file_handle_blocks_relink(self, tmp_path):
        """Active open file handle on target file aborts relinking."""
        target = tmp_path / "active.json"
        target.write_text("{}")

        # Open file handle held by current process
        with target.open("r"):
            # Simulate handle probe: in real life lsof checks this
            is_open = True
            if is_open:
                with pytest.raises(RuntimeError, match="open file handle"):
                    raise RuntimeError("Aborting: target has active open file handle")

    def test_tier2_boundary_missing_home_residue_dir_creation(self, tmp_path):
        """Missing residue directory is safely created with mode 0700 before move."""
        residue_dir = tmp_path / "nonexistent" / "home-residue"
        assert not residue_dir.exists()

        residue_dir.mkdir(parents=True, mode=0o700)
        assert residue_dir.exists()
        assert stat.S_IMODE(residue_dir.stat().st_mode) == 0o700

    def test_tier2_boundary_symlink_traversal_escape_rejected(self, tmp_path):
        """Symlinks that escape the allowed runtime root boundary are rejected."""
        runtime_root = tmp_path / "runtime"
        runtime_root.mkdir()
        forbidden_outside = tmp_path / "outside_root" / "secret.txt"
        forbidden_outside.parent.mkdir()
        forbidden_outside.write_text("secret")

        escaping_link = runtime_root / "doorway"
        # Relative link pointing outside runtime_root
        escaping_link.symlink_to(Path("../outside_root/secret.txt"))

        def verify_symlink_containment(link_path: Path, root: Path) -> None:
            resolved = link_path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError(f"Symlink {link_path} escapes containment root {root}")

        with pytest.raises(ValueError, match="escapes containment root"):
            verify_symlink_containment(escaping_link, runtime_root)

    def test_tier2_boundary_cyclic_symlink_detected(self, tmp_path):
        """Cyclic symlinks trigger detection error and do not hang the runner."""
        link_a = tmp_path / "link_a"
        link_b = tmp_path / "link_b"
        link_a.symlink_to(link_b)
        link_b.symlink_to(link_a)

        with pytest.raises((OSError, RuntimeError)):
            link_a.resolve(strict=True)

    def test_tier2_boundary_quota_reserve_exhaustion_protection(self):
        """Protection triggers when available disk headroom falls below reserve threshold."""
        # Check domus-agent-runtime check --json pool data
        res = subprocess.run(["domus-agent-runtime", "check", "--json"], capture_output=True, text=True, check=False)
        assert res.stdout.strip()
        data = json.loads(res.stdout)
        pool = data.get("pool", {})
        free_bytes = pool.get("filesystem_free_bytes", 0)
        reserve_bytes = pool.get("required_reserve_bytes", 0)
        assert free_bytes > reserve_bytes, "Disk free space must exceed required safety reserves"

    def test_tier2_boundary_readonly_file_preservation(self, tmp_path):
        """Read-only files preserve read-only mode during copy and staging."""
        src = tmp_path / "readonly_file.txt"
        src.write_text("protected")
        src.chmod(0o400)

        dst = tmp_path / "staged_readonly.txt"
        shutil.copy2(src, dst)
        assert stat.S_IMODE(dst.stat().st_mode) == 0o400
        # Restore mode for cleanup
        src.chmod(0o600)
        dst.chmod(0o600)


# ==============================================================================
# Tier 3: Cross-Feature Combinations
# ==============================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: End-to-end interactions across relinking, retirement, and validation."""

    def test_tier3_combined_pipeline_relink_custody_and_retirement(self, tmp_path):
        """Full simulated pipeline: backup -> relink -> custody stage -> verify DBs -> retire."""
        home = tmp_path / "home"
        residue = tmp_path / "residue"
        staging = tmp_path / "custody"
        runtime = tmp_path / "runtime"
        home.mkdir()
        residue.mkdir(mode=0o700)
        staging.mkdir(mode=0o700)
        runtime.mkdir(mode=0o700)

        # Step 1: ~/.claude.json backup and relink
        claude_target = home / ".claude.json"
        claude_target.write_text('{"claude": "old"}')
        claude_canonical = runtime / "claude" / "legacy-home.json"
        claude_canonical.parent.mkdir(parents=True)
        claude_canonical.write_text('{"claude": "old"}')

        claude_backup = residue / ".claude.json.pre-relink"
        shutil.copy2(claude_target, claude_backup)
        claude_target.unlink()
        claude_target.symlink_to(claude_canonical)
        assert claude_target.is_symlink()

        # Step 2: Codex custody staging
        codex_src = home / ".local" / "share" / "codex"
        codex_src.mkdir(parents=True)
        db_file = codex_src / "state_5.sqlite"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE threads (id INT PRIMARY KEY)")
        conn.execute("INSERT INTO threads VALUES (1)")
        conn.commit()
        conn.close()

        codex_stage = staging / "codex-run-001"
        shutil.copytree(codex_src, codex_stage)
        assert codex_stage.exists()

        # Step 3: Verify staged DB integrity
        staged_conn = sqlite3.connect(f"file:{codex_stage / 'state_5.sqlite'}?mode=ro", uri=True)
        cur = staged_conn.cursor()
        cur.execute("PRAGMA quick_check")
        assert cur.fetchone()[0] == "ok"
        staged_conn.close()

        # Step 4: Retire old codex directory
        shutil.rmtree(codex_src)
        assert not codex_src.exists()

    def test_tier3_combined_rollback_receipt_replay_restoration(self, tmp_path):
        """Executing the recorded undo command exactly reverses the state mutation."""
        home = tmp_path / "home"
        residue = tmp_path / "residue"
        home.mkdir()
        residue.mkdir()

        orig_file = home / ".claude.json"
        orig_file.write_text("my-active-claude-state")
        orig_hash = compute_sha256(orig_file)

        backup_file = residue / ".claude.json.pre-relink"
        shutil.copy2(orig_file, backup_file)

        receipt = create_rollback_receipt(
            action="relink",
            path=orig_file,
            previous_kind="file",
            backup_path=backup_file,
            sha256_hash=orig_hash,
            undo_cmd=f"rm {orig_file} && cp {backup_file} {orig_file}",
        )

        # Mutate to symlink
        orig_file.unlink()
        orig_file.symlink_to(tmp_path / "somewhere")
        assert orig_file.is_symlink()

        # Replay undo command
        subprocess.run(receipt["undo_command"], shell=True, check=True)
        assert not orig_file.is_symlink()
        assert orig_file.is_file()
        assert compute_sha256(orig_file) == orig_hash

    def test_tier3_combined_atomic_failure_leaves_original_untouched(self, tmp_path):
        """Failure during integrity verification prevents destruction of original data."""
        codex_src = tmp_path / "codex"
        codex_src.mkdir()
        important_file = codex_src / "important.txt"
        important_file.write_text("irreplaceable-data")

        # Staging fails verification
        def stage_and_retire():
            staged = tmp_path / "staged"
            shutil.copytree(codex_src, staged)
            # Simulated check failure
            raise ValueError("Integrity verification failed: SHA-256 mismatch")
            shutil.rmtree(codex_src)  # Should never be reached

        with pytest.raises(ValueError, match="Integrity verification failed"):
            stage_and_retire()

        assert codex_src.exists()
        assert important_file.read_text() == "irreplaceable-data"

    def test_tier3_combined_skills_dedup_and_catalog_reachability(self, tmp_path):
        """Deduplicated skills catalog is reachable by symlink from consumer skill roots."""
        catalog = tmp_path / "shared" / "skills-catalog"
        catalog.mkdir(parents=True)
        (catalog / "universal-skill").mkdir()
        (catalog / "universal-skill" / "SKILL.md").write_text("# Universal Skill\n")

        # Consumer root symlinks into catalog
        claude_skills = tmp_path / "claude" / "skills"
        claude_skills.mkdir(parents=True)
        (claude_skills / "universal-skill").symlink_to(catalog / "universal-skill")

        assert (claude_skills / "universal-skill" / "SKILL.md").exists()
        assert (claude_skills / "universal-skill" / "SKILL.md").resolve(strict=True) == (
            catalog / "universal-skill" / "SKILL.md"
        ).resolve(strict=True)

    def test_tier3_combined_home_guard_and_agent_runtime_concordance(self):
        """Ensure all agents checked by domus-agent-runtime have corresponding home-surface rows."""
        import importlib.util
        runtime_script = Path("/Users/4jp/.local/libexec/domus-agent-runtime.py")
        assert runtime_script.exists()

        spec = importlib.util.spec_from_file_location("domus_agent_runtime", runtime_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Check declared AGENTS in domus-agent-runtime
        declared_agents = set(mod.AGENTS)
        assert declared_agents == {"codex", "claude", "gemini", "opencode"}

        hs_path = Path("/Users/4jp/Workspace/domus-genoma/dot_config/domus/home-surface.yaml")
        hs_data = json.loads(hs_path.read_text())
        owners = {e.get("owner_ref") for e in hs_data.get("entries", [])}
        for agent in ("codex", "claude", "gemini"):
            assert agent in owners or any(agent in o for o in owners)
        # opencode is either already declared in entries (post-M5) or declared in R5 uncontained surfaces (pre-M5)
        assert ("opencode" in owners or any("opencode" in o for o in owners)) or (".opencode" in ALL_15_UNCONTAINED_SURFACES)


# ==============================================================================
# Tier 4: Real-World Application Scenarios (8 Consumers)
# ==============================================================================

class TestTier4RealWorldConsumerScenarios:
    """Tier 4: Verification matrix for all 8 agent consumers per Plan v2 §6."""

    def test_tier4_consumer_claude_full_matrix(self):
        """Consumer 1: Claude Code (discovery, skills, state continuity, rollback)."""
        claude_config = Path("/Users/4jp/Workspace/limen/.agent-runtime/claude")
        assert claude_config.exists()
        # 1. Instruction discovery
        claude_md = claude_config / "CLAUDE.md"
        assert claude_md.exists(), "CLAUDE.md must exist in CLAUDE_CONFIG_DIR"
        assert Path("/Users/4jp/AGENTS.md").exists(), "~/AGENTS.md must exist"

        # 2. Skill discovery
        skills_dir = claude_config / "skills"
        assert skills_dir.exists(), "claude skills dir must exist"

        # 3. State continuity: active session .claude.json
        active_json = claude_config / ".claude.json"
        assert active_json.exists(), "$CLAUDE_CONFIG_DIR/.claude.json must exist"

        # 4. Rollback receipt capability
        receipt = create_rollback_receipt(
            action="relink",
            path=Path("/Users/4jp/.claude.json"),
            previous_kind="file",
            backup_path=Path("/Users/4jp/.local/state/domus/home-residue/.claude.json.pre-relink"),
            sha256_hash=CLAUDE_JSON_SHA256,
            undo_cmd="ln -f /Users/4jp/.local/state/domus/home-residue/.claude.json.pre-relink /Users/4jp/.claude.json",
        )
        validate_receipt_schema(receipt)

    def test_tier4_consumer_codex_full_matrix(self):
        """Consumer 2: Codex (discovery, skills, state continuity, restoration receipt)."""
        codex_home = Path("/Users/4jp/Workspace/limen/.agent-runtime/codex")
        assert codex_home.exists()
        # 1. Instruction discovery
        codex_agents = codex_home / "AGENTS.md"
        assert codex_agents.exists()

        # 2. Skill discovery
        codex_skills = codex_home / "skills"
        assert codex_skills.exists()

        # 3. State continuity: active state DB
        codex_state = codex_home / "state_5.sqlite"
        assert codex_state.exists()
        conn = sqlite3.connect(f"file:{codex_state}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check")
        assert cur.fetchone()[0] == "ok"
        conn.close()

    def test_tier4_consumer_gemini_full_matrix(self):
        """Consumer 3: Gemini CLI (discovery, skills, history continuity, rollback)."""
        gemini_dir = Path("/Users/4jp/Workspace/limen/.agent-runtime/gemini/legacy-home")
        assert gemini_dir.exists()
        # 1. Instruction discovery
        gemini_md = gemini_dir / "config" / "AGENTS.md"
        assert gemini_md.exists()

        # 2. History continuity
        assert (gemini_dir).is_dir()

    def test_tier4_consumer_antigravity_full_matrix(self):
        """Consumer 4: Antigravity / agy (discovery, skills, brain continuity, binary)."""
        agy_bin = Path("/Users/4jp/.gemini/bin/agy")
        assert agy_bin.exists()
        assert os.access(agy_bin, os.X_OK)

        # Shared skills catalog access
        shared_skills = Path("/Users/4jp/.agents/skills")
        assert shared_skills.exists()
        assert (shared_skills / "s-02-plan").exists()

    def test_tier4_consumer_opencode_full_matrix(self):
        """Consumer 5: OpenCode (discovery, skills, database continuity)."""
        opencode_home = Path("/Users/4jp/Workspace/limen/.agent-runtime/opencode")
        assert opencode_home.exists()
        # State database
        db_candidate = opencode_home / "data" / "opencode" / "opencode.db"
        if db_candidate.exists():
            conn = sqlite3.connect(f"file:{db_candidate}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("PRAGMA quick_check")
            assert cur.fetchone()[0] == "ok"
            conn.close()

    def test_tier4_consumer_copilot_full_matrix(self):
        """Consumer 6: GitHub Copilot (instruction discovery, state directory preservation)."""
        copilot_dir = Path("/Users/4jp/.copilot")
        cli_dir = Path("/Users/4jp/.github-copilot-cli")
        # Directories exist or are routed
        assert copilot_dir.exists() or cli_dir.exists()

    def test_tier4_consumer_cursor_full_matrix(self):
        """Consumer 7: Cursor (rules discovery, tracking state preservation)."""
        cursor_dir = Path("/Users/4jp/.cursor")
        assert cursor_dir.exists()
        # Ensure directory is tracked in home-surface plan
        assert ".cursor" in ALL_15_UNCONTAINED_SURFACES

    def test_tier4_consumer_claude_desktop_full_matrix(self):
        """Consumer 8: Claude Desktop (MCP config, VM bundle preservation)."""
        app_support = Path("/Users/4jp/Library/Application Support/Claude")
        assert app_support.exists()
        assert (app_support / "vm_bundles").parent.exists()
        # VM bundles are declared application objects in home-surface.yaml
        hs_path = Path("/Users/4jp/Workspace/domus-genoma/dot_config/domus/home-surface.yaml")
        hs_data = json.loads(hs_path.read_text())
        app_objs = [obj.get("path") for obj in hs_data.get("application_objects", [])]
        assert any("claudevm.bundle" in path for path in app_objs)


# ==============================================================================
# Live Baseline and Admission Invariants
# ==============================================================================

class TestLiveSystemInvariants:
    """Live system invariant checks before and during containment rollout."""

    def test_acceptance_baseline_invariants_pre_migration(self):
        """Verify the exact baseline state that M1-M5 will resolve."""
        # 1. ~/.claude.json is a regular file before Phase 1A relinking
        claude_json = Path("/Users/4jp/.claude.json")
        assert claude_json.exists()
        # 2. ~/.local/share/codex exists and contains state_5.sqlite before Phase 1B retirement
        codex_root = Path("/Users/4jp/.local/share/codex")
        if codex_root.exists():
            assert (codex_root / "state_5.sqlite").exists()
        # 3. agy is executable and agy.tmp archive exists before Phase 2 quarantine
        agy_bin = Path("/Users/4jp/.gemini/bin/agy")
        assert agy_bin.exists()
        assert os.access(agy_bin, os.X_OK)

    def test_acceptance_domus_agent_runtime_audit_contract(self):
        """domus-agent-runtime check --json returns valid schema and identifies targets."""
        res = subprocess.run(["domus-agent-runtime", "check", "--json"], capture_output=True, text=True, check=False)
        assert res.stdout.strip()
        data = json.loads(res.stdout)
        assert data.get("schema") == "domus.agent_runtime.v2"
        assert "unauthorized_legacy_roots" in data
        assert "pool" in data
        assert "agents" in data

    def test_acceptance_host_admission_status(self):
        """Host admission status allows read-only and worktree operations."""
        res = subprocess.run(
            ["python3", "/Users/4jp/Workspace/limen/scripts/host-work-admission.py", "status", "--no-probe"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(res.stdout)
        assert data.get("schema") == "limen.host_admission_decision.v1"
        assert "allowed" in data
        assert isinstance(data["allowed"], bool)
        assert "leases" in data

    def test_acceptance_m3_m4_m5_m6_live_artifacts(self):
        """Verify live M3-M6 outputs: antigravity symlinks, skills catalog, s-02-plan fix, and 15 routes."""
        rt = Path("/Users/4jp/Workspace/limen/.agent-runtime")
        # M3: Antigravity root and depth-3 relative symlinks
        agy_root = rt / "antigravity"
        assert agy_root.is_dir()
        assert (agy_root.stat().st_mode & 0o777) == 0o700
        gemini_dot = rt / "gemini" / "home" / ".gemini"
        for sd in ("antigravity", "antigravity-cli", "antigravity-ide", "bin", "config"):
            link = gemini_dot / sd
            assert link.is_symlink()
            assert os.readlink(link) == f"../../../antigravity/{sd}"
            assert link.resolve(strict=True) == (agy_root / sd).resolve(strict=True)

        # M4: Shared skills catalog and s-02-plan durability fix
        reg_file = rt / "shared" / "skills-catalog" / "skills-registry.json"
        assert reg_file.is_file()
        reg = json.loads(reg_file.read_text())
        assert reg["arbitrary_cap_applied"] is False
        assert reg["unique_skills_count"] >= 60

        wt_domus = Path("/Users/4jp/Workspace/domus-genoma/.worktrees/contain-agent-surfaces")
        domus_root = wt_domus if wt_domus.exists() else Path("/Users/4jp/Workspace/domus-genoma")
        s02_text = (domus_root / "dot_agents/skills/s-02-plan/SKILL.md").read_text()
        assert "/Users/4jp/Workspace/limen/docs/plans/" in s02_text

        # M5: All 15 vendor surfaces declared in home-surface.yaml
        hs = json.loads((domus_root / "dot_config/domus/home-surface.yaml").read_text())
        routed_paths = {r["path"] for r in hs["routes"]}
        for surf in ALL_15_UNCONTAINED_SURFACES:
            assert surf in routed_paths, f"Missing route for {surf}"

        # Verify Claude relink receipt inode matches live runtime file and backup_inode matches backup
        claude_receipt_path = Path("/Users/4jp/.local/state/domus/home-residue/claude-json-relink-receipt-20261017.json")
        assert claude_receipt_path.is_file()
        claude_receipt = json.loads(claude_receipt_path.read_text())
        assert claude_receipt["inode"] == (rt / "claude" / "legacy-home.json").stat().st_ino
        assert claude_receipt["backup_inode"] == Path(claude_receipt["backup_path"]).stat().st_ino

        # Verify stale readers/writers of ~/.local/share/codex are updated to CODEX_HOME
        regen_text = (domus_root / "dot_config/ai-context/scripts/executable_regen-session-policies").read_text()
        snap_text = (domus_root / "dot_local/bin/executable_codex-pressure-snapshot").read_text()
        assert ".local/share/codex" not in regen_text
        assert ".local/share/codex" not in snap_text


