"""P2-LLM — optional, evidence-constrained interpretation of the day's brief.

Deterministic v1 leaves this dark. When ``OBSERVATORY_LLM=1`` the organ asks a *synthesis*-class
model (Opus, resolved through :mod:`limen.model_selection`) to explain — **in the evidence's own
terms** — why the top mechanisms are legibility wins and how to transfer the top one to the hero.
It invents nothing: the prompt carries only the brief's observed mechanisms / confounders / gaps.

The model is reached the way the whole fleet reaches one — a bounded ``claude -p`` subprocess
(this repo is a dispatch orchestrator, not an SDK consumer; cf. ``dispatch._claude_model``). Every
direction fails open: gate off, ``claude`` binary absent, timeout, non-zero exit, empty output →
``interpretation`` is ``None`` and the deterministic core of the brief is never mutated.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable

from . import config

_TIMEOUT = 60
_MAX_CHARS = 1500  # bound the returned interpretation

# (prompt, model, timeout) -> (text | None, error | None)
Invoke = Callable[[str, str, int], "tuple[str | None, str | None]"]


def _synthesis_model() -> str:
    """The ``claude --model`` value for OBSERVATORY's synthesis class, via model_selection (→ opus).
    Fail-safe to ``opus`` — synthesis is an Opus class by charter."""
    try:
        from limen import model_selection as ms

        tier = "opus" if "synthesis" in ms._claude_opus_classes() else "sonnet"
        return ms._resolve_claude_model(tier)
    except Exception:
        return "opus"


def _evidence_prompt(brief: dict) -> str:
    """A prompt constrained to the observed evidence — no free generation, no new repos."""
    evidence = {
        "hero": brief.get("hero"),
        "mechanisms": brief.get("mechanisms") or [],
        "confounders": brief.get("confounders") or [],
        "experiment": (brief.get("experiment") or {}).get("change") if brief.get("experiment") else None,
        "internal_gaps": brief.get("internal_gaps"),
        "external_gaps": brief.get("external_gaps"),
    }
    return (
        "You are OBSERVATORY's analyst. Using ONLY the JSON evidence below — invent no repos, "
        "features, or numbers not present in it — write at most 6 sentences explaining why these "
        "mechanisms are legibility wins and how to transfer the top one to the hero repo. If the "
        "evidence is empty, say exactly that.\n\n"
        f"EVIDENCE:\n{json.dumps(evidence, sort_keys=True, indent=2)}\n"
    )


def _default_invoke(prompt: str, model: str, timeout: int) -> tuple[str | None, str | None]:
    """Reach a synthesis model via a bounded ``claude -p`` subprocess. Fail-open, never raises."""
    if not shutil.which("claude"):
        return None, "claude binary not found"
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", model],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return None, str(exc)[:120]
    if proc.returncode != 0:
        return None, (proc.stderr or "claude non-zero exit").strip()[:120]
    text = (proc.stdout or "").strip()
    return (text or None), (None if text else "empty output")


def interpret(brief: dict, *, apply: bool = False, invoke: Invoke | None = None) -> dict:
    """Return an evidence-constrained interpretation when ``OBSERVATORY_LLM`` is armed; else inert.

    ``invoke(prompt, model, timeout) -> (text, error)`` is injectable for hermetic tests. Fail-open:
    any fault → ``{"interpretation": None, …}``. The deterministic core of the brief is never
    mutated here — the caller attaches ``interpretation`` only when it is a non-empty string."""
    if not config.get("OBSERVATORY_LLM", 0, cast=int):
        return {"interpretation": None, "model": None, "reason": "off"}
    model = _synthesis_model()
    prompt = _evidence_prompt(brief)
    text, error = (invoke or _default_invoke)(prompt, model, _TIMEOUT)
    clean = text.strip() if isinstance(text, str) else ""
    return {
        "interpretation": clean[:_MAX_CHARS] if clean else None,
        "model": model,
        "evidence_keys": sorted(k for k in ("hero", "mechanisms", "confounders", "experiment") if brief.get(k)),
        "reason": None if clean else (error or "no output"),
    }
