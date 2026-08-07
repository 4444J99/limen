"""guard_contract — the invariant "a guard that cannot see must WARN, not pass", executable.

F7 of the 2026-08-07 cadence-guard arc, and the generalization of everything before it. The arc
found the SAME defect four times in one stack:

  * three forked weekly-meter readers typed ``dict | None``, where None meant both "no meter" and
    "a meter I decided not to trust", and every caller read it as permissive;
  * ``_resolve_model`` returning ``""`` for an unresolvable session model, so ``_is_fable("")`` was
    False and the guard exited 0 printing zero bytes — byte-identical to a confirmed-cheap session;
  * an undeployed copy of a guard printing superseded advice with no sign it was pre-merge;
  * an unarmed SessionStart hook indistinguishable from one that ran and found nothing.

One sentence: **a safety guard degrades silently toward "everything is fine" whenever its input is
stale, unresolvable, undeployed, or unarmed — because "I could not resolve this" and "this is fine"
are encoded as the same value** (censor precedent PREC-2026-08-07-guard-degrades-toward-silence).

Fixing four instances by hand leaves the fifth to be discovered by an incident. This module makes
the invariant a THING THE ESTATE CAN RUN.

THE STRUCTURAL HALF — :func:`verdict`. ``trusted`` is DERIVED from ``state``, never passed. A
caller cannot mark an unresolvable state trusted because there is no parameter with which to do
it. That is the short-circuit: it lands before any guard-specific condition, so a new guard gets
the invariant by construction rather than by remembering it.

THE EXECUTED HALF — :func:`check_degrades`. It does not INSPECT a guard for the shape of its code;
it RUNS the guard against degenerate inputs and reads what comes back. Every prior episode of this
class passed inspection: `verify-fable-gate.sh` was green through the whole incident, because the
question it asked was answered correctly by a meter that was itself lying. A proof that is executed
against a degenerate input cannot be satisfied by a plausible-looking implementation.

WHY THIS MODULE IS NOT IMPORTED BY ``model_selection``. That module's docstring pins a hard
contract — pure stdlib, imports nothing from the ``limen`` package — so ``scripts/shims/claude``
can importlib-load it by file path without triggering the package ``__init__`` or depending on
PYTHONPATH. An import here would break the chokepoint that keeps every fleet spawn tiered. So the
readers construct their own verdicts in the same SHAPE, and this module owns the shape, the
normalizer, and the executed proof. :func:`normalize` is what makes that safe: it coerces any
guard's return into the canonical form and REFUSES to guess, so a reader that drifts out of shape
is a finding rather than a silent pass — which is the same rule the invariant states, applied to
the invariant's own enforcement.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager

# The one canonical "everything resolved and is fine" state name. Anything else is a degradation.
OK = "ok"


def verdict(state: str, *, ok_states: Iterable[str] = (OK,), detail: str = "", **extra) -> dict:
    """Build a guard verdict whose ``trusted`` flag is DERIVED, never supplied.

    This is the invariant made structural: there is no argument by which a caller can declare an
    unresolvable state trustworthy. ``extra`` carries guard-specific payload (a parsed balance, an
    age, a provenance) — payload never decides trust.

    Passing ``trusted=`` raises. The first cut of this function spread ``**extra`` LAST, so
    ``verdict("absent", trusted=True)`` silently overwrote the derived value and the structural
    guarantee was decorative — caught by its own test, which is the argument for writing the
    catches-a-violation case before believing a checker. Refusing loudly beats dropping it
    silently: a caller who thought they were setting trust must find out, and a constructor
    argument is a build-time error, never a runtime input a guard has to survive.
    """
    if "trusted" in extra:
        raise TypeError(
            "guard_contract.verdict() derives `trusted` from `state`; passing it is the defect this "
            "contract exists to prevent. Add the state to `ok_states` if it is genuinely resolved."
        )
    allowed = set(ok_states)
    return {**extra, "state": state, "trusted": state in allowed, "detail": detail}


def normalize(obj) -> dict | None:
    """Coerce a guard's return value into ``{state, trusted, detail}``; None if it is not a verdict.

    Deliberately REFUSES to guess. A bare dict without a ``state``, a bare bool, a None — none of
    these are silently read as "fine"; they come back as None so the caller reports "this reader is
    not speaking the contract". Guessing here would reproduce, inside the enforcement mechanism,
    the exact substitution the enforcement exists to forbid.
    """
    if not isinstance(obj, Mapping):
        return None
    if "state" not in obj:
        return None
    state = str(obj.get("state"))
    trusted = obj.get("trusted")
    if not isinstance(trusted, bool):
        trusted = state == OK
    return {"state": state, "trusted": trusted, "detail": str(obj.get("detail") or "")}


@contextmanager
def _env(overrides: Mapping[str, str]):
    """Impose a degenerate environment, then restore it exactly. Restores DELETIONS too, so a case
    that unsets a variable cannot leak into the next one."""
    saved = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def check_degrades(reader: Callable, cases: Iterable[Mapping]) -> list[dict]:
    """EXECUTE ``reader`` under each degenerate case; return the findings (empty == invariant holds).

    Each case is ``{name, env?, args?}``. A finding is raised when the reader, given an input it
    cannot resolve, comes back TRUSTED — or when it comes back in a shape this contract cannot
    read, or raises. A guard that crashes on a degenerate input is not "failing safe": a
    SessionStart hook ends `|| true`, so a crash is indistinguishable from silence at the surface
    that matters.
    """
    findings: list[dict] = []
    for case in cases:
        name = str(case.get("name") or "unnamed")
        args = list(case.get("args") or [])
        overrides = dict(case.get("env") or {})
        try:
            with _env(overrides):
                raw = reader(*args)
        except Exception as exc:  # noqa: BLE001 — a crash IS the finding
            findings.append({"case": name, "why": f"reader raised {type(exc).__name__}: {exc}"})
            continue
        v = normalize(raw)
        if v is None:
            findings.append({"case": name, "why": f"reader returned {type(raw).__name__}, not a verdict"})
            continue
        if v["trusted"]:
            findings.append(
                {"case": name, "why": f"degenerate input returned TRUSTED (state={v['state']!r}) — it must not"}
            )
    return findings
