"""codex-skill-slim: distill EVERY loaded Codex skill/plugin description under a derived cap.

Codex loads skill metadata from every cached marketplace plugin — not just the ones enabled in
config.toml — plus ~/.codex/skills and ~/.codex/memories/skills, and divides a fixed char budget
across them (its render log: budget_limit=5440 total_skills=133 → ~169 chars/skill). The first
version scoped to enabled plugins at a hardcoded 240-char cap and left the warning firing on ~132
descriptions. These lock the fix: the enumerator sees ALL cached plugins regardless of enablement,
and the cap is DERIVED worst-case (budget ÷ the larger of Codex's skill count and ours) so no subset
Codex loads — today or after it caches more plugins — can overflow. Distillation keeps every skill.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "codex-skill-slim.py"
    spec = importlib.util.spec_from_file_location("codex_skill_slim", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _skill(dirpath: Path, name: str, desc: str) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\nbody\n", encoding="utf-8")


def _synthetic_home(tmp: Path) -> Path:
    """A ~/.codex with two UN-enabled marketplace plugins + a user skill + a memory skill."""
    cache = tmp / "plugins" / "cache"
    # marketplace plugin A (.codex-plugin layout), versioned, NOT listed in config.toml
    a = cache / "openai-curated-remote" / "vercel" / "1.0.0"
    (a / ".codex-plugin").mkdir(parents=True)
    (a / ".codex-plugin" / "plugin.json").write_text(
        '{"name": "vercel", "description": "' + "x " * 200 + '"}', encoding="utf-8"
    )
    _skill(a / "skills" / "nextjs", "nextjs", "y " * 200)
    # marketplace plugin B (.claude-plugin layout)
    b = cache / "openai-curated-remote" / "investment-banking" / "0.1.27"
    (b / ".claude-plugin").mkdir(parents=True)
    (b / ".claude-plugin" / "plugin.json").write_text('{"name": "ib", "description": "short"}', encoding="utf-8")
    _skill(b / "skills" / "tearsheet", "tearsheet", "z " * 200)
    # user + memory skills
    _skill(tmp / "skills" / "userskill", "userskill", "w " * 200)
    _skill(tmp / "memories" / "skills" / "memskill", "memskill", "v " * 200)
    # config.toml enables NOTHING from those markets (proves enablement does not gate loading)
    (tmp / "config.toml").write_text('[plugins."documents@openai-primary-runtime"]\nenabled = true\n', encoding="utf-8")
    return tmp


def _point_at(mod, home: Path) -> None:
    mod.CODEX_HOME = home
    mod.CACHE = home / "plugins" / "cache"
    mod.LEDGER = home / ".skill-slim" / "backup.json"
    mod.LOGDB = home / "logs_2.sqlite"


def _write_trunc_log(home: Path, ts: int, total_skills: int = 133, chars_per_skill: int = 169) -> None:
    """Seed a synthetic Codex render log with one 'truncated skill metadata' row at epoch `ts`."""
    import sqlite3

    con = sqlite3.connect(home / "logs_2.sqlite")
    try:
        con.execute("CREATE TABLE IF NOT EXISTS logs (ts INTEGER, feedback_log_body TEXT)")
        body = (
            "truncated skill metadata to fit skills context budget "
            f"budget_limit=5440 total_skills={total_skills} "
            f"truncated_description_chars_per_skill={chars_per_skill} truncated_skill_descriptions=132"
        )
        con.execute("INSERT INTO logs (ts, feedback_log_body) VALUES (?, ?)", (ts, body))
        con.commit()
    finally:
        con.close()


# ── scope: every cached plugin, not just enabled ─────────────────────────────────────────────────
def test_targets_enumerate_all_cached_plugins_not_just_enabled(tmp_path):
    mod = _load()
    _point_at(mod, _synthetic_home(tmp_path))
    ids = {t["id"] for t in mod.targets()}
    # skills from BOTH un-enabled marketplace plugins are enumerated (id = "{plugin}:{skill}")…
    assert "vercel:nextjs" in ids
    assert "investment-banking:tearsheet" in ids
    # …plus the user and memory skills, and both plugin.json descriptions
    assert "userskill" in ids and "memskill" in ids
    assert "openai-curated-remote/vercel" in ids  # plugin.desc target
    kinds = {t["kind"] for t in mod.targets()}
    assert {"plug.skill", "user.skill", "mem.skill", "plugin.desc"} <= kinds


# ── cap: derived worst-case from the budget, not hardcoded ────────────────────────────────────────
def test_derive_cap_worst_case_from_logged_budget(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "CAP_OVERRIDE", None)
    # Codex logged 169 chars/skill across 133 skills → 22477-char budget. Worst-case N=182 → 111.
    monkeypatch.setattr(
        mod, "codex_skill_budget", lambda: {"chars_per_skill": 169, "total_skills": 133, "budget_tokens": 5440}
    )
    assert mod.derive_cap(182) == int(169 * 133 / 182 * 0.9) == 111
    # a LARGER logged skill-count than ours still wins the divisor (worst case)
    assert mod.derive_cap(10) == int(169 * 133 / 133 * 0.9)


def test_derive_cap_override_and_fallback(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "codex_skill_budget", lambda: None)  # no logs
    monkeypatch.setattr(mod, "CAP_OVERRIDE", "200")
    assert mod.derive_cap(182) == 200  # explicit override wins
    monkeypatch.setattr(mod, "CAP_OVERRIDE", None)
    # no logs → token-ratio fallback, still clamped into [60, 240]
    cap = mod.derive_cap(182)
    assert 60 <= cap <= 240


# ── distill: thin under the cap, keep the lead, no dangling tail ──────────────────────────────────
def test_distill_respects_cap_and_keeps_lead():
    mod = _load()
    text = "Deploy apps to the edge. Use when building, shipping, or debugging — routing, caching, and more."
    out = mod.distill(text, cap=48)
    assert len(out) <= 48
    assert out.startswith("Deploy apps to the edge")
    assert not out.endswith(("—", "-", ",", "(", "and", "with"))


def test_distill_leaves_short_text_untouched():
    mod = _load()
    assert mod.distill("Already thin.", cap=111) == "Already thin."


# ── apply/restore round-trip is idempotent and reversible ────────────────────────────────────────
def test_apply_is_idempotent_and_restorable(tmp_path, monkeypatch):
    mod = _load()
    _point_at(mod, _synthetic_home(tmp_path))
    monkeypatch.setattr(mod, "CAP_OVERRIDE", "80")  # deterministic cap for the test
    skill = tmp_path / "skills" / "userskill" / "SKILL.md"
    target = {"path": skill, "field": "yaml:description"}
    orig_value = mod._get(target)

    assert mod.run("apply", quiet=True) == 0
    assert len(mod._get(target)) <= 80 < len(orig_value)  # slimmed under cap
    assert mod.run("check", quiet=True) == 0  # everything now ≤ cap

    # second apply changes nothing on disk (fixed point)
    before = skill.read_text()
    assert mod.run("apply", quiet=True) == 0
    assert skill.read_text() == before

    # restore brings the original description VALUE back (re-emitted as a quoted scalar)
    assert mod.run("restore", quiet=True) == 0
    assert mod._get(target) == orig_value


# ── check is confirmed against Codex's emission, not just our own cap ─────────────────────────────
def test_check_fails_when_codex_truncated_after_last_slim(tmp_path, monkeypatch):
    """The anti-false-green lock: even with every description UNDER our cap, if Codex's own log shows
    it truncated AFTER the last slim, --check must fail — the witness overrides the proxy."""
    mod = _load()
    _point_at(mod, _synthetic_home(tmp_path))
    monkeypatch.setattr(mod, "CAP_OVERRIDE", "80")  # fixed cap so the proxy half is deterministically clean

    assert mod.run("apply", quiet=True) == 0  # writes the ledger → its mtime is the "last slim" instant
    applied_at = mod.LEDGER.stat().st_mtime
    # Codex truncated AFTER we slimmed → our cap is proven too loose, regardless of the byte-count.
    _write_trunc_log(tmp_path, ts=int(applied_at) + 1000)
    assert mod.run("check", quiet=True) == 1  # ground truth fails the check even though nothing is over-cap


def test_check_passes_when_no_truncation_since_slim(tmp_path, monkeypatch):
    """Same setup, but Codex's latest truncation PREDATES the slim → the fix held → --check is green."""
    mod = _load()
    _point_at(mod, _synthetic_home(tmp_path))
    monkeypatch.setattr(mod, "CAP_OVERRIDE", "80")

    assert mod.run("apply", quiet=True) == 0
    applied_at = mod.LEDGER.stat().st_mtime
    _write_trunc_log(tmp_path, ts=int(applied_at) - 1000)  # last truncation was before we slimmed
    assert mod.run("check", quiet=True) == 0
