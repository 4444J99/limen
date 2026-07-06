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


def _claude_model_is_fable(model: str | None) -> bool:
    return bool(model and "fable" in str(model).lower())


def _claude_model_is_opus(model: str | None) -> bool:
    return bool(model and "opus" in str(model).lower())


def _claude_model_uses_large_context(model: str | None) -> bool:
    text = str(model or "").lower()
    return bool("1m" in text or "1000000" in text or "1,000,000" in text)


def _tier_index(tier: str) -> int:
    try:
        return _CLAUDE_TIER_ORDER.index(tier)
    except ValueError:
        return 0


def _cap_tier(tier: str, cap: str) -> str:
    """Return ``tier`` capped to ``cap`` in the shared cheap→expensive ladder."""
    if tier not in _CLAUDE_TIER_ORDER:
        tier = "haiku"
    if cap not in _CLAUDE_TIER_ORDER:
        cap = "sonnet"
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
    if (
        (_claude_model_is_opus(model) or _claude_model_uses_large_context(model))
        and not _expensive_model_pin_allowed()
    ):
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
    tier = os.environ.get("LIMEN_CLAUDE_SHIM_FLOOR", "haiku")
    if tier not in _CLAUDE_TIER_ORDER:
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
