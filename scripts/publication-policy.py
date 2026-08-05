#!/usr/bin/env python3
"""publication-policy.py — the ONE disposition engine for "what goes on which repo."

Given (repo visibility) x (content classification), it returns a single disposition
so the answer is always CLEAR and never re-litigated per repo. This converges the
scattered content-safety gates (creds-hydrate `_SECRET_RX`, scan-legacy
`SENSITIVE_PATTERNS`, the persona disclosure contracts, positioning `awaiting_publish`)
behind one rule table instead of a per-repo human judgment call.

DOCTRINE (the source of truth this engine encodes):
  - PII is PROCESSED AND REDACTED, never deleted — owner identifiers scrubbed,
    substance preserved. Redaction is OWNER-SCOPED ONLY, never category-scoped:
    it never uses a bare `@domain` / any-phone wildcard that would eat product
    contacts (`legal@styx.protocol`), UI placeholders (`you@styx.protocol`,
    `partner@example.com`), or fiction-reserved `555` test fixtures. (That bare
    wildcard was the 2026-07 over-redaction bug this engine exists to prevent.)
  - Secrets are NEVER restored to any repo. They are removed + rotated (the
    credential organ owns rotation); the engine only flags them.
  - Subject-matter-sensitive content (internal strategy, raw session artifacts,
    named third parties) on a PUBLIC surface stays OFF the public HEAD — preserved
    in git HISTORY (never deleted from the universe), just not on the live face.
    On a PRIVATE repo the same content is restore-and-redacted (kept, PII-scrubbed).
    On a SHARED (collab) repo it stays off the head too: a private repo is a safe
    home, a tree an invited collaborator can read is not.
  - There are THREE audiences, not two — world / collab / self (2026-07-30). The
    same axis ships as `persona: owner|client|public` in the surface-manifest
    schema; both spellings normalize here (see the matrix header).
  - Autonomy is DERIVED from reversibility (the Censor's constitution): reversible
    -> auto; publish / flip-visibility / send -> his hand (the media-pillar boundary
    "mine, but the publish click is his").

CLI:
  classify <path>                          -> content class + why (path-first, then content)
  disposition --visibility V --class C     -> the one disposition + autonomy
  redact <path> [--apply]                  -> owner-identifier-only redaction (dry by default)
  audit <ledger.json> [--json]             -> run the matrix over a ledger of items
  --verify                                 -> self-test predicate (exit 0 <=> engine sound)
  --check                                  -> cheap stamp/presence check

Fractal: OWNER identity is a NAMED config (macro form works for anyone); the default
instance is Anthony's. Override via env LIMEN_OWNER_IDENTITY (a JSON object).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
STAMP = LOGS / "publication-policy-state.json"

# ---------------------------------------------------------------------------
# OWNER identity (the only thing the redactor is scoped to). Generic underneath,
# his instance as the default. NEVER add a category-wide (@domain / any-phone) rule.
# ---------------------------------------------------------------------------
DEFAULT_OWNER = {
    "handles": ["padavano.anthony", "anthony.padavano"],  # personal-email local parts
    "email_domains": ["gmail.com"],  # a handle is redacted only at these domains (or bare)
    "names": ["Anthony James Padavano", "Anthony Padavano", "Padavano, Anthony"],
    "username": "4jp",  # OS username / path + handle segment
    "phone": None,  # owner's REAL personal number, if ever known. None => no phone redaction.
}


def _owner() -> dict:
    raw = os.environ.get("LIMEN_OWNER_IDENTITY")
    if raw:
        try:
            o = dict(DEFAULT_OWNER)
            o.update(json.loads(raw))
            return o
        except Exception:
            pass
    return dict(DEFAULT_OWNER)


# ---------------------------------------------------------------------------
# Content classification taxonomy
# ---------------------------------------------------------------------------
CLASSES = ("secret", "personal_pii", "internal_strategy", "product_content", "public_safe")

# HARD secret files (path) — these ARE credential material by convention (env/cert/key/tfvars);
# path alone is decisive, content-independent.
_SECRET_PATH = re.compile(
    r"(?:^|/)(?:\.env(?:\.[^/]*)?|[^/]*\.local\.json|settings\.local\.json|"
    r"[^/]*\.pem|[^/]*\.key|[^/]*id_rsa[^/]*|[^/]*\.tfvars)$",
    re.I,
)
# SOFT secret-NAME files — a name saying 'credentials'/'secrets' is USUALLY a store, but can be a
# POLICY REGISTRY / doc that holds no values (institutio/governance/credentials.yaml: vault names +
# routes, values-never-in-repo). Secret only if the content is unavailable (binary/unknown) or
# actually carries a secret shape; a readable, shape-free map falls through to ordinary classification.
_SECRET_NAME_SOFT = re.compile(r"(?:^|/)[^/]*(?:credentials?|secrets?)[^/]*$", re.I)
# secret SHAPES in content (from creds-hydrate.py::_SECRET_RX — the canonical firewall)
_SECRET_RX = re.compile(
    r"AIza[\w\-]{4}[\w\-]+|gh[pousr]_[A-Za-z0-9]{4}[A-Za-z0-9]+|\bapi[_-]?key\b\s*[:=]\s*['\"]?[A-Za-z0-9\-_]{16,}"
)

# internal-strategy signals (path): raw session artifacts / planning / premortem / prompt dumps
_TS_SESSION = re.compile(r"\d{4}-\d{2}-\d{2}-\d{6}-")  # timestamped session dump, e.g. 2026-04-04-145105-*
_STRATEGY_PATH = re.compile(
    r"(?:^|/)(?:\.claude/|\.codex/|"  # agent working dirs
    r"[^/]*prompts?-raw|[^/]*-prompts?\.(?:md|jsonl|txt)|"  # raw prompt dumps
    r"docs/planning/|premortem|"  # planning / premortems
    r"intake/drafts/|"  # raw intake exports
    r"[^/]*transcript[^/]*|[^/]*session[^/]*\.(?:md|txt|jsonl))",  # transcripts / session logs
    re.I,
)

# product content (path): app/source code + their fixtures/tests
_PRODUCT_PATH = re.compile(
    r"\.(?:tsx?|jsx?|py|go|rs|rb|java|kt|swift|c|cc|cpp|h|hpp|css|scss|vue|svelte)$"
    r"|(?:^|/)(?:src|app|lib|components?|pages|tests?|__tests__|fixtures?)/",
    re.I,
)

# env example/template/sample/dist — DOCUMENTATION placeholders (build-in-public config docs),
# not live secrets. A path-shape secret rule below would otherwise flag every `.env.*` regardless
# of content; these carry placeholders (`change-me`, empty), so they are public-safe unless the
# content actually matches a live-secret shape. The example-word may appear anywhere after `.env.`
# (`.env.local.example`, `.env.example.local`) — but a bare `.env.local` (real values) is NOT exempt.
_ENV_EXAMPLE = re.compile(r"(?:^|/)\.env\.[^/]*(?:example|template|sample|dist|defaults)[^/]*$", re.I)

# PLACEHOLDER secret values — a secret SHAPE whose matched value is an obvious example/placeholder,
# not a live credential: security docs that document key patterns (`ghp_xxxx…`, `your_api_key_here`,
# `api_key: "actual-secret-value"`), config templates, etc. TIGHT list (unambiguous markers only) so
# a real high-entropy token (mixed-case, no runs, no marker words) never matches and stays a secret.
_PLACEHOLDER_RX = re.compile(
    r"x{5,}|0{5,}|your[-_]|[-_]here\b|here['\"]|example|change[-_]?me|placeholder|dummy|"
    r"\bfake\b|\bsample\b|redacted|actual[-_]secret|secret[-_ ]?value|token[-_ ]?here|<[^>]*>|\.\.\.",
    re.I,
)


def _has_live_secret(text: str | None) -> bool:
    """True iff `text` carries a secret SHAPE whose value is NOT an obvious placeholder/example.
    Documentation of secret patterns and config templates match the shape but are not live creds;
    a real high-entropy credential contains none of the placeholder markers and still trips this."""
    if not text:
        return False
    return any(not _PLACEHOLDER_RX.search(m.group(0)) for m in _SECRET_RX.finditer(text))


# test / fixture / mock paths — a secret-SHAPED string here is a PLANTED FIXTURE (a secret-scrubber's
# own mock provider errors), never a live credential: real secrets live in the credential organ
# (op:// / ~/.limen.env), never in the tree. Path-scoped exemption only — a shape match on any
# NON-fixture path stays a hard secret (the real-secret catch is never blunted).
_FIXTURE_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|fixtures?|specs?|mocks?|__mocks__)/"
    r"|(?:^|/)(?:test_[^/]+\.py|[^/]+_test\.(?:py|go|js|ts|tsx|sh|rb)|[^/]+\.(?:test|spec)\.[a-z]+|conftest\.py)$",
    re.I,
)


def _is_fixture_path(path: str) -> bool:
    """True where a secret-SHAPED string is a legitimate test fixture, not a live credential."""
    return bool(_FIXTURE_PATH.search(path.replace("\\", "/")))


# owner-personal-identifier content signal (drives personal_pii) — see redactor below
def _has_owner_pii(text: str, owner: dict | None = None) -> bool:
    return _residual_pii(text, owner) is not None


def classify(path: str, text: str | None = None, owner: dict | None = None) -> tuple[str, str]:
    """Return (class, reason). Path-first (cheap, decisive), then content signals."""
    owner = owner or _owner()
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]

    # 0. env example/template/sample — documentation placeholders (build-in-public config docs),
    #    public-safe by convention UNLESS a LIVE-secret shape (non-placeholder) was fat-fingered in.
    if _ENV_EXAMPLE.search(p):
        if _has_live_secret(text):
            return "secret", "content matches a live-secret shape (AIza…/gh?_…/api_key:)"
        return "public_safe", f"env example/template — placeholder config, no live secret ({base})"

    # 1. secret — real credential PATH shape (.env/.pem/.key/.tfvars), never restored anywhere
    if _SECRET_PATH.search(p):
        return "secret", f"secret/credential path shape ({base})"
    # 1b. credential-NAMED file — a store OR a policy registry (values-never-in-repo). Secret only if
    #     content is unavailable (binary/unknown) or carries a LIVE-secret shape; a readable map with
    #     only placeholders (institutio/governance/credentials.yaml) falls through to ordinary class.
    if _SECRET_NAME_SOFT.search(p):
        if text is None or _has_live_secret(text):
            return "secret", f"credential-named file, content unavailable or secret-shaped ({base})"
    # in-content LIVE-secret shape (non-placeholder). On a FIXTURE/test path it is a planted fixture
    # (a scrubber's own mock), NOT a live credential — exempt (product_content). Documentation of key
    # patterns (`ghp_xxxx…`, `your_api_key_here`) is a placeholder and never trips this (see
    # _has_live_secret). On any other path a live shape stays a hard secret (catch never blunted).
    if _has_live_secret(text):
        if _is_fixture_path(p):
            return "product_content", f"secret-shaped test fixture (not a live credential) ({base})"
        return "secret", "content matches a secret shape (AIza…/gh?_…/api_key:)"

    # 2. internal strategy — raw session artifact / planning / premortem / prompt dump
    if _TS_SESSION.search(base):
        return "internal_strategy", f"timestamped raw-session dump ({base})"
    if _STRATEGY_PATH.search(p):
        return "internal_strategy", "path signals raw session/planning/premortem/prompt material"

    # 3. product content — app/source code + its fixtures (never redacted for PII)
    if _PRODUCT_PATH.search(p):
        return "product_content", "source/app/test path — product code + fixtures"

    # 4. personal PII in an otherwise-ordinary doc -> personal_pii (redact identifiers only)
    if text and _has_owner_pii(text, owner):
        return "personal_pii", "contains owner personal identifiers (redact identifiers, keep substance)"

    # 5. everything else is public-safe by default (README, curated docs, data)
    return "public_safe", "no secret / strategy / product / owner-PII signal"


# ---------------------------------------------------------------------------
# Disposition matrix: (audience, class) -> (disposition, autonomy)
#   autonomy: "auto" (reversible, executive) | "his_lever" (publish/flip/rotate = his hand)
#
# THREE audiences, not two (2026-07-30, decision 4 of the PORTVS/ASTRA plan). Every surface faces
# one of: the world, an invited collaborator, or nobody. The estate already ENFORCED the middle
# tier in exactly one place without being able to name it — moat-audit's "a partner's eyes make the
# tree exposed", which applies a zero-Actions-secrets rule to granted repos that world-public repos
# never face, because a push collaborator can exfiltrate via a workflow edit.
#
# ONE vocabulary, three spellings. `spec/contracts/surface-manifest.schema.json` already owns this
# axis as `persona: owner|client|public` (PUBLICATION-POLICY.md convergence row 3). The operator
# names it world|collab|self. Both are accepted as INPUT and normalized here; the table keys stay
# public/collab/private so no shipped row is renamed.
#
#   world  ≡ public  ≡ persona:public      collab ≡ persona:client       self ≡ private ≡ persona:owner
#
# The collab column differs from private in exactly ONE content cell — internal_strategy — and that
# cell is the whole justification for the column: a private repo is a safe home, a SHARED tree is
# not, because premortems, positioning and raw session dumps routinely discuss the very
# collaborator who was invited in.
# ---------------------------------------------------------------------------
DISPOSITIONS = {
    # class            (public,                collab,                 private)
    "secret": {
        "public": ("REMOVE_ROTATE", "his_lever"),  # remove now (auto), rotation is the credential organ + his mint
        # Unchanged, and if anything more urgent: a third party now HOLDS the credential.
        "collab": ("REMOVE_ROTATE", "his_lever"),
        "private": ("REMOVE_ROTATE", "his_lever"),
    },
    "personal_pii": {
        "public": ("REDACT_IDENTIFIERS", "auto"),  # reversible, protective
        # Same ACTION, honest NAME: the redactor is owner-scoped by construction, so on a shared
        # tree it scrubs his identifiers and nothing else. The collaborator's own identifiers are a
        # legitimate resident there; a THIRD party's are not, and nothing redacts them today.
        # Reporting plain REDACT_IDENTIFIERS here would be a false assurance.
        "collab": ("REDACT_OWNER_ONLY", "auto"),
        "private": ("REDACT_IDENTIFIERS", "auto"),
    },
    "internal_strategy": {
        "public": ("KEEP_OFF_PUBLIC_HEAD", "auto"),  # don't restore to public HEAD; history preserves it
        "collab": ("KEEP_OFF_SHARED_HEAD", "auto"),  # a shared tree is NOT a safe home — see the header
        "private": ("RESTORE_REDACT", "auto"),  # private is a safe home: restore + redact identifiers
    },
    "product_content": {
        "public": ("LEAVE", "noop"),  # NEVER redact product emails / placeholders / 555 fixtures
        "collab": ("LEAVE", "noop"),  # it is what the collaborator was invited for
        "private": ("LEAVE", "noop"),
    },
    "public_safe": {
        "public": ("PUBLISH", "his_lever"),  # the publish/flip-visibility click is his
        # Still his. Autonomy derives from the reversibility of the action the disposition NAMES,
        # and PUBLISH names the visibility flip — irreversible and outbound whether or not a
        # collaborator is already inside.
        "collab": ("PUBLISH", "his_lever"),
        "private": ("PUBLISH", "his_lever"),
    },
}

DISPOSITION_DOC = {
    "REMOVE_ROTATE": "Secret — remove from the tree now; rotation is the credential organ + a vendor mint (his).",
    "REDACT_IDENTIFIERS": "Scrub OWNER identifiers only (name/handle/home-path/convo-link); keep all substance.",
    "REDACT_OWNER_ONLY": (
        "Shared tree — scrub OWNER identifiers only. The invited collaborator's own identifiers are a "
        "legitimate resident; THIRD-party identifiers are NOT covered by any redactor and stay unadjudicated."
    ),
    "KEEP_OFF_PUBLIC_HEAD": "Internal strategy on a PUBLIC surface — keep OFF the public HEAD; git history is the residue (not deleted).",
    "KEEP_OFF_SHARED_HEAD": (
        "Internal strategy on a SHARED surface — keep OFF the head an invited collaborator can read. "
        "A private repo is a safe home; a shared one is not (the material routinely discusses them)."
    ),
    "RESTORE_REDACT": "Private repo is a safe home — restore the content and redact owner identifiers.",
    "LEAVE": "Product content (source, product contacts, UI placeholders, synthetic 555/example fixtures) — never touch.",
    "PUBLISH": "Public-safe — publishing / flipping visibility is HIS hand (the media-pillar boundary).",
}

# Every spelling of the three audiences -> the matrix column. `any` (the estate's contrib_fork /
# frozen / archived classes) resolves to the STRICTEST column, never the most permissive.
_AUDIENCE_ALIASES = {
    "public": "public",
    "world": "public",
    "any": "public",
    "collab": "collab",
    "client": "collab",
    "guest": "collab",
    "private": "private",
    "self": "private",
    "owner": "private",
}


def audience_column(audience: str) -> str:
    """Normalize any accepted audience spelling to a matrix column, or die.

    This used to be `"public" if str(v).lower().startswith("pub") else "private"` — which silently
    swallowed EVERY unrecognized value into the *permissive* column. `disposition("world", ...)`
    returned RESTORE_REDACT ("private repo is a safe home") for something actually world-readable:
    the most dangerous cell in the table, reached by a typo. Callers feed this from arbitrary
    ledger JSON (`cmd_audit`) and from argv (`cmd_classify`), so an unknown value is a bug in the
    caller and must say so rather than fail open.
    """
    key = str(audience).strip().lower()
    col = _AUDIENCE_ALIASES.get(key)
    if col is None:
        raise SystemExit(f"unknown audience: {audience!r} (expected one of {sorted(_AUDIENCE_ALIASES)})")
    return col


def disposition(visibility: str, cls: str) -> tuple[str, str]:
    """(disposition, autonomy) for one (audience, class) pair. `visibility` accepts any spelling."""
    if cls not in DISPOSITIONS:
        raise SystemExit(f"unknown class: {cls!r} (expected one of {CLASSES})")
    return DISPOSITIONS[cls][audience_column(visibility)]


# ---------------------------------------------------------------------------
# The CORRECTED redactor — owner-scoped ONLY. Drops the generic EMAIL/PHONE that
# caused the 2026-07 over-redaction. Product emails, placeholders, 555 fixtures,
# and other users' home paths are all preserved.
# ---------------------------------------------------------------------------
def _domain_rx(d: str) -> str:
    """A domain, tolerant of TLD truncation: 'gmail.com' -> 'gmail(?:\\.com)?'
    (real data carries truncated forms like 'padavano.anthony@gmail')."""
    labels = d.split(".")
    pat = re.escape(labels[0])
    for lbl in labels[1:]:
        pat += r"(?:\." + re.escape(lbl)
    return pat + ")?" * (len(labels) - 1)


def _build_patterns(owner: dict):
    handles = "|".join(re.escape(h) for h in owner["handles"])
    domains = "|".join(_domain_rx(d) for d in owner.get("email_domains") or [])
    # handle, optionally @<owner-domain> (bare or TLD-truncated). NOT a bare @wildcard.
    dom = f"(?:@(?:{domains}))?" if domains else ""
    HANDLE = re.compile(rf"(?:{handles}){dom}", re.I) if handles else None
    NAME = re.compile("|".join(re.escape(n) for n in owner["names"])) if owner.get("names") else None
    user = re.escape(owner["username"]) if owner.get("username") else None
    HOME = re.compile(rf"/(?:Users|home)/{user}/") if user else None
    USER = re.compile(rf"(?<![A-Za-z0-9]){user}(?![A-Za-z0-9])") if user else None
    CONVO = re.compile(
        r"https?://(?:chatgpt\.com/(?:g|c|share)/|chat\.openai\.com/|claude\.ai/(?:chat|share)/)[^\s)\]]+"
    )
    PHONE = re.compile(re.escape(owner["phone"])) if owner.get("phone") else None
    return HANDLE, NAME, HOME, USER, CONVO, PHONE


def redact(text: str, owner: dict | None = None) -> str:
    owner = owner or _owner()
    HANDLE, NAME, HOME, USER, CONVO, PHONE = _build_patterns(owner)
    t = CONVO.sub("[personal conversation link redacted]", text)
    if HANDLE:
        t = HANDLE.sub("[email redacted]", t)
    if NAME:
        t = NAME.sub("[name redacted]", t)
    if HOME:
        t = HOME.sub("~/", t)
    if PHONE:
        t = PHONE.sub("[phone redacted]", t)
    if USER:
        t = USER.sub("[user]", t)
    return t


def _residual_pii(text: str, owner: dict | None = None) -> str | None:
    """Return the first surviving owner-identifier, or None if clean."""
    owner = owner or _owner()
    HANDLE, NAME, HOME, USER, CONVO, PHONE = _build_patterns(owner)
    for rx in (CONVO, HANDLE, NAME, HOME, USER, PHONE):
        if rx is None:
            continue
        m = rx.search(text)
        if m:
            return m.group(0)
    return None


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------
def _read_text(path: str) -> str | None:
    try:
        raw = Path(path).read_bytes()
        if b"\x00" in raw[:8192]:
            return None
        return raw.decode("utf-8", "replace")
    except Exception:
        return None


def cmd_classify(args) -> int:
    text = _read_text(args.path)
    cls, why = classify(args.path, text)
    vis = args.visibility
    out = {"path": args.path, "class": cls, "why": why}
    if vis:
        disp, auto = disposition(vis, cls)
        out.update(visibility=vis, disposition=disp, autonomy=auto, means=DISPOSITION_DOC[disp])
    print(json.dumps(out, indent=2))
    return 0


def cmd_disposition(args) -> int:
    disp, auto = disposition(args.visibility, args.cls)
    print(
        json.dumps(
            {
                "visibility": args.visibility,
                "class": args.cls,
                "disposition": disp,
                "autonomy": auto,
                "means": DISPOSITION_DOC[disp],
            },
            indent=2,
        )
    )
    return 0


def cmd_redact(args) -> int:
    text = _read_text(args.path)
    if text is None:
        print("bin")
        return 0
    r = redact(text)
    changed = r != text
    if changed and args.apply:
        Path(args.path).write_text(r, encoding="utf-8")
    resid = _residual_pii(r)
    print(
        json.dumps(
            {
                "path": args.path,
                "changed": changed,
                "applied": bool(args.apply and changed),
                "residual_owner_pii": resid,
            },
            indent=2,
        )
    )
    return 2 if resid else 0


def cmd_audit(args) -> int:
    """Ledger: list of {repo, visibility, class?|path?, note?}. Emits dispositions."""
    items = json.loads(Path(args.ledger).read_text())
    if isinstance(items, dict):
        items = items.get("items") or items.get("repos") or []
    rows = []
    for it in items:
        cls = it.get("class")
        if not cls and it.get("path"):
            cls = classify(it["path"], _read_text(it["path"]) if Path(it["path"]).exists() else None)[0]
        disp, auto = disposition(it["visibility"], cls)
        rows.append(
            {
                "repo": it.get("repo", it.get("path", "?")),
                "visibility": it["visibility"],
                "class": cls,
                "disposition": disp,
                "autonomy": auto,
                "note": it.get("note", ""),
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        w = max((len(r["repo"]) for r in rows), default=4)
        for r in rows:
            print(f"{r['repo']:<{w}}  {r['visibility']:<7}  {r['class']:<17}  {r['disposition']:<22}  {r['autonomy']}")
    return 0


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Convergence integrity — verify every scattered gate still references this rule table
# ---------------------------------------------------------------------------
_CONVERGENCE_GATES: list[tuple[str, str]] = [
    ("scripts/creds-hydrate.py", "_SECRET_RX"),
    ("scripts/scan-legacy-session-batch.py", "SENSITIVE_PATTERNS"),
    ("spec/contracts/surface-manifest.schema.json", "persona contracts"),
    ("scripts/generate-positioning.py", "awaiting_publish"),
]

GATE_REF = "PUBLICATION-POLICY.md"


def _check_convergence() -> list[str]:
    """Verify every scattered gate still references PUBLICATION-POLICY.md (the convergence table)."""
    fails = []
    for rel_path, gate_name in _CONVERGENCE_GATES:
        target = ROOT / rel_path
        if not target.exists():
            fails.append(
                f"convergence: {rel_path} — file missing; convergence table row ({gate_name}) cannot be verified"
            )
            continue
        if GATE_REF not in target.read_text(encoding="utf-8", errors="replace"):
            fails.append(
                f"convergence: {rel_path} — file no longer references {GATE_REF}; "
                f"convergence table row '{gate_name}' has drifted"
            )
    return fails


def _self_test() -> list[str]:
    """Return a list of failure strings (empty => sound)."""
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    o = dict(DEFAULT_OWNER)
    # 1. redactor scrubs OWNER identifiers
    check(redact("mail padavano.anthony@gmail.com", o) == "mail [email redacted]", "owner email not redacted")
    check(redact("by Anthony Padavano", o) == "by [name redacted]", "owner name not redacted")
    check(redact("path /Users/4jp/x/y", o) == "path ~/x/y", "owner home path not normalized")
    check(redact("user 4jp done", o) == "user [user] done", "owner username token not redacted")
    check(
        "[personal conversation link redacted]" in redact("see https://claude.ai/share/abc123", o),
        "personal convo link not redacted",
    )
    # 2. redactor PRESERVES product content, placeholders, fixtures, other users
    for keep in (
        "legal@styx.protocol",
        "you@styx.protocol",
        "partner@example.com",
        "buyer@example.com",
        "test@example.com",
        "555-111-2222",
        "(555) 867-5309",
        "/Users/someoneelse/repo",
    ):
        check(keep in redact(f"x {keep} y", o), f"OVER-REDACTED product/fixture content: {keep}")
    # 3. classifier signals
    check(
        classify("out/2026-04-04-145105-define-workspace.txt")[0] == "internal_strategy",
        "timestamped session dump not classed internal_strategy",
    )
    check(classify("docs/planning/premortem-x.md")[0] == "internal_strategy", "premortem not internal_strategy")
    check(classify("web/app/src/pages/login/page.tsx")[0] == "product_content", "source not product_content")
    check(classify(".env.production")[0] == "secret", ".env not secret")
    check(classify("moneta/.env")[0] == "secret", ".env (nested) not secret")
    check(classify("README.md")[0] == "public_safe", "README not public_safe")
    check(
        classify("notes.md", "reach me at padavano.anthony@gmail.com")[0] == "personal_pii",
        "owner-PII doc not personal_pii",
    )
    check(
        classify("notes.md", "contact legal@styx.protocol")[0] == "public_safe",
        "product-email doc wrongly classed as PII",
    )
    # 3b. calibration — build-in-public false-positives must NOT block; real secrets STILL must.
    #     The secret-SHAPED fixtures below are assembled from parts so this gate never flags its OWN
    #     source (a leak-gate must not trip on its own test fixtures); the string only exists, and
    #     only matches _SECRET_RX, at runtime — never contiguously in this file's blob.
    #     LIVE = high-entropy shapes (no placeholder markers); assembled so this file's own blob never
    #     carries a contiguous match. Placeholder values below are safe as literals — they never trip.
    _aiza = "AIza" + "SyC08Pb1Vk9mQ2rTx7Lz3Hn6Wd4Fg8Jp"  # AIzaSy… LIVE-key shape, high-entropy
    _ghlive = "gho" + "_R4bH9uuzBq7OvTu85pl7HMIb7kyWNoC4dMz"  # gho_… LIVE token, high-entropy
    check(classify(".env.example")[0] == "public_safe", "env.example placeholder wrongly classed secret")
    check(classify("moneta/.env.template")[0] == "public_safe", "env.template placeholder wrongly classed secret")
    check(classify(".env.local.example")[0] == "public_safe", ".env.local.example variant wrongly classed secret")
    check(
        classify(".env.example", "GEMINI_API_KEY=" + _aiza)[0] == "secret",
        "env.example with a LIVE secret shape must still be secret",
    )
    check(
        classify("cli/tests/test_creds_hydrate.py", "api_key:" + _aiza)[0] == "product_content",
        "LIVE secret shape in a test fixture wrongly classed secret (should be product_content)",
    )
    # placeholder / documentation shapes must NOT be flagged (the secret-patterns.md false-positive class)
    check(
        classify("references/secret-patterns.md", "example: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")[0]
        == "public_safe",
        "placeholder ghp_xxxx documentation wrongly classed secret",
    )
    check(
        classify("skills/x/SKILL.md", 'api_key = "your_api_key_here"')[0] == "public_safe",
        "placeholder your_api_key_here wrongly classed secret",
    )
    check(
        classify("doc.md", 'api_key: "actual-secret-value"')[0] == "public_safe",
        "placeholder actual-secret-value wrongly classed secret",
    )
    # THE SMOKE GUARD — a real high-entropy token on a NON-fixture path must STILL be a hard secret.
    check(
        classify("web/api/config.py", "token=" + _ghlive)[0] == "secret",
        "REGRESSION: recalibration blunted the real-secret catch on a non-fixture path",
    )
    check(
        classify("references/secret-patterns.md", "leaked: " + _ghlive)[0] == "secret",
        "a LIVE token in a documentation file must still be secret",
    )
    # 3c. credential-NAMED files: a values-free POLICY registry is public; a store / unknown stays secret
    check(
        classify("app/config/credentials.json")[0] == "secret",
        "credential-named file with unknown content must stay secret",
    )
    check(
        classify(
            "institutio/governance/credentials.yaml",
            "automation_vault: Limen-Automation\nservice_account:\n  name: limen-fleet",
        )[0]
        == "public_safe",
        "values-free credential POLICY registry wrongly classed secret",
    )
    check(
        classify("app/secrets.json", "gh_token=" + _ghlive)[0] == "secret",
        "credential-named file carrying a LIVE secret shape must stay secret",
    )
    # 4. disposition matrix invariants
    check(disposition("PUBLIC", "internal_strategy")[0] == "KEEP_OFF_PUBLIC_HEAD", "public strategy disposition wrong")
    check(disposition("private", "internal_strategy")[0] == "RESTORE_REDACT", "private strategy disposition wrong")
    check(disposition("PUBLIC", "product_content") == ("LEAVE", "noop"), "product disposition wrong")
    check(disposition("PUBLIC", "secret")[0] == "REMOVE_ROTATE", "secret disposition wrong")
    check(disposition("PUBLIC", "public_safe") == ("PUBLISH", "his_lever"), "publish disposition wrong")
    check(disposition("PUBLIC", "personal_pii") == ("REDACT_IDENTIFIERS", "auto"), "pii disposition wrong")
    # 4b. the collab column — the middle audience the estate enforced without naming (2026-07-30).
    # The cell that justifies the column: a SHARED tree is not the safe home a private repo is.
    check(
        disposition("collab", "internal_strategy") == ("KEEP_OFF_SHARED_HEAD", "auto"),
        "collab strategy must stay off a shared head — a collaborator's tree is not a safe home",
    )
    check(
        disposition("collab", "personal_pii") == ("REDACT_OWNER_ONLY", "auto"),
        "collab PII must name the third-party gap, not report blanket REDACT_IDENTIFIERS",
    )
    check(disposition("collab", "secret")[0] == "REMOVE_ROTATE", "collab secret must never soften")
    check(
        disposition("collab", "public_safe") == ("PUBLISH", "his_lever"),
        "an already-invited collaborator does not make the PUBLIC flip reversible",
    )
    check(disposition("collab", "product_content") == ("LEAVE", "noop"), "collab product disposition wrong")
    # 4c. one axis, three spellings — his world|collab|self and the shipped persona|client|owner
    # must land on the same cells, or the estate is running two vocabularies through one engine.
    for a, b in (("world", "public"), ("client", "collab"), ("owner", "private"), ("self", "private")):
        for cls_ in CLASSES:
            check(
                disposition(a, cls_) == disposition(b, cls_),
                f"audience alias {a!r} must resolve identically to {b!r} for {cls_}",
            )
    # 4d. fail-CLOSED on an unknown audience. This was the live fail-open: anything not starting
    # with "pub" collapsed to the permissive private column, so a typo bought RESTORE_REDACT
    # ("safe home") on a world-readable tree. `any` must resolve to the STRICTEST column, not the
    # loosest — verified against internal_strategy, the only row where the columns disagree.
    check(
        disposition("any", "internal_strategy")[0] == "KEEP_OFF_PUBLIC_HEAD",
        "visibility 'any' must resolve to the strictest column",
    )
    try:
        disposition("wrold", "secret")
        check(False, "an unknown audience must raise, never collapse into a column")
    except SystemExit:
        pass
    # 5. convergence integrity — scattered gates still reference this rule table
    fails.extend(_check_convergence())
    return fails


def _stamp(ok: bool, note: str = "") -> None:
    try:
        LOGS.mkdir(exist_ok=True)
        STAMP.write_text(
            json.dumps(
                {
                    "ran_at": datetime.now().isoformat(timespec="seconds"),
                    "sound": ok,
                    "classes": list(CLASSES),
                    "note": note,
                },
                indent=2,
            )
        )
        vd = LOGS / ".voice"
        vd.mkdir(exist_ok=True)
        (vd / "pubpolicy").write_text(datetime.now().isoformat(timespec="seconds"))
    except Exception:
        pass


def cmd_verify(_args) -> int:
    fails = _self_test()
    _stamp(not fails, "verify")
    if fails:
        print("publication-policy UNSOUND:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("publication-policy sound: redactor owner-scoped, matrix + classifier verified")
    return 0


def cmd_check(_args) -> int:
    fresh = STAMP.exists()
    print(f"stamp={'present' if fresh else 'absent'} ({STAMP})")
    return 0 if fresh else 1


def census() -> dict:
    """Counts-only public census; no owner identifiers, sample text, paths, or raw policy bodies."""
    owner = _owner()
    return {
        "classes": len(CLASSES),
        "disposition_rows": sum(len(rows) for rows in DISPOSITIONS.values()),
        "disposition_docs": len(DISPOSITION_DOC),
        "convergence_gates": len(_CONVERGENCE_GATES),
        "convergence_failures": len(_check_convergence()),
        "owner_scope_shape": {
            "handles": len(owner.get("handles") or []),
            "email_domains": len(owner.get("email_domains") or []),
            "names": len(owner.get("names") or []),
            "username_configured": bool(owner.get("username")),
            "phone_configured": bool(owner.get("phone")),
        },
        "stamp_present": STAMP.exists(),
    }


def cmd_census(_args) -> int:
    print(json.dumps(census(), indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="publication-policy — the disposition engine")
    ap.add_argument("--verify", action="store_true", help="self-test predicate (exit 0 <=> sound)")
    ap.add_argument("--check", action="store_true", help="cheap stamp presence check")
    ap.add_argument("--census", action="store_true", help="counts-only public census JSON")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("classify")
    c.add_argument("path")
    c.add_argument("--visibility", default=None)
    d = sub.add_parser("disposition")
    d.add_argument("--visibility", required=True)
    d.add_argument("--class", dest="cls", required=True)
    r = sub.add_parser("redact")
    r.add_argument("path")
    r.add_argument("--apply", action="store_true")
    a = sub.add_parser("audit")
    a.add_argument("ledger")
    a.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.verify:
        return cmd_verify(args)
    if args.check:
        return cmd_check(args)
    if args.census:
        return cmd_census(args)
    if args.cmd == "classify":
        return cmd_classify(args)
    if args.cmd == "disposition":
        return cmd_disposition(args)
    if args.cmd == "redact":
        return cmd_redact(args)
    if args.cmd == "audit":
        return cmd_audit(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
