"""census — the single register of model vendors and their standing.

In Rome the *censor* (the governance organ that already lives in this system) conducted the
*census*: the register that assessed each citizen's **class** (→ our model tier) and **means**
(→ our token/run budget). This module is that register for the fleet's AI vendors.

WHY IT EXISTS. Before this module the vendor list was hand-maintained in FOUR places that drifted
independently — `capacity.PAID_AGENT_ORDER`, `dispatch._LANE_CASCADE`, `route._vendor_health`, and
`ianva/agents.py` — and a single vendor's facts (identity, auth, cap, window, meter, credential,
availability) were scattered across six modules with no shared record. That fragmentation is not
cosmetic: cap/window data duplicated between `logs/usage.json`, `logs/usage-limits.json`, and the
board's `portal.budget` is the exact DRIFT / SHARED-POOL pathology `scripts/verify-budget-gauge.py`
was built to *hunt*. One source of truth prevents the class of bug the audit tool exists to catch.

THE RULE. Every per-vendor fact is homed on exactly one :class:`Vendor` record here. The historical
lists become **derived views** (see the accessors below) — never re-typed by hand. Adding a vendor,
or recording that one went dark, is a one-record edit in this file, not an edit in six.

PURE STDLIB by design (like ``model_selection``) so scripts can load it by file path without pulling
in the package. ``model_selection`` remains the authority for the *Claude* tier ladder; census points
at it via ``Vendor.tiering`` rather than duplicating it.

CONVERGENCE ROADMAP (each remaining consumer records its own residual rewire, so nothing hangs in a
head or a chat):
  * DONE  — ``capacity.py`` derives PAID_AGENT_ORDER / AGENT_ALIASES / LOCAL_CHECKOUT_AGENTS /
            ISSUE_ASSIGNMENT_AGENTS / _DEFAULT_BINARIES / _KINDS from :data:`VENDORS`.
  * DONE  — ``dispatch._LANE_CASCADE`` now DERIVES from :func:`lane_cascade` (was drift-guarded);
            ``test_census`` still asserts the two are equal.
  * DONE  — ``scripts/usage-telemetry.py`` ``_DEFAULT_LIMITS`` metered rows derive from :func:`budgets`
            (filter: ``Budget.window != "none"``), with a drift-guarded fallback for launchd.
  * DONE  — ``scripts/route.py`` ``_vendor_health`` fallback derives its lane set + binaries from
            census (:func:`lane_cascade` + :func:`default_binaries`).
  * DONE  — ``ianva/src/ianva/agents.py`` keys reconcile against census names (``test_census`` guards
            that every dispatchable ianva target is a canonical vendor; ``cline`` is the one MCP-only
            target, documented).
  * DONE (Increment-1) — per-vendor model choice is homed on ``Vendor.tiering`` and projected by
            :func:`tiering`; ``test_census`` drift-guards it against a closed sentinel set. Remaining
            OpenCode consumes the provider-neutral live capability selector; Warp/Oz delegate the
            changing underlying catalog to provider Auto.  Model names remain runtime outputs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    """The 'means' half of the census: one vendor's spend window.

    Mirrors the row shape in ``usage-telemetry._DEFAULT_LIMITS`` so that table can eventually
    derive from here. ``trust`` is machine-readable so a controller reads an untrusted cap
    PESSIMISTICALLY (an estimate the size of 100M tokens otherwise looks like infinite headroom).
    """

    limit: int | None  # None = no modeled numeric cap (local floor, or not yet measured)
    unit: str  # "tokens" | "runs" | "app-runs"
    window: str  # "5h rolling" | "24h" | "today" | "none"
    source: str  # provenance of the number, human-readable
    trust: str  # "measured" | "estimate" | "calibrated" | "unmodeled"
    pool: str | None = None  # lanes sharing ONE subscription window (claude-plan / openai-plan)


@dataclass(frozen=True)
class Status:
    """The availability half of the census: is this lane usable, and if not, who owns the fix.

    ``deprecated_paths`` is the field this whole organ was worth building for — a machine-readable
    record that a *specific auth path* died upstream, so the fleet stops routing into a wall the
    code can't see. ``lever`` names the his-hand registry item that owns any irreducible human atom;
    the atom lives in ``his-hand-levers.json``, never recited in chat.
    """

    available: bool  # usable in principle right now (auth/quota/liveness permitting)
    state: str  # "live" | "live_if_model_pulled" | "suspended" | "needs_auth" | ...
    note: str
    lever: str | None = None  # his-hand-levers.json id owning any human atom
    deprecated_paths: tuple[str, ...] = ()  # auth/client paths that died upstream (do NOT route)


@dataclass(frozen=True)
class Vendor:
    """One provider of dispatchable work-capacity, with every scattered fact homed here."""

    name: str  # canonical lane name
    aliases: tuple[str, ...]  # alternate spellings that resolve to `name`
    binary: str  # default CLI binary (overridable via LIMEN_<VENDOR>_BIN)
    kind: str  # local-cli | cloud-cli | github-issue | paid-service | github-actions
    local_checkout: bool  # runs against a local worktree
    issue_assignment: bool  # dispatched by assigning a GitHub issue
    auth_mode: str  # how it authenticates (see notes on each record)
    cred_ref: str | None  # op:// source when creds-hydrate owns a key for it
    meter: str  # how usage is measured (see notes)
    tiering: str  # which model-selection layer owns its model choice
    budget: Budget
    status: Status
    doc: str = ""


# ── THE REGISTER ─────────────────────────────────────────────────────────────────────────────
# Canonical order == the historical `capacity.PAID_AGENT_ORDER`. Order is load-bearing (it is the
# preference order for lane selection), so it is asserted against the frozen literal in test_census.
VENDORS: tuple[Vendor, ...] = (
    Vendor(
        name="codex",
        aliases=(),
        binary="codex",
        kind="local-cli",
        local_checkout=True,
        issue_assignment=False,
        auth_mode="chatgpt_oauth",  # ~/.codex/auth.json — no API key held
        cred_ref=None,
        meter="vendor_ratelimit",  # real rate_limits in ~/.codex/sessions/*.jsonl (5h + weekly)
        tiering="provider_auto",  # explicit override only; no built-in model-name fallback
        budget=Budget(
            100_000_000, "tokens", "5h rolling", "ESTIMATE - tune to plan (/status)", "estimate", "openai-plan"
        ),
        status=Status(True, "live", "ChatGPT-plan OAuth lane"),
    ),
    Vendor(
        name="claude",
        aliases=(),
        binary="claude",
        kind="local-cli",
        local_checkout=True,
        issue_assignment=False,
        auth_mode="keychain_oauth",  # login-flap handler owns it; token deliberately not held
        cred_ref=None,
        meter="calibrated_ondisk",  # scripts/claude-usage.py calibrated 5h/7d gauge
        tiering="model_selection",  # THE tier authority — model_selection.py owns Claude's ladder
        budget=Budget(
            100_000_000, "tokens", "5h rolling", "ESTIMATE - tune to plan (/status)", "estimate", "claude-plan"
        ),
        status=Status(True, "live", "Claude-plan OAuth lane; shim pins the per-spawn floor tier"),
    ),
    Vendor(
        name="opencode",
        aliases=(),
        binary="opencode",
        kind="local-cli",
        local_checkout=True,
        issue_assignment=False,
        auth_mode="opencode_auth",  # own auth.json may expand the live reachable catalog
        cred_ref=None,
        meter="dispatch_count",
        tiering="provider_selection",  # provider_selection.py + live `opencode models --verbose`
        budget=Budget(100, "runs", "today", "operator board cap until live vendor meter", "calibrated"),
        status=Status(True, "live", "capabilities and pricing discovered from the live catalog"),
    ),
    Vendor(
        name="agy",
        aliases=("antigravity",),
        binary="agy",
        kind="local-cli",
        local_checkout=True,
        issue_assignment=False,
        auth_mode="google_oauth",  # ~/.gemini/antigravity-cli; agy IS Google's Antigravity client
        cred_ref=None,
        meter="dispatch_count",  # no readable vendor meter — agy persists NO local usage; /usage is live-fetched from Google OAuth only
        tiering="none",
        budget=Budget(100, "runs", "today", "operator board cap until live vendor meter", "calibrated"),
        # Antigravity is Google's DIRECTED migration target off the sunset Gemini Code-Assist OAuth
        # (see the gemini record). agy is healed, not archived: _bridge_agy_scratch carries its
        # scratch-dir work into the worktree; agy-noop-shim stops a mid-run browser sign-in.
        status=Status(True, "live", "Google Antigravity CLI; the migration target off Code-Assist OAuth"),
    ),
    Vendor(
        name="gemini",
        aliases=(),
        binary="gemini",
        kind="local-cli",
        local_checkout=True,
        issue_assignment=False,
        # Historically GEMINI_API_KEY *or* ~/.gemini/settings.json OAuth (Code Assist for
        # individuals). The OAuth/Code-Assist path is DEPRECATED (see status.deprecated_paths);
        # the live auth is the API key (or Vertex AI). dispatch.py:994's LIMEN_GEMINI_OAUTH=1
        # drops the key to use that now-dead client — do NOT set it until dispatch is rewired.
        auth_mode="api_key",  # was api_key_or_oauth; OAuth path sunset upstream
        cred_ref="op://Personal/Gemini API Key/credential",
        meter="dispatch_count",  # no readable vendor meter
        tiering="none",
        budget=Budget(10, "runs", "24h", "operator board cap until live vendor meter", "calibrated"),
        status=Status(
            available=False,
            state="suspended",
            # Two independent breakages, both homed here so the fleet stops guessing:
            #  1) API-key project: 403 CONSUMER_SUSPENDED (Google project suspended behind the
            #     card-0186 billing hold). Fix path is upstream billing, not a token re-mint.
            #  2) "Sign in with Google" / Code-Assist-for-individuals OAuth client: SUNSET
            #     2026-06-18 for all individuals -> migrate to Antigravity (agy), or use an API
            #     key from a NON-suspended project, or Vertex AI.
            note=(
                "API-key project suspended (403 CONSUMER_SUSPENDED, card-0186 hold); free "
                "Sign-in-with-Google Code-Assist OAuth sunset 2026-06-18 -> Antigravity/API-key/Vertex"
            ),
            lever="L-FLEET-CAPACITY",  # upstream root: L-CARD-FRAUD-HOLD
            deprecated_paths=("oauth_code_assist",),
        ),
    ),
    Vendor(
        name="ollama",
        aliases=(),
        binary="ollama",
        kind="local-cli",
        local_checkout=True,
        issue_assignment=False,
        auth_mode="local",  # unmetered local floor — no auth, no cap
        cred_ref=None,
        meter="unmetered",
        tiering="none",
        # The LOCAL, UNMETERED floor of the cascade — the pilot light. No token budget and no
        # rate-limit window, so when every metered/cloud vendor is spent the beat still has a lane
        # that can produce. Self-activating: reachable only once a model is pulled.
        budget=Budget(None, "runs", "none", "local unmetered floor (no cap)", "measured"),
        status=Status(True, "live_if_model_pulled", "one `ollama pull` from a live floor lane"),
    ),
    Vendor(
        name="jules",
        aliases=(),
        binary="jules",
        kind="cloud-cli",
        local_checkout=False,
        issue_assignment=False,
        auth_mode="keyring_gh",  # GH_TOKEN keyring-derived
        cred_ref=None,
        meter="run_count",
        tiering="none",
        budget=Budget(100, "runs", "24h", "known hard cap", "measured"),
        status=Status(True, "live", "async cloud lane; first pick for genuine big-task horizons"),
    ),
    Vendor(
        name="copilot",
        aliases=(),
        binary="gh",
        kind="github-issue",
        local_checkout=False,
        issue_assignment=True,
        auth_mode="keyring_gh",
        cred_ref=None,
        meter="none",  # dispatched by issue assignment, not run-metered locally
        tiering="none",
        budget=Budget(None, "runs", "none", "not modeled (issue-assignment lane)", "unmodeled"),
        status=Status(True, "live", "GitHub-issue assignment lane"),
    ),
    Vendor(
        name="warp",
        aliases=(),
        binary="warp",
        kind="paid-service",
        local_checkout=False,
        issue_assignment=False,
        auth_mode="warp_key",  # WARP_API_KEY
        cred_ref=None,
        meter="none",
        tiering="provider_auto",
        budget=Budget(None, "runs", "none", "not modeled (paid service)", "unmodeled"),
        status=Status(True, "live", "paid-service lane"),
    ),
    Vendor(
        name="oz",
        aliases=(),
        binary="oz",
        kind="paid-service",
        local_checkout=False,
        issue_assignment=False,
        auth_mode="warp_key",  # WARP_API_KEY family
        cred_ref=None,
        meter="none",
        tiering="provider_auto",
        budget=Budget(None, "runs", "none", "not modeled (paid service)", "unmodeled"),
        status=Status(True, "live", "paid-service lane"),
    ),
    Vendor(
        name="github_actions",
        aliases=("actions", "gha", "github-actions"),
        binary="gh",
        kind="github-actions",
        local_checkout=False,
        issue_assignment=False,
        auth_mode="keyring_gh",
        cred_ref=None,
        meter="none",
        tiering="none",
        budget=Budget(None, "runs", "none", "not modeled (CI lane)", "unmodeled"),
        status=Status(True, "live", "GitHub Actions lane"),
    ),
)

# The subset + order that `dispatch._LANE_CASCADE` walks (the earned local rotation). Homed here so
# the two can never silently diverge; test_census asserts equality against dispatch.
_LANE_CASCADE_ORDER: tuple[str, ...] = ("codex", "opencode", "agy", "claude", "gemini", "jules", "ollama")


# ── DERIVED VIEWS ────────────────────────────────────────────────────────────────────────────
# Everything below is a projection of VENDORS. Callers read these; they never re-type the facts.

_BY_NAME: dict[str, Vendor] = {v.name: v for v in VENDORS}


def by_name(name: str) -> Vendor | None:
    """The vendor record for a canonical name (or None)."""
    return _BY_NAME.get(name)


def canonical(name: str | None) -> str:
    """Resolve an alias (e.g. 'antigravity') to its canonical vendor name."""
    value = (name or "").strip()
    return agent_aliases().get(value, value)


def paid_agent_order() -> tuple[str, ...]:
    """The full preference-ordered vendor list (source of `capacity.PAID_AGENT_ORDER`)."""
    return tuple(v.name for v in VENDORS)


def agent_aliases() -> dict[str, str]:
    """alias -> canonical name (source of `capacity.AGENT_ALIASES`)."""
    return {alias: v.name for v in VENDORS for alias in v.aliases}


def local_checkout_agents() -> frozenset[str]:
    """Vendors that run against a local worktree (source of `capacity.LOCAL_CHECKOUT_AGENTS`)."""
    return frozenset(v.name for v in VENDORS if v.local_checkout)


def issue_assignment_agents() -> frozenset[str]:
    """Vendors dispatched by GitHub-issue assignment (source of `capacity.ISSUE_ASSIGNMENT_AGENTS`)."""
    return frozenset(v.name for v in VENDORS if v.issue_assignment)


def default_binaries() -> dict[str, str]:
    """name -> default CLI binary (source of `capacity._DEFAULT_BINARIES`)."""
    return {v.name: v.binary for v in VENDORS}


def kinds() -> dict[str, str]:
    """name -> lane kind (source of `capacity._KINDS`)."""
    return {v.name: v.kind for v in VENDORS}


def tiering() -> dict[str, str]:
    """name -> which model-selection layer owns its model choice (drift-guard for dispatch)."""
    return {v.name: v.tiering for v in VENDORS}


def lane_cascade() -> list[str]:
    """The earned local rotation order (should equal `dispatch._LANE_CASCADE`)."""
    return list(_LANE_CASCADE_ORDER)


def budgets() -> dict[str, Budget]:
    """name -> Budget (the eventual source of `usage-telemetry._DEFAULT_LIMITS` rows)."""
    return {v.name: v.budget for v in VENDORS}


def deprecated_paths() -> dict[str, tuple[str, ...]]:
    """name -> auth/client paths that died upstream and must not be routed into.

    The umbrella's headline query: 'which vendor paths are dead?'. Empty for a healthy fleet.
    """
    return {v.name: v.status.deprecated_paths for v in VENDORS if v.status.deprecated_paths}


def unavailable() -> dict[str, Status]:
    """name -> Status for every vendor not usable right now (its lever names who owns the fix)."""
    return {v.name: v.status for v in VENDORS if not v.status.available}
