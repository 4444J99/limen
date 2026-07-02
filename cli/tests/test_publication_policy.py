"""Tests for scripts/publication-policy.py — the content disposition engine.

The load-bearing guarantee is that the redactor is OWNER-SCOPED, never
category-scoped: it must NOT eat product emails, UI placeholders, or the
fiction-reserved 555 fixtures (the 2026-07 over-redaction bug). And the
disposition matrix must be deterministic so "the answer is clear" per repo.
"""

import importlib.util
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
        ("mail <owner-email> now", "mail [email redacted] now"),
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
        ("notes.md", "reach me at <owner-email>", "personal_pii"),
        ("notes.md", "contact legal@styx.protocol for terms", "public_safe"),
    ],
)
def test_classify(path, text, cls):
    assert pp.classify(path, text)[0] == cls


def test_secret_shape_in_content():
    assert pp.classify("random.txt", "token=ghp_ABCD1234ABCD1234ABCD")[0] == "secret"


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
    ],
)
def test_disposition(vis, cls, disp, auto):
    assert pp.disposition(vis, cls) == (disp, auto)


def test_self_test_passes():
    assert pp._self_test() == []


def test_residual_pii_detects_and_clears():
    assert pp._residual_pii("Anthony Padavano here") is not None
    assert pp._residual_pii(pp.redact("Anthony Padavano here")) is None
