"""Single source of truth for the Claude-lane model vocabulary + the non-bypassable shim's
per-spawn floor sort.

Two callers share this ONE module so the model decision never drifts across copies:

  * ``dispatch.py``'s per-TASK earned-tier ladder (``_claude_tier_for`` / ``_bump_tier`` /
    ``_claude_model``) imports the shared primitives below — it owns the rich sort, keyed on a
    task's classes/labels, and passes ``--model`` explicitly.
  * ``scripts/shims/claude`` — the non-bypassable chokepoint prepended onto the FLEET PATH —
    calls :func:`model_for_argv` to decide what ``--model`` to inject when a fleet spawn carries
    NONE. It owns the per-SPAWN floor: nothing escapes the sort to the account default (Opus 4.8 +
    auto-1M context, which drove the 2026-06-25 usage bleed) WITHOUT a declaration.

Design note — this module is PURE stdlib (only ``os``) and imports nothing from the ``limen``
package, so the shim can ``importlib``-load it by file path without triggering ``limen``'s package
``__init__`` or depending on ``PYTHONPATH``. ([[fleet-model-floor-bleed]] [[derive-never-pin-hardcodes]])
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Iterable, Mapping

# The ladder rungs, cheapest-first. Shared with dispatch's earned-tier ladder. Fable is a
# reserved top tier above Opus, not a new default escalation target.
_CLAUDE_TIER_ORDER = ("haiku", "sonnet", "opus", "fable")

# Reserved-Opus classes: the doctrine's small principled set whose failure is BOTH undetectable
# AND high-stakes (final/canon synthesis, irreversible go-live reasoning, kernel abstraction). A
# stated principle, env-overridable (comma-separated LIMEN_CLAUDE_OPUS_CLASSES) — not inherited config.
_CLAUDE_OPUS_CLASSES_DEFAULT = ("canon", "synthesis", "kernel", "go-live", "irreversible")

# Fable classes are narrower than reserved-Opus classes and still require an explicit acceptance
# receipt before model selection is allowed to return the Fable rung.
_CLAUDE_FABLE_CLASSES_DEFAULT = (
    "fable",
    "long-horizon",
    "huge-context",
    "ambiguous-root-cause",
    "final-canonical-decision",
)

# Phase (mode:*) labels — planning is the Opus-reserved phase; building is capped cheap
# (docs/fable-allotment.md: "Fable plans, cheaper tiers build"). plan_handoff.py imports these
# two so the label vocabulary has ONE home; this module is pure-stdlib and imports nothing,
# so the dependency direction is legal. Deliberately NOT members of _CLAUDE_OPUS_CLASSES_DEFAULT:
# that set is work-DOMAIN vocabulary (check-session-streams gate G validates job_class against
# it), and an LIMEN_CLAUDE_OPUS_CLASSES override must not be able to drop the phase guarantee.
_PLAN_ONLY_CLASS = "mode:plan-only"
_BUILD_FROM_PLAN_CLASS = "mode:build-from-plan"


def _build_max_tier() -> str:
    """The CEILING for mode:build-from-plan work. Env-tunable (LIMEN_CLAUDE_BUILD_MAX_TIER,
    default sonnet) but hard-capped at opus: building on Fable is prohibited by doctrine —
    no env value can grant it."""
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_BUILD_MAX_TIER", "sonnet"), "opus")


def _claude_opus_classes() -> set[str]:
    """The reserved-Opus class set — env override (LIMEN_CLAUDE_OPUS_CLASSES, comma-separated)
    wins, else the stated default. Shared by dispatch's per-task ladder."""
    raw = os.environ.get("LIMEN_CLAUDE_OPUS_CLASSES")
    if raw is not None:
        return {c.strip() for c in raw.split(",") if c.strip()}
    return set(_CLAUDE_OPUS_CLASSES_DEFAULT)


def _claude_fable_classes() -> set[str]:
    """The reserved-Fable class set — env override (LIMEN_CLAUDE_FABLE_CLASSES,
    comma-separated) wins, else the stated default. A class match alone is not enough;
    :func:`_claude_fable_acceptance_present` must also pass."""
    raw = os.environ.get("LIMEN_CLAUDE_FABLE_CLASSES")
    if raw is not None:
        return {c.strip() for c in raw.split(",") if c.strip()}
    return set(_CLAUDE_FABLE_CLASSES_DEFAULT)


def _claude_fable_acceptance_present() -> bool:
    """True only when the operator has provided a written Fable acceptance artifact.

    The expected value is a path to a receipt produced by ``scripts/fable-allotment.py accept``.
    Test processes may set ``1``; real runs must point at a current-week receipt so an old shell
    export or arbitrary existing path cannot become a standing Fable grant.
    """
    raw = os.environ.get("LIMEN_FABLE_ACCEPTANCE", "").strip()
    if not raw:
        return False
    if raw == "1":
        return "PYTEST_CURRENT_TEST" in os.environ
    try:
        path = os.path.expanduser(raw)
        with open(path) as fh:
            receipt = json.load(fh)
        now = dt.datetime.now(dt.timezone.utc)
        monday = (now - dt.timedelta(days=now.weekday())).date().isoformat()
        return receipt.get("schema") == "limen.fable_acceptance.v1" and receipt.get("week") == monday
    except Exception:
        return False


# ── The weekly Fable meter: ONE reader, returning a VERDICT ─────────────────────────────────
#
# Until 2026-08-07 THREE copies of this read existed — model_selection._fable_balance,
# fable-session-guard._load_balance, vendor-cancel-advisor._fable_over_cap — each typed
# ``dict | None``, and each caller read None as permissive. That type WAS the bug: it had no room
# for "unknown", so unknown collapsed into fine. `parameters.yaml` had named all three as a
# declared fork since before the incident; the fork was declared and never closed.
#
# The replacement returns a VERDICT with an explicit state, so "I could not establish this" and
# "this is fine" can never again be the same value (design decisions D2/D3).

_FABLE_BALANCE_MAX_AGE_S_DEFAULT = 21600.0  # 6h — several beats' slack, still catches a dead writer


def _fable_balance_path() -> tuple[str, bool]:
    """(path, is_beat_written). ``LIMEN_FABLE_BALANCE_PATH`` names a caller-supplied file — a test
    fixture or a deliberate pin — which is NOT the beat's artifact, so the deployment-provenance
    dimension below does not apply to it."""
    raw = os.environ.get("LIMEN_FABLE_BALANCE_PATH")
    if raw:
        return raw, False
    root = os.environ.get("LIMEN_ROOT")
    base = root if root else os.path.join(os.path.expanduser("~"), "Workspace", "limen")
    return os.path.join(base, "logs", "fable-allotment.json"), True


def _fable_balance_max_age_s() -> float:
    """Freshness budget for the meter file, in seconds. THE DECLARED HATCH (D4): a value <= 0
    disables both the freshness and the provenance dimensions, restoring the pre-2026-08-07
    fail-open behaviour for a host that genuinely runs no beat."""
    try:
        return float(os.environ.get("LIMEN_FABLE_BALANCE_MAX_AGE_S", _FABLE_BALANCE_MAX_AGE_S_DEFAULT))
    except (TypeError, ValueError):
        return _FABLE_BALANCE_MAX_AGE_S_DEFAULT


def deployment_currency() -> tuple[str, str]:
    """(state, detail) for the tree the beat executes — read from the OFFLINE receipt written by
    ``scripts/check-live-checkout.py`` (no network, no git). States: ``coherent`` / ``drift`` /
    ``unverifiable-here`` / ``absent`` / ``unreadable``.

    This is the provenance dimension the 2026-08-07 incident demanded (D0). The meter file there
    was FRESH and WRONG: rewritten every beat by a copy of fable-allotment.py that predated the
    heal giving it sight, so it reported 0.0% while the true figure was 75.47%. No age bound
    catches that, because the stale party was the writer's code, not the artifact.
    """
    raw = os.environ.get("LIMEN_LIVE_CHECKOUT_RECEIPT")
    if raw:
        path = os.path.expanduser(raw)
    else:
        root = os.environ.get("LIMEN_ROOT")
        base = root if root else os.path.join(os.path.expanduser("~"), "Workspace", "limen")
        path = os.path.join(base, "logs", "live-checkout-currency.json")
    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return "absent", "no live-checkout receipt — deployment currency unestablished"
    except Exception as exc:  # noqa: BLE001 — an unreadable receipt is itself the finding
        return "unreadable", f"live-checkout receipt unreadable ({type(exc).__name__})"
    if not isinstance(data, dict):
        return "unreadable", "live-checkout receipt is not an object"
    state = str(data.get("state") or "unreadable")
    if state == "drift":
        return state, (
            f"the tree the beat executes is {data.get('behind', '?')} commit(s) behind origin/main "
            "— every artifact it wrote is suspect regardless of how recently it was written"
        )
    return state, str(data.get("detail") or "")


def balance_verdict() -> dict:
    """THE reader of the weekly Fable meter. Never returns None; always returns a verdict:

        {state, trusted, balance, age_s, provenance, detail}

    ``state``       ok | absent | unreadable | malformed | stale-week | stale-file | undeployed
    ``trusted``     False for every state except ``ok`` — the caller must degrade, not proceed
    ``balance``     the parsed dict when readable, else None (never the trust signal)
    ``provenance``  deployment_currency() state, always reported even when it costs nothing

    Freshness is measured from the file's MTIME, not a body field (D1): ``compute_balance()``
    declares that timestamps derive from data and never from wall-clock, and
    ``verify-fable-gate.sh`` block 5 asserts two consecutive runs are byte-identical — adding a
    ``generated_at`` would redden a green predicate and restamp fixtures across four test files.
    ``logs/`` is gitignored runtime state with exactly one writer, so the file's mtime IS the
    writer's heartbeat.

    PROVENANCE COSTS TRUST ONLY ON ``drift``. An ``absent`` receipt means deployment currency is
    unestablished, which is REPORTED in ``detail`` and carried in ``provenance`` for callers that
    should speak about it — but it does not by itself withhold a tier, because a receipt that has
    simply never been written yet (a fresh host, a CI runner) is not evidence of a stale tree. The
    distinction the defect class forbids collapsing is preserved: every state is named and
    reachable by the caller. What varies is only which of them costs a TIER.
    """
    path, beat_written = _fable_balance_path()
    max_age = _fable_balance_max_age_s()
    checks_disabled = max_age <= 0
    prov_state, prov_detail = ("skipped", "") if checks_disabled else deployment_currency()

    def verdict(state, trusted, balance=None, age_s=None, detail=""):
        return {
            "state": state,
            "trusted": trusted,
            "balance": balance,
            "age_s": age_s,
            "provenance": prov_state,
            # ``enforced`` is POLICY, kept separate from the verdict's truth: with the declared
            # hatch armed the state is still reported honestly (``absent`` stays ``absent``), and
            # only the consumer's decision to withhold a tier is switched off. A hatch must never
            # be implemented by making the reader lie about what it saw.
            "enforced": not checks_disabled,
            "detail": detail or prov_detail,
        }

    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return verdict("absent", False, detail=f"no weekly Fable meter at {path}")
    except Exception as exc:  # noqa: BLE001 — an unreadable meter is the finding
        return verdict("unreadable", False, detail=f"meter unreadable ({type(exc).__name__})")
    if not isinstance(data, dict):
        return verdict("malformed", False, detail="meter is not an object")

    now = dt.datetime.now(dt.timezone.utc)
    monday = (now - dt.timedelta(days=now.weekday())).date().isoformat()
    if str(data.get("week")) != monday:
        return verdict(
            "stale-week", False, balance=data, detail=f"meter is for week {data.get('week')!r}, not {monday}"
        )

    age_s = None
    if not checks_disabled:
        try:
            age_s = max(0.0, dt.datetime.now().timestamp() - os.stat(path).st_mtime)
        except OSError:
            age_s = None
        if age_s is not None and age_s > max_age:
            return verdict(
                "stale-file",
                False,
                balance=data,
                age_s=age_s,
                detail=f"meter last written {age_s / 3600:.1f}h ago (budget {max_age / 3600:.1f}h) — the writer stopped",
            )
        if beat_written and prov_state == "drift":
            return verdict("undeployed", False, balance=data, age_s=age_s, detail=prov_detail)

    return verdict("ok", True, balance=data, age_s=age_s)


def _balance_over_cap(balance: dict) -> bool:
    """Derive over-cap from the numbers, never from the stored boolean alone. One home for the
    ``bool(x.get("over_cap"))`` read that was forked across three files — a False/absent flag on a
    body whose spent_pct already exceeds hard_cap must not read as under cap."""
    if not isinstance(balance, dict):
        return False
    try:
        spent = float(balance.get("spent_pct"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bool(balance.get("over_cap"))
    hard_cap = float(balance.get("hard_cap", 50) or 50)
    return bool(balance.get("over_cap")) or spent >= hard_cap


def _fable_capped_tier(reserve_ok: bool) -> str | None:
    """The live-cap decision for a would-be Fable selection whose acceptance receipt already
    passed. Returns None when Fable is still allowed, else the fallback tier to use instead:

      * spent_pct < deliberate_cap (40)         → None (Fable allowed).
      * deliberate_cap ≤ spent_pct < hard_cap   → only a current-week ``reserve`` receipt passes;
                                                   every other Fable route → Opus.
      * spent_pct ≥ hard_cap (50)               → hard downgrade to Opus, NO exception.

    ``reserve_ok`` marks that the caller's authorization is a fresh ``reserve``-category receipt.
    HARD_CAP is a hard cap. The cap downgrade lands on Opus (an over-cap Fable job was legitimately
    high-value; Opus is the nearest tier down), distinct from the acceptance-ABSENT fallback which
    stays at ``_fable_fallback_tier``.

    BEHAVIOUR REVERSAL, 2026-08-07 (design decision D4). This used to FAIL OPEN: an absent,
    unreadable, or stale meter returned None, so the acceptance receipt alone decided and Fable was
    granted. That is exactly how the incident ran — a meter reporting 0.0% because the deployed
    writer was blind released both brakes, and ~50% of the weekly allotment burned in two days with
    no downgrade and no warning. An unresolvable meter now costs a TIER: the selection lands on
    Opus. It never costs the WORK — no job is blocked, only the reserved tier withheld — and the
    declared hatch (``LIMEN_FABLE_BALANCE_MAX_AGE_S <= 0``) restores the old behaviour for a host
    that genuinely runs no beat.
    """
    verdict = balance_verdict()
    if not verdict["trusted"]:
        if not verdict["enforced"]:
            return None  # declared hatch armed — the operator has switched this dimension off
        return _fable_cap_downgrade_tier()
    bal = verdict["balance"]
    try:
        spent = float(bal.get("spent_pct"))
    except (TypeError, ValueError):
        return _fable_cap_downgrade_tier()
    deliberate_cap = float(bal.get("deliberate_cap", 40) or 40)
    hard_cap = float(bal.get("hard_cap", 50) or 50)
    if spent >= hard_cap:
        return _fable_cap_downgrade_tier()
    if spent >= deliberate_cap:
        return None if reserve_ok else _fable_cap_downgrade_tier()
    return None


def _fable_cap_downgrade_tier() -> str:
    """Where an OVER-CAP (but acceptance-valid) Fable selection lands: Opus by default, capped to
    the ladder, env-overridable via ``LIMEN_CLAUDE_FABLE_CAP_TIER``."""
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_FABLE_CAP_TIER", "opus"), "opus")


def _fable_reserve_receipt_present() -> bool:
    """True only when the current acceptance receipt is a fresh (current-ISO-week) ``reserve``
    category receipt — the single exception that passes the 40–50% band. Reuses the same receipt
    file the acceptance gate reads; a test ``LIMEN_FABLE_ACCEPTANCE=1`` is NOT a reserve receipt."""
    raw = os.environ.get("LIMEN_FABLE_ACCEPTANCE", "").strip()
    if not raw or raw == "1":
        return False
    try:
        with open(os.path.expanduser(raw)) as fh:
            receipt = json.load(fh)
        now = dt.datetime.now(dt.timezone.utc)
        monday = (now - dt.timedelta(days=now.weekday())).date().isoformat()
        return (
            receipt.get("schema") == "limen.fable_acceptance.v1"
            and receipt.get("week") == monday
            and receipt.get("category") == "reserve"
        )
    except Exception:
        return False


def _fable_or_downgrade(fable_tier: str = "fable") -> str:
    """Resolve a Fable-authorized selection against the LIVE weekly cap. Precondition: the caller
    has already confirmed a valid acceptance receipt is present. Returns ``fable_tier`` when the
    cap still allows Fable, else the fallback tier (Opus). This is the runtime backstop layered on
    top of the accept-time receipt gate."""
    downgrade = _fable_capped_tier(_fable_reserve_receipt_present())
    return downgrade if downgrade is not None else fable_tier


def tier_for_classes(
    classes: Iterable[str],
    *,
    waste_classes: Iterable[str] = (),
    overrides: Mapping[str, Iterable[str]] | None = None,
) -> str:
    """THE class -> tier sort, cheapest-first. Default = haiku (verifiable, so the existing cascade
    escalates); a higher rung is pre-assigned ONLY where failure is undetectable.

    Extracted from ``dispatch._claude_tier_for`` so a THIRD consumer — the STREAMS registry's
    ``job_class`` -> ``--model`` derivation — can reach the ladder without importing ``dispatch``
    (which drags in the whole ``limen`` package and would break this module's pure-stdlib contract,
    see the module docstring). Callers supply the two lane-local inputs rather than this module
    reaching for them: ``waste_classes`` (ledger-DISCOVERED) and ``overrides``
    (``logs/model-tiers.json``). ``dispatch`` keeps its per-task pin and its ``Task`` plumbing and
    calls this for the sort, so there is exactly one ladder, not a second copy.

    Phase rules (docs/fable-allotment.md — "Fable plans, cheaper tiers build"):
    ``mode:plan-only`` floors the sort at opus (Fable still needs its acceptance receipt; an
    un-accepted fable class on PLANNING lands on opus, the plan rung, not the cheap fallback).
    ``mode:build-from-plan`` caps the result at :func:`_build_max_tier` (default sonnet, hard
    cap opus) — cap-wins unconditionally, even over plan-only residue or an ACCEPTED fable
    class, because build authorization means execution and building above the ceiling is the
    doctrine violation this sort exists to prevent.
    """
    wanted = set(classes)
    override = dict(overrides or {})
    plan_only = _PLAN_ONLY_CLASS in wanted
    if wanted & (_claude_fable_classes() | set(override.get("fable") or [])):
        if _claude_fable_acceptance_present():
            tier = _fable_or_downgrade()
        else:
            # Un-accepted fable-class PLANNING still belongs on the plan-phase rung; the cheap
            # fallback is for build-ish work that overstated its class.
            tier = "opus" if plan_only else _fable_fallback_tier()
    elif plan_only or wanted & (_claude_opus_classes() | set(override.get("opus") or [])):
        tier = "opus"
    elif wanted & (set(waste_classes) | set(override.get("sonnet") or [])):
        tier = "sonnet"
    else:
        tier = "haiku"
    if _BUILD_FROM_PLAN_CLASS in wanted:
        tier = _cap_tier(tier, _build_max_tier())  # cap-wins, unconditionally
    return tier


def _claude_model_is_fable(model: str | None) -> bool:
    return bool(model and "fable" in str(model).lower())


def _claude_model_is_opus(model: str | None) -> bool:
    return bool(model and "opus" in str(model).lower())


def _claude_model_uses_large_context(model: str | None) -> bool:
    text = str(model or "").lower()
    return bool("1m" in text or "1000000" in text or "1,000,000" in text)


def _ladder_index(rung: str, ladder: tuple[str, ...]) -> int:
    """Ordinal position of ``rung`` in a cheapest-first ladder; 0 (the cheapest) when unknown.

    THE one ordinal primitive (design decision D5). It is generic over the ladder so a per-vendor
    census can reuse it without a second copy of "which of these is dearer" — the shape that had
    already forked three times for the weekly meter.
    """
    try:
        return ladder.index(rung)
    except ValueError:
        return 0


def _tier_index(tier: str) -> int:
    """The Claude binding of :func:`_ladder_index`. Kept as a name so no caller moves."""
    return _ladder_index(tier, _CLAUDE_TIER_ORDER)


def _rung_of(pin: str, ladder: tuple[str, ...] = _CLAUDE_TIER_ORDER) -> str:
    """Classify a model PIN (``claude-opus-5``, ``sonnet``, ``gpt-5.6-sol``) to its ladder rung.

    DEAREST-FIRST, deliberately: if a pin somehow names two rungs, the expensive reading wins, so
    an ambiguous string fails toward caution rather than toward silence. Returns ``""`` when the
    pin matches no rung — an explicit "unclassifiable", never the cheapest rung, because that
    substitution is precisely the defect this arc exists to close.
    """
    text = str(pin or "").lower()
    for rung in reversed(ladder):
        if rung in text:
            return rung
    return ""


def _norm_rung(value: str, ladder: tuple[str, ...] = _CLAUDE_TIER_ORDER) -> str:
    """Normalize a DECLARED rung name (a ceiling, a floor, a cap) to its ladder member, or ``""``.

    EXACT membership after case/whitespace normalization — deliberately NOT :func:`_rung_of`'s
    substring scan, which classifies model PINS. A declaration names a rung outright, so ``"opus"``
    must match and ``"claude-opus-5"`` must not: a ceiling is not a model.

    Returns ``""`` rather than a rung when the value names none, so a caller WITH a verdict channel
    can say "this could not be resolved" instead of substituting a value nobody declared (D3). The
    string-returning accessors keep their own fallbacks — this primitive only stops the two ways a
    real declaration was being thrown away: surrounding whitespace, and capitalisation.
    """
    text = str(value or "").strip().lower()
    return text if text in ladder else ""


def _declared_ceiling(ceiling: str | None, ladder: tuple[str, ...] = _CLAUDE_TIER_ORDER) -> tuple[str, str]:
    """THE one reader of the declared opening ceiling: ``(raw, resolved)``.

    ``resolved`` is ``""`` when ``raw`` names no rung of ``ladder``. Both the ``--ceiling`` flag and
    ``LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER`` land here — D6's "the cap belongs to the VALUE, not one
    accessor", now true of the unknown-value case too and not only of the opus hard cap. Kept as ONE
    reader because two readers of one env var is precisely the fork D2 deleted for the weekly meter.

    An EMPTY declaration is absent, not garbage: it falls through to the default exactly as the
    previous ``or``-chain did. Only a value that genuinely NAMES something the ladder does not
    contain is unresolvable — the distinction matters because ``os.environ.get(k, default)`` hands
    back ``""`` for a set-but-empty var, and turning that into a warning would fire on ``export VAR=``.
    """
    if ceiling is not None and str(ceiling).strip():
        raw = str(ceiling)
    elif ladder == _CLAUDE_TIER_ORDER:
        raw = os.environ.get("LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER", "").strip() or "sonnet"
    else:
        raw = ladder[0]
    return raw, _norm_rung(raw, ladder)


def session_open_max_tier() -> str:
    """The cadence CEILING for an interactive session's OPENING model.

    Registry-declared via ``LIMEN_CLAUDE_SESSION_OPEN_MAX_TIER`` (default ``sonnet``, per
    CLAUDE.md's Session Phase Entry: open cheap, escalate deliberately) and hard-capped at
    ``opus`` — no env value can declare Fable an acceptable opening tier, because Fable is
    reserved behind a written acceptance receipt and an opening default is by definition not one.
    The cap belongs to the VALUE, so every accessor routes through it (D6).

    A plain ``str`` for callers that need one. An unresolvable declaration still degrades to the
    cheapest rung HERE, because this signature has no room to say anything else — that is a declared,
    accepted degradation, not a silent one. Callers that can carry a verdict use
    :func:`opening_verdict`, which reports the unresolvable declaration instead of substituting for it.
    """
    return _cap_tier(_declared_ceiling(None)[1] or "haiku", "opus")


def _cap_rung(rung: str, cap: str, ladder: tuple[str, ...]) -> str:
    """Cap ``rung`` to ``cap`` WITHIN THE GIVEN LADDER — the generic form of :func:`_cap_tier`.

    ``_cap_tier`` hardcodes the Claude ladder and its unknown-value fallbacks (haiku / sonnet), so
    handing it a foreign rung silently collapses to ``haiku``: a codex ``high`` ceiling came back
    as ``'haiku'`` the first time the per-lane census ran. That is this arc's own defect wearing a
    different hat — an unclassifiable value resolving to the cheapest rung instead of saying so —
    which is why the generic path validates against the ladder it was actually handed.

    It still resolves a genuinely unclassifiable rung to ``ladder[0]``: a ``-> str`` signature has no
    verdict channel. :func:`opening_verdict` therefore resolves the ceiling BEFORE calling this, so
    the unresolvable case never reaches here disguised as a value.
    """
    rung = _norm_rung(rung, ladder) or ladder[0]
    cap = _norm_rung(cap, ladder) or ladder[0]
    return ladder[min(_ladder_index(rung, ladder), _ladder_index(cap, ladder))]


def opening_verdict(
    pin: str,
    ceiling: str | None = None,
    ladder: tuple[str, ...] = _CLAUDE_TIER_ORDER,
    hard_cap: str | None = None,
) -> dict:
    """Is an opening model pin at or below the cadence ceiling?

    Returns ``{state, rung, ceiling, pin}`` with state ∈ ``ok`` | ``above-ceiling`` | ``unresolved``.

    ``unresolved`` covers BOTH inputs — an unclassifiable pin and an unclassifiable ceiling — because
    either one makes the comparison unanswerable. ``detail`` says which, so a consumer prints the real
    reason instead of re-deriving a pin-shaped one. There is no fourth state on purpose: the third
    already means "I could not answer this", and splitting it would make every consumer learn a state
    to reach the same conclusion.

    The guard used to ask ``"fable" in model.lower()`` — ONE rung of a four-rung ladder. Every tier
    between the cadence floor and Fable was unguarded, so the operator's saved Opus default (~15x
    sonnet) opened every session with the guard reporting a clean no-op. Guarding a literal string
    guards a value; guarding an ORDINAL guards the policy.

    LADDER-GENERIC (D5), so the per-vendor census reuses it rather than forking: ``ladder`` may be
    any cheapest-first tuple, and the ceiling is capped within THAT ladder. ``hard_cap`` defaults
    to ``opus`` on the Claude ladder — no declaration may make Fable an acceptable opening default,
    since Fable is reserved behind a written acceptance receipt — and to the ladder's top elsewhere,
    because a foreign ladder has no equivalent reserved rung to protect.
    """
    if hard_cap and hard_cap in ladder:
        top = hard_cap
    elif "opus" in ladder:
        top = "opus"
    else:
        top = ladder[-1]
    raw, declared = _declared_ceiling(ceiling, ladder)
    if not declared:
        # THE CEILING IS THE OTHER INPUT. `_cap_rung` would answer this with `ladder[0]` and the
        # verdict would render it as the declared ceiling — so a haiku pin measured against a ceiling
        # nobody declared came back state='ok', trusted=True: a degenerate input returning TRUSTED,
        # which guard_contract names as the one thing a guard must never do. Same defect as the pin
        # side (D3), one argument over, and invisible because it fails toward caution for every pin
        # ABOVE the cheapest rung — no incident, so nothing forced it up.
        return {
            "state": "unresolved",
            "trusted": False,
            "rung": _rung_of(pin, ladder),
            "ceiling": "",  # never render a value nobody declared as the authoritative one
            "pin": pin,
            "detail": (
                f"the declared opening ceiling {raw!r} names no rung of {ladder} — the session's tier "
                f"cannot be placed against a ceiling that could not be resolved"
            ),
        }
    cap = _cap_rung(declared, top, ladder)
    rung = _rung_of(pin, ladder)
    if not rung:
        # `trusted` is present and DERIVED on every branch so this reader speaks the same contract
        # balance_verdict() does — see limen.guard_contract, which owns the shape and the executed
        # proof. It is not imported here: this module's pure-stdlib contract is what lets the
        # non-bypassable shim load it by file path, and that chokepoint outranks the convenience.
        return {"state": "unresolved", "trusted": False, "rung": "", "ceiling": cap, "pin": pin, "detail": ""}
    state = "ok" if _ladder_index(rung, ladder) <= _ladder_index(cap, ladder) else "above-ceiling"
    return {"state": state, "trusted": state == "ok", "rung": rung, "ceiling": cap, "pin": pin, "detail": ""}


def _cap_tier(tier: str, cap: str) -> str:
    """Return ``tier`` capped to ``cap`` in the shared cheap→expensive ladder.

    Both arguments are DECLARATIONS (env values, mostly), so both are normalized: ``"Opus"`` and
    ``" opus "`` are the operator writing ``opus``, and throwing that away was silently handing five
    registry-declared env vars the cheapest rung instead of the tier they asked for. A value that
    names no rung even after normalization still degrades to the cheapest — this signature cannot
    say "unresolvable", which is why the ceiling resolves through :func:`opening_verdict` instead.
    """
    tier = _norm_rung(tier) or "haiku"
    cap = _norm_rung(cap) or "sonnet"
    return _CLAUDE_TIER_ORDER[min(_tier_index(tier), _tier_index(cap))]


def _max_inherited_tier() -> str:
    """The highest tier allowed for inherited/default fleet choices.

    This applies to unclassed shim floors and global ``LIMEN_CLAUDE_MODEL`` pins. Task-specific
    declaration sites can still earn Opus/Fable through the ladder and acceptance gates.
    """
    hard_cap = "fable" if _expensive_model_pin_allowed() else "sonnet"
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_MAX_INHERITED_TIER", "sonnet"), hard_cap)


def _fable_fallback_tier() -> str:
    return _cap_tier(os.environ.get("LIMEN_CLAUDE_FABLE_FALLBACK_TIER", "sonnet"), "opus")


def _expensive_model_pin_allowed() -> bool:
    return os.environ.get("LIMEN_ALLOW_EXPENSIVE_CLAUDE_MODEL_PIN") == "1"


def _large_context_allowed() -> bool:
    return os.environ.get("LIMEN_ALLOW_CLAUDE_1M_CONTEXT") == "1" or _claude_fable_acceptance_present()


def _resolve_claude_model(tier: str) -> str:
    """tier → the ``claude --model`` value. Env pin wins (LIMEN_CLAUDE_<TIER>_MODEL); else the
    bare CLI tier alias, which the ``claude`` CLI resolves to the current dated model itself
    (nothing pinned, survives renames). ([[derive-never-pin-hardcodes]])"""
    model = os.environ.get(f"LIMEN_CLAUDE_{tier.upper()}_MODEL") or tier
    if _claude_model_is_fable(model) and not _claude_fable_acceptance_present():
        return _resolve_claude_model(_fable_fallback_tier()) if tier == "fable" else tier
    # Live weekly-cap backstop: a valid receipt is necessary-not-sufficient. When the week's Fable
    # spend is at/over cap, downgrade to Opus even for an accepted Fable selection (reserve receipts
    # pass only in the 40–50% band). Fail-open when no balance meter is present.
    if _claude_model_is_fable(model):
        capped = _fable_capped_tier(_fable_reserve_receipt_present())
        if capped is not None:
            return _resolve_claude_model(capped)
    if _claude_model_uses_large_context(model) and not _large_context_allowed():
        return tier if tier in _CLAUDE_TIER_ORDER else _max_inherited_tier()
    return model


def _guard_claude_model_pin(model: str | None) -> str | None:
    """Prevent global model pins from turning every inherited fleet spawn expensive.

    Per-task declaration sites still pass explicit ``--model`` values through the shim; those are
    audited by transcript/workflow guards. This guard covers the global default pin
    ``LIMEN_CLAUDE_MODEL``, which otherwise becomes inherited fan-out for unrelated cheap work.
    """
    if _claude_model_is_fable(model) and not _claude_fable_acceptance_present():
        return _resolve_claude_model(_fable_fallback_tier())
    if (_claude_model_is_opus(model) or _claude_model_uses_large_context(model)) and not _expensive_model_pin_allowed():
        return _resolve_claude_model(_max_inherited_tier())
    if _claude_model_uses_large_context(model) and not _large_context_allowed():
        return _resolve_claude_model(_max_inherited_tier())
    return model


def _guard_fable_model_pin(model: str | None) -> str | None:
    """Backward-compatible name for the global Claude model-pin guard."""
    return _guard_claude_model_pin(model)


# ── The non-bypassable shim's per-spawn floor sort ──────────────────────────────────────────
# The shim sits FIRST on the fleet PATH, so every fleet-spawned `claude` resolves to it. It is the
# ENFORCEMENT half of the tiering chain: the rich, per-task SORT happens at the declaration sites
# (dispatch's ladder, converge's tier factory) which pass --model explicitly; the shim GUARANTEES
# nothing escapes that sort to the account default WITHOUT a declaration. The rule:
#
#   • --model already present  → leave it (the declaration site already sorted this spawn);
#   • not a `-p` / `--print` run → leave it (interactive / `claude mcp …` / etc. — never re-tier);
#   • else                      → inject the FLOOR: LIMEN_CLAUDE_SHIM_FLOOR (default "haiku" — the
#                                 SAME tier dispatch's ladder assigns to unclassed work, so this is
#                                 the ladder's own default, NOT a blanket downgrade).
#
# SO THE SHIM IS A FLOOR, NOT A CAP — and in particular it is NOT a second Fable cap. An explicit
# `--model claude-fable-5` rides straight through untouched, by the first rule above; that is the
# documented contract, not an oversight. Fable enforcement lives in exactly two places, and neither
# is here: dispatch's ladder (`_claude_tier_for` → `_earned_fable_tier`, receipt AND live weekly cap)
# and the SessionStart guard. Do not "harden" the shim into a third — it is on the fail-open hot path
# of every fleet spawn, and a cap that must never block a spawn is not a cap.
#
# Subagents default to `inherit`, so this one top-level injection governs the ENTIRE fan-out tree.
# CAVEAT: `claude --resume` ignores --model (a resumed session keeps its BIRTH model), so a resume
# is governed by the tier it was born at — which this shim sets for every NEW session. Fail-open to
# None in every branch (→ bare invocation under the ANTHROPIC_MODEL seatbelt), never block a spawn.


def _shim_floor_tier() -> str:
    """The floor tier for an unclassed fleet spawn.

    ``LIMEN_CLAUDE_SHIM_FLOOR`` tunes it, but inherited/default floors are capped by
    ``LIMEN_CLAUDE_MAX_INHERITED_TIER`` (default Sonnet) so a shell export cannot make trivial
    workers inherit Opus/Fable or 1M context by default.
    """
    tier = _norm_rung(os.environ.get("LIMEN_CLAUDE_SHIM_FLOOR", "haiku"))
    if not tier:
        return "haiku"
    return _cap_tier(tier, _max_inherited_tier())


def model_for_argv(args: list[str]) -> str | None:
    """The ``--model`` value to INJECT for a fleet ``claude`` invocation, or None to leave the
    spawn untouched.

    ``args`` is argv WITHOUT the program name (i.e. ``sys.argv[1:]``). Returns a model string to
    splice in as ``--model <value>``, or None when the spawn must not be touched: it already
    carries --model (a declaration site sorted it), it is not a print/headless run, tiering is
    deliberately gated off, or anything errors (fail-open). Mirrors the precedence of
    ``dispatch._claude_model``: explicit pin > feature gate > derived floor.
    """
    try:
        if any(arg == "--model" or arg.startswith("--model=") for arg in args):
            return None  # the declaration site already sorted this spawn — respect it
        if not ("-p" in args or "--print" in args):
            return None  # interactive / `claude mcp …` / any non-print — never re-tier
        pin = os.environ.get("LIMEN_CLAUDE_MODEL")
        if pin:
            return _guard_claude_model_pin(pin)  # a manual pin wins only inside the expensive gates
        if os.environ.get("LIMEN_CLAUDE_TIER_SELECT", "1") != "1":
            return None  # tiering deliberately disabled → bare invocation (account default)
        return _resolve_claude_model(_shim_floor_tier())
    except Exception:
        return None  # never block a spawn on a sort hiccup


def main(argv: list[str] | None = None) -> int:
    """Debug/inspection entrypoint: print the model :func:`model_for_argv` would inject for the
    given args (nothing if it would leave the spawn untouched). Example:
    ``python -m limen.model_selection -p hello`` → ``haiku``."""
    import sys

    model = model_for_argv(list(argv if argv is not None else sys.argv[1:]))
    if model:
        print(model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
