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
  * DONE  — peer-conduct execution metadata is homed on ``Vendor.execution`` and projected by
            :func:`execution_profiles`; health, auth, concurrency, and meters stay live references,
            never cached model catalogs or numeric fallback tops.
  * DONE  — ``capacity.DEFAULT_FILL_AGENTS`` derives from execution-profile eligibility, while ianva
            transport drift tests reconcile every primary native adapter against the same profiles.
"""

from __future__ import annotations

from collections.abc import Mapping
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
class ExecutionProfile:
    """Provider-neutral execution and peer-conduct metadata for one native lane.

    The profile deliberately records *references* for health, auth, concurrency, and metering.
    Those values are live runtime state and must not become fixed catalog snapshots or numeric
    fallback tops in this register.  The fields shared with ``ConductorSessionV1`` can be copied
    directly when a healthy native session registers with the conduct broker.
    """

    capabilities: frozenset[str]
    transport: str
    native_fanout: bool
    harvest_method: str
    concurrency_ref: str
    meter_ref: str
    health_ref: str
    auth_ref: str
    daily_fill: bool = False
    # Stable workstream invocation protocol. Provider IDs are registry data and may be renamed;
    # launch behavior must therefore dispatch on this protocol rather than on ``Vendor.name``.
    workstream_adapter: str = "positional"
    workstream_model_flag: bool = False


@dataclass(frozen=True)
class OpeningFloor:
    """Where one lane's INTERACTIVE opening model/effort is pinned, and how to read it.

    The cadence question generalized past Claude (F6 of the 2026-08-07 cadence-guard arc). The
    operator's own framing was "all providers, not just Claude": every vendor with an interactive
    surface has some opening default, each in its own file, and nothing in the estate could say
    what any of them were. Measured that day: ``~/.codex/config.toml`` carried ``gpt-5.6-sol`` at
    ``ultra`` effort, and ``~/.gemini/settings.json`` carried no ``model`` key at all — neither
    fact was reachable by any predicate.

    ``kind`` is the reason a lane has (or lacks) a readable floor, so no row is ever a bare N/A:

      config-file      a readable config file declares it — probe ``config_path`` at ``pointer``
      hook-armed       the pin lives in a harness-internal store no predicate can read; the only
                       observable is whether the DECLARED pin is armed, so the row delegates to
                       ``arming_valve`` in spec/armed-valves.json (design decision D8: exactly one
                       reader of settings.json arming state, and this is not a second one)
      unresolved       the lane has an interactive surface but its config was NOT LOCATED — the
                       honest starting state, which clears when someone finds the file
      not-interactive  no interactive session surface exists (issue-dispatch / CI lanes), so there
                       is no opening default to pin. A reason, not a vacuum.
      not-metered      interactive but no per-token spend (local weights), so cadence does not apply

    ``ladder_ref`` follows the same convention as ExecutionProfile's ``*_ref`` fields: a REFERENCE
    to live code rather than a copied snapshot, so the Claude ladder is never re-typed here and
    cannot drift from the one in model_selection.
    """

    kind: str
    config_path: str = ""
    # The agent_config_paths vendor key whose ACTIVE config this row lives in. When set, the reader
    # resolves the real file through that module instead of expanding ``config_path`` — because
    # CLAUDE_CONFIG_DIR / GEMINI_CLI_HOME / CODEX_HOME relocate these roots, and the abandoned copy
    # keeps parsing. Measured 2026-08-12: this row's ``~/.codex/config.toml`` said effort ``ultra``
    # (reported as an above-ceiling breach) while the file codex actually reads said ``max``.
    # ``config_path`` stays as the human-readable label and the fallback for unmapped lanes.
    config_vendor: str = ""
    pointer: str = ""
    ladder: tuple[str, ...] = ()
    ladder_ref: str = ""
    ceiling: str = ""
    arming_valve: str = ""
    note: str = ""


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
    execution: ExecutionProfile
    doc: str = ""


def _execution(
    name: str,
    *,
    capabilities: tuple[str, ...],
    transport: str,
    native_fanout: bool,
    harvest_method: str,
    concurrency_scope: str,
    daily_fill: bool = False,
    workstream_adapter: str = "positional",
    workstream_model_flag: bool = False,
) -> ExecutionProfile:
    """Build one profile while deriving every per-lane live-state reference from its name."""

    return ExecutionProfile(
        capabilities=frozenset(capabilities),
        transport=transport,
        native_fanout=native_fanout,
        harvest_method=harvest_method,
        concurrency_ref=f"capacity:{concurrency_scope}/{name}",
        meter_ref=f"logs/usage.json#/vendors/{name}",
        health_ref=f"limen.capacity:agent_status/{name}",
        auth_ref=f"limen.census:vendors/{name}/auth_mode",
        daily_fill=daily_fill,
        workstream_adapter=workstream_adapter,
        workstream_model_flag=workstream_model_flag,
    )


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
        execution=_execution(
            "codex",
            capabilities=("conduct", "execute", "code", "review", "inspect", "local-worktree"),
            transport="ianva-http",
            native_fanout=True,
            harvest_method="conduct-report",
            concurrency_scope="local-host-admission",
            daily_fill=True,
            workstream_adapter="codex",
        ),
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
        execution=_execution(
            "claude",
            capabilities=("conduct", "execute", "code", "review", "inspect", "local-worktree"),
            transport="ianva-http",
            native_fanout=True,
            harvest_method="conduct-report",
            concurrency_scope="local-host-admission",
            daily_fill=True,
            workstream_model_flag=True,
        ),
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
        execution=_execution(
            "opencode",
            capabilities=("conduct", "execute", "code", "review", "inspect", "local-worktree"),
            transport="ianva-http",
            native_fanout=True,
            harvest_method="conduct-report",
            concurrency_scope="local-host-admission",
            daily_fill=True,
            workstream_adapter="prompt-flag",
            workstream_model_flag=True,
        ),
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
        execution=_execution(
            "agy",
            capabilities=(
                "conduct",
                "execute",
                "code",
                "review",
                "inspect",
                "local-worktree",
                "scratch-bridge",
            ),
            transport="ianva-stdio",
            native_fanout=False,
            harvest_method="conduct-report",
            concurrency_scope="local-host-admission",
            daily_fill=True,
            workstream_adapter="prompt-interactive",
            workstream_model_flag=True,
        ),
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
            state="needs_auth",
            # Two observed breakages, kept distinct so the fleet stops inventing a shared cause:
            #  1) The registered API key returned 400 API_KEY_INVALID on 2026-08-07. The current
            #     evidenced action is a replacement credential, not a billing attribution.
            #  2) "Sign in with Google" / Code-Assist-for-individuals OAuth client: SUNSET
            #     2026-06-18 for all individuals -> migrate to Antigravity (agy), or use an API
            #     key, or Vertex AI.
            note=(
                "registered key rejected with 400 API_KEY_INVALID on 2026-08-07; no current billing "
                "cause established; Sign-in-with-Google Code-Assist OAuth sunset 2026-06-18"
            ),
            lever="L-FLEET-CAPACITY",
            deprecated_paths=("oauth_code_assist",),
        ),
        execution=_execution(
            "gemini",
            capabilities=("conduct", "execute", "code", "review", "inspect", "local-worktree"),
            transport="ianva-http",
            native_fanout=False,
            harvest_method="conduct-report",
            concurrency_scope="local-host-admission",
            daily_fill=True,
            workstream_adapter="prompt-interactive",
            workstream_model_flag=True,
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
        execution=_execution(
            "ollama",
            capabilities=("conduct", "execute", "review", "inspect", "local-worktree"),
            transport="native-cli",
            native_fanout=False,
            harvest_method="conduct-report",
            concurrency_scope="local-host-admission",
        ),
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
        execution=_execution(
            "jules",
            capabilities=("conduct", "execute", "code", "review", "inspect", "github-remote"),
            transport="provider-receipt-relay",
            native_fanout=False,
            harvest_method="jules-remote",
            concurrency_scope="provider-headroom",
            daily_fill=True,
            workstream_adapter="jules",
        ),
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
        execution=_execution(
            "copilot",
            capabilities=("conduct", "execute", "code", "review", "inspect", "github-remote"),
            transport="ianva-http",
            native_fanout=True,
            harvest_method="github-receipt",
            concurrency_scope="provider-headroom",
            daily_fill=True,
        ),
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
        execution=_execution(
            "warp",
            capabilities=("conduct", "execute", "code", "review", "inspect", "remote"),
            transport="provider-receipt-relay",
            native_fanout=False,
            harvest_method="provider-receipt",
            concurrency_scope="provider-headroom",
        ),
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
        execution=_execution(
            "oz",
            capabilities=("conduct", "execute", "code", "review", "inspect", "remote"),
            transport="provider-receipt-relay",
            native_fanout=False,
            harvest_method="provider-receipt",
            concurrency_scope="provider-headroom",
        ),
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
        execution=_execution(
            "github_actions",
            capabilities=("conduct", "execute", "review", "inspect", "verify", "github-remote"),
            transport="provider-receipt-relay",
            native_fanout=False,
            harvest_method="provider-receipt",
            concurrency_scope="provider-headroom",
        ),
    ),
)

# The subset + order that `dispatch._LANE_CASCADE` walks (the earned local rotation). Homed here so
# the two can never silently diverge; test_census asserts equality against dispatch.
_LANE_CASCADE_ORDER: tuple[str, ...] = ("codex", "opencode", "agy", "claude", "gemini", "jules", "ollama")


# ── SESSION-OPENING FLOORS ───────────────────────────────────────────────────────────────────
# One row per lane, keyed by canonical vendor name. Declared as a block beside VENDORS rather than
# as a field inside each record because it is a HOST-configuration fact about the interactive
# surface, not a dispatch fact — but it is completeness-checked against VENDORS below, so a new
# vendor cannot land without one and the registry can never silently lag the register.
#
# Every row carries a REASON (see OpeningFloor.kind). Rule #1: an N/A is a vacuum, never a resting
# state — "not-interactive" and "unresolved" are different findings and are recorded as such.
OPENING_FLOORS: dict[str, OpeningFloor] = {
    "claude": OpeningFloor(
        kind="hook-armed",
        config_path="~/.claude/settings.json",
        config_vendor="claude-settings",
        pointer="model",
        ladder_ref="limen.model_selection:_CLAUDE_TIER_ORDER",
        ceiling="sonnet",
        arming_valve="SESSION_MODEL_OPENING_PIN",
        note=(
            "`/model` persists its choice to a harness-internal store that is absent from "
            "settings.json, settings.local.json and every plain key of ~/.claude.json — searched "
            "2026-08-07, only per-project lastModelUsage exists. So the LIVE opening tier is "
            "unreadable by construction and only the DECLARED pin can be probed. This row is "
            "therefore about arming, and delegates; the live tier is caught at SessionStart by "
            "fable-session-guard.py's ceiling arm instead."
        ),
    ),
    "codex": OpeningFloor(
        kind="config-file",
        config_path="~/.codex/config.toml",
        config_vendor="codex",
        pointer="model_reasoning_effort",
        # ``max`` was observed in the live config on 2026-08-12 and matched no rung, which would
        # have downgraded a real breach to an `unresolved` shrug the moment path resolution was
        # fixed. Its exact rank against ``ultra`` is not established here — both sit above the
        # ``high`` ceiling, so the above-ceiling verdict holds either way.
        ladder=("minimal", "low", "medium", "high", "ultra", "max"),
        ceiling="high",
        note=(
            "Measured 2026-08-07: model gpt-5.6-sol at `ultra` effort — one rung above the "
            "declared ceiling. Codex's cost axis is reasoning EFFORT rather than a model tier, "
            "which is why this row points at model_reasoning_effort and not at `model`; the "
            "cadence question ('does this lane open dearer than it needs to?') is the same one."
        ),
    ),
    "gemini": OpeningFloor(
        kind="config-file",
        config_path="~/.gemini/settings.json",
        config_vendor="gemini",
        pointer="model",
        ladder=("flash", "pro"),
        ceiling="flash",
        note=(
            "Measured 2026-08-07: no `model` key at all, so the lane opens on whatever the CLI's "
            "own default is — unreadable from here and therefore UNSET rather than known-cheap. "
            "An absent pin is reported as unset, never assumed to be the cheap rung."
        ),
    ),
    "agy": OpeningFloor(kind="unresolved", note="interactive surface; opening-pin config not located"),
    "copilot": OpeningFloor(kind="unresolved", note="interactive surface; opening-pin config not located"),
    "warp": OpeningFloor(kind="unresolved", note="interactive surface; opening-pin config not located"),
    "oz": OpeningFloor(kind="unresolved", note="interactive surface; opening-pin config not located"),
    "opencode": OpeningFloor(kind="unresolved", note="interactive surface; opening-pin config not located"),
    "ollama": OpeningFloor(
        kind="not-metered",
        note="local weights, no per-token spend — a cadence ceiling has nothing to protect here",
    ),
    "jules": OpeningFloor(
        kind="not-interactive",
        note="dispatched by assigning a GitHub issue; there is no interactive session to open",
    ),
    "github_actions": OpeningFloor(
        kind="not-interactive",
        note="CI runner lane; no interactive session surface exists",
    ),
}


def opening_floor(name: str) -> OpeningFloor | None:
    """The declared session-opening floor for a canonical vendor name (or None)."""
    return OPENING_FLOORS.get(canonical(name))


def undeclared_opening_floors() -> tuple[str, ...]:
    """Vendors in VENDORS with no OPENING_FLOORS row — a self-surfacing vacuum, the same shape
    armed-valve-audit's UNCLASSIFIED uses. A new vendor lands red here rather than silently
    inheriting "no cadence applies"."""
    return tuple(v.name for v in VENDORS if v.name not in OPENING_FLOORS)


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


def execution_profiles() -> dict[str, ExecutionProfile]:
    """Return every canonical lane's model-neutral execution/conduct profile.

    This is an inventory, not a preference list.  Callers combine it with live health, auth,
    provider headroom, ownership, and packet requirements before selecting an executor.
    """

    return {v.name: v.execution for v in VENDORS}


def conduct_capabilities(
    health: Mapping[str, bool] | None = None,
) -> dict[str, ExecutionProfile]:
    """Return the currently eligible peer-conduct profiles.

    ``health`` is the live capacity/broker observation when a caller has one.  Without it the
    register's fail-closed availability state is used; this never probes binaries or provider
    catalogs at import time.  Capability matching and ranking remain runtime operations.
    """

    live = health or {}
    return {
        vendor.name: vendor.execution
        for vendor in VENDORS
        if "conduct" in vendor.execution.capabilities and bool(live.get(vendor.name, vendor.status.available))
    }


def default_fill_agents() -> tuple[str, ...]:
    """Lanes included in daily capacity-fill reporting, derived from their profiles."""

    return tuple(v.name for v in VENDORS if v.execution.daily_fill)


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
