"""Tests for scripts/publication-policy.py — the content disposition engine.

The load-bearing guarantee is that the redactor is OWNER-SCOPED, never
category-scoped: it must NOT eat product emails, UI placeholders, or the
fiction-reserved 555 fixtures (the 2026-07 over-redaction bug). And the
disposition matrix must be deterministic so "the answer is clear" per repo.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("publication_policy", ROOT / "scripts" / "publication-policy.py")
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)


# --- the redactor scrubs OWNER identifiers -----------------------------------
@pytest.mark.parametrize(
    "src,want",
    [
        ("mail padavano.anthony@gmail.com now", "mail [email redacted] now"),
        ("anthony.padavano@gmail", "[email redacted]"),
        ("by Anthony Padavano", "by [name redacted]"),
        ("Padavano, Anthony", "[name redacted]"),
        ("/Users/4jp/Workspace/x", "~/Workspace/x"),
        ("/home/4jp/x", "~/x"),
        ("the 4jp user", "the [user] user"),
    ],
)
def test_owner_identifiers_redacted(src, want):
    assert pp.redact(src) == want


def test_personal_conversation_links_redacted():
    assert "[personal conversation link redacted]" in pp.redact("see https://claude.ai/share/abc")
    assert "[personal conversation link redacted]" in pp.redact("g https://chatgpt.com/g/xyz")


# --- the redactor PRESERVES product content (the bug this engine prevents) ----
@pytest.mark.parametrize(
    "keep",
    [
        "legal@styx.protocol",  # product contact
        "you@styx.protocol",  # UI placeholder
        "partner@example.com",  # placeholder
        "buyer@example.com",  # test fixture
        "leads@example.com",
        "test@example.com",
        "555-111-2222",  # fiction-reserved phone fixture
        "(555) 867-5309",
        "/Users/someoneelse/repo",  # a DIFFERENT user's home path
    ],
)
def test_product_and_fixtures_preserved(keep):
    out = pp.redact(f"prefix {keep} suffix")
    assert keep in out, f"over-redacted: {keep!r} -> {out!r}"
    assert "redacted" not in out


def test_no_owner_phone_means_no_phone_redaction():
    # owner phone is unset by default -> NO phone is ever touched
    assert pp.redact("call 347-555-0100") == "call 347-555-0100"


def test_owner_phone_when_configured():
    owner = dict(pp.DEFAULT_OWNER, phone="347-555-0100")
    assert pp.redact("call 347-555-0100", owner) == "call [phone redacted]"
    # still leaves an unrelated number
    assert pp.redact("other 212-555-9999", owner) == "other 212-555-9999"


# --- classifier --------------------------------------------------------------
@pytest.mark.parametrize(
    "path,text,cls",
    [
        ("out/2026-04-04-145105-define-workspace.txt", None, "internal_strategy"),
        ("docs/planning/premortem-x.md", None, "internal_strategy"),
        (".codex/plans/gtm-role-prompts.md", None, "internal_strategy"),
        ("corpus-prompts.md", None, "internal_strategy"),
        ("web/app/src/pages/login/page.tsx", None, "product_content"),
        ("cli/tests/test_x.py", None, "product_content"),
        (".env.production", None, "secret"),
        ("moneta/.env", None, "secret"),
        ("app/config/credentials.json", None, "secret"),
        ("README.md", None, "public_safe"),
        ("data/leads.csv", None, "public_safe"),
        ("notes.md", "reach me at padavano.anthony@gmail.com", "personal_pii"),
        ("notes.md", "contact legal@styx.protocol for terms", "public_safe"),
        # calibration: env-example/template are build-in-public config DOCS (placeholders), not secrets
        (".env.example", None, "public_safe"),
        ("moneta/.env.template", None, "public_safe"),
        # a REAL secret shape fat-fingered into an example must STILL be secret
        (".env.example", "GEMINI_API_KEY=ghp_ABCD1234ABCD1234ABCD", "secret"),
        # a secret SHAPE on a fixture/test path is a planted fixture (scrubber mock), not a live cred
        ("cli/tests/test_creds.py", "token=ghp_ABCD1234ABCD1234ABCD", "product_content"),
        ("scripts/tests/x.test.sh", "api_key: 'ghp_ABCD1234ABCD1234ABCD'", "product_content"),
        # …but the SAME shape on a NON-fixture source path stays a hard secret (catch not blunted)
        ("web/api/config.py", "token=ghp_ABCD1234ABCD1234ABCD", "secret"),
        # credential-NAMED files: a values-free POLICY registry is public; a store / unknown stays secret
        ("institutio/governance/credentials.yaml", "automation_vault: X\nservice_account:\n  name: y", "public_safe"),
        ("config/secrets.json", "api_key: 'ghp_ABCD1234ABCD1234ABCD'", "secret"),
        # env-example VARIANTS (.local infix) are placeholders, not secrets; bare .env.local is NOT exempt
        (".env.local.example", None, "public_safe"),
        # PLACEHOLDER secret shapes (docs that DOCUMENT key patterns) are not live credentials
        ("references/secret-patterns.md", "example ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "public_safe"),
        ("skills/x/SKILL.md", 'api_key = "your_api_key_here"', "public_safe"),
        ("doc.md", 'api_key: "actual-secret-value"', "public_safe"),
        # …but a real high-entropy token stays a hard secret, even in a documentation file
        ("references/secret-patterns.md", "leaked gho_Zx7Kq2Wm9Bn4Vc6Rt1Yp3Lf8Hs5Jd0Gg", "secret"),
    ],
)
def test_classify(path, text, cls):
    assert pp.classify(path, text)[0] == cls


def test_secret_shape_in_content():
    assert pp.classify("random.txt", "token=ghp_ABCD1234ABCD1234ABCD")[0] == "secret"


def test_has_live_secret_excludes_placeholders_keeps_real():
    # placeholders / documentation → not live
    assert not pp._has_live_secret("ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    assert not pp._has_live_secret('api_key = "your_api_key_here"')
    assert not pp._has_live_secret('api_key: "actual-secret-value"')
    # real high-entropy tokens → live (catch never blunted)
    assert pp._has_live_secret("token gho_Zx7Kq2Wm9Bn4Vc6Rt1Yp3Lf8Hs5Jd0Gg")
    assert pp._has_live_secret("key=AIzaSyC08Pb1Vk9mQ2rTx7Lz3Hn6Wd4Fg8Jp")


def test_fixture_path_helper():
    assert pp._is_fixture_path("cli/tests/test_x.py")
    assert pp._is_fixture_path("scripts/tests/publish-flip.test.sh")
    assert not pp._is_fixture_path("web/api/config.py")


# --- disposition matrix ------------------------------------------------------
@pytest.mark.parametrize(
    "vis,cls,disp,auto",
    [
        ("PUBLIC", "internal_strategy", "KEEP_OFF_PUBLIC_HEAD", "auto"),
        ("private", "internal_strategy", "RESTORE_REDACT", "auto"),
        ("PUBLIC", "product_content", "LEAVE", "noop"),
        ("private", "product_content", "LEAVE", "noop"),
        ("PUBLIC", "secret", "REMOVE_ROTATE", "his_lever"),
        ("PUBLIC", "public_safe", "PUBLISH", "his_lever"),
        ("PUBLIC", "personal_pii", "REDACT_IDENTIFIERS", "auto"),
        # the collab audience (2026-07-30) — the middle tier the estate enforced before it could
        # name it. internal_strategy is the ONLY row where it differs from private, and that
        # difference is the whole reason the column exists.
        ("collab", "internal_strategy", "KEEP_OFF_SHARED_HEAD", "auto"),
        ("collab", "personal_pii", "REDACT_OWNER_ONLY", "auto"),
        ("collab", "secret", "REMOVE_ROTATE", "his_lever"),
        ("collab", "public_safe", "PUBLISH", "his_lever"),
        ("collab", "product_content", "LEAVE", "noop"),
        # his spellings and the shipped persona spellings are the same axis
        ("world", "internal_strategy", "KEEP_OFF_PUBLIC_HEAD", "auto"),
        ("self", "internal_strategy", "RESTORE_REDACT", "auto"),
        ("owner", "internal_strategy", "RESTORE_REDACT", "auto"),
        ("client", "internal_strategy", "KEEP_OFF_SHARED_HEAD", "auto"),
        # `any` (contrib_fork / frozen / archived) resolves to the STRICTEST column, not the loosest
        ("any", "internal_strategy", "KEEP_OFF_PUBLIC_HEAD", "auto"),
    ],
)
def test_disposition(vis, cls, disp, auto):
    assert pp.disposition(vis, cls) == (disp, auto)


def test_unknown_audience_fails_closed():
    """The pre-2026-07-30 normalizer collapsed anything not starting with "pub" into the PRIVATE
    column, so a typo silently bought RESTORE_REDACT ("a private repo is a safe home") on a
    world-readable tree — the most permissive cell, reached by a misspelling. It must raise."""
    with pytest.raises(SystemExit):
        pp.disposition("wrold", "internal_strategy")
    with pytest.raises(SystemExit):
        pp.disposition("", "secret")


def test_self_test_passes():
    assert pp._self_test() == []


def test_residual_pii_detects_and_clears():
    assert pp._residual_pii("Anthony Padavano here") is not None
    assert pp._residual_pii(pp.redact("Anthony Padavano here")) is None


def test_census_is_counts_only():
    census = pp.census()
    encoded = json.dumps(census, sort_keys=True)

    assert census["classes"] == len(pp.CLASSES)
    assert census["disposition_rows"] == 15  # 5 classes x 3 audiences (world/collab/self)
    assert census["convergence_gates"] == len(pp._CONVERGENCE_GATES)
    assert "Anthony" not in encoded
    assert "padavano" not in encoded.lower()
    assert "gmail" not in encoded.lower()
