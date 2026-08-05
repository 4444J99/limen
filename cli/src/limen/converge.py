"""converge() — the convergence half of the conductor loop.

Limen's ``scripts/route.py`` is *divergence*: it fans ONE task across many vendor
lanes so the idea gets attacked from N angles. ``converge()`` is the reverse arrow:
it takes the N divergent shots at one idea and alchemically distills them into the
ONE better version that supersedes them — keeping the losers as cited provenance
(nothing destroyed) and surfacing the gaps as the next divergent shots to fire.

    route.py   :  idea ──► [shot_1, shot_2, ... shot_N]      (divergence / dispatch)
    converge() :  idea + [shot_1 ... shot_N] ──► better_version
                                                 + cited_losers   (provenance)
                                                 + next_shots      (re-divergence)

The pipeline (see :func:`converge`):

    1. ranker.rank(idea, shots)         -> influence/quality order
    2. synthesizer.synthesize(idea, .)  -> THE ALCHEMY: better_version + kept/dropped
    3. scorer.score(idea, better, shots)-> is the distillate good enough?
    4. if score >= threshold: promoter.promote(...)   (reversible)
       else:                  promoter.rollback()     (nothing destroyed)
    5. gap_finder.gaps(idea, shots)     -> dead-zones => next divergent shots

Everything is wired through small :class:`typing.Protocol` contracts so the organ
can run with dependency-free fallbacks (:class:`LexicalRanker`,
:class:`DeterministicScorer`, :class:`NoopPromoter`, :class:`LexicalGapFinder`) or
with REAL adapters into the wider system. All real adapters are **import-guarded**
with ``try/except ImportError`` so this module imports cleanly WITHOUT them
installed — each raises a clear error only when actually constructed/used:

  * :class:`MeshRanker` / :class:`MeshGapFinder` — wrap the ``mesh`` repo
    (``~/Workspace/organvm-i-theoria/mesh``, which needs its OWN ``.venv``):
    ranking via ``mesh.primitives.link.InfluenceLinker.pagerank`` (or the
    ``mesh influence`` CLI); gaps via
    ``mesh.primitives.query.StructuralDeadZoneEngine.analyze`` (or
    ``mesh dead-zones --structural``).
  * :class:`AnthropicSynthesizer` — THE CORE alchemy. Calls the Anthropic SDK
    (``anthropic`` package, import-guarded) with the ranked shots and asks for ONE
    better version plus the kept/dropped accounting. The model is DERIVED per tier by
    :func:`resolve_tier_model` (env-overridable; sonnet falls back to the current
    sonnet model via the ``claude`` CLI), never pinned, and :class:`LadderSynthesizer`
    climbs the tiers haiku→sonnet→opus under a cheap :class:`Scorer` gate.
  * :class:`CCEPromoter` — wraps ``conversation_corpus_engine.corpus_candidates``:
    promote = ``stage_corpus_candidate`` -> ``review_corpus_candidate(decision=
    'approve')`` -> ``promote_corpus_candidate``; rollback =
    ``rollback_corpus_promotion``. Import-guarded.

CLI (dependency-free in ``--dry-run``)::

    python -m limen.converge --idea "..." --shot path_or_text ... [--dry-run]

``--dry-run`` uses only the fallback adapters: no network, no mesh, no CCE.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import functools
from pathlib import Path
from typing import Protocol, runtime_checkable


# ─── Data model ──────────────────────────────────────────────────────


@dataclass
class Shot:
    """One divergent attempt at an idea (a draft, a lane output, a session-meta turn)."""

    id: str
    text: str
    source: str = ""


@dataclass
class ConvergeResult:
    """The distilled outcome of one convergence cycle."""

    better_version: str
    cited_losers: list[Shot] = field(default_factory=list)
    next_shots: list[str] = field(default_factory=list)
    promoted: bool = False
    score: float = 0.0


@dataclass
class Synthesis:
    """What a :class:`Synthesizer` returns: the distillate plus its accounting.

    ``kept_ids`` / ``dropped_ids`` reference :attr:`Shot.id` values. ``cited_losers``
    in the final :class:`ConvergeResult` is the ranked set minus the kept ids, so a
    synthesizer only has to report what it *kept* for the provenance to be correct.
    """

    better_version: str
    kept_ids: list[str] = field(default_factory=list)
    dropped_ids: list[str] = field(default_factory=list)


# ─── Protocols (the swappable contracts) ─────────────────────────────


@runtime_checkable
class Ranker(Protocol):
    def rank(self, idea: str, shots: list[Shot]) -> list[Shot]:
        """Return shots in influence/quality order (best first)."""
        ...


@runtime_checkable
class Synthesizer(Protocol):
    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:
        """THE ALCHEMY: fold the ranked shots into one better version."""
        ...


@runtime_checkable
class Scorer(Protocol):
    def score(self, idea: str, better_version: str, shots: list[Shot]) -> float:
        """Score the distillate in ``[0.0, 1.0]`` — the promotion gate."""
        ...


@runtime_checkable
class Promoter(Protocol):
    def promote(self, idea: str, better_version: str) -> None:
        """Stage + accept the better version (must be reversible)."""
        ...

    def rollback(self) -> None:
        """Undo a staged promotion; destroy nothing."""
        ...


@runtime_checkable
class GapFinder(Protocol):
    def gaps(self, idea: str, shots: list[Shot]) -> list[str]:
        """Return dead-zones as next divergent shots to fire."""
        ...


# ─── The organ ───────────────────────────────────────────────────────


def converge(
    idea: str,
    shots: list[Shot],
    *,
    ranker: Ranker,
    synthesizer: Synthesizer,
    scorer: Scorer,
    promoter: Promoter,
    gap_finder: GapFinder,
    threshold: float = 0.7,
) -> ConvergeResult:
    """Distill ``shots`` at ``idea`` into the one better version.

    See the module docstring for the conceptual picture. Steps:

    1. ``ranked   = ranker.rank(idea, shots)``
    2. ``result   = synthesizer.synthesize(idea, ranked)``
    3. ``score    = scorer.score(idea, result.better_version, shots)``
    4. ``score >= threshold`` → ``promoter.promote(...)``, ``promoted=True``;
       else ``promoter.rollback()``, ``promoted=False`` (reversible, nothing lost).
    5. ``next     = gap_finder.gaps(idea, shots)``

    ``cited_losers`` is the ranked set minus the shots the synthesizer kept, in
    rank order — the losers preserved as provenance.
    """
    ranked = ranker.rank(idea, shots)

    result = synthesizer.synthesize(idea, ranked)

    score = scorer.score(idea, result.better_version, shots)

    if score >= threshold:
        promoter.promote(idea, result.better_version)
        promoted = True
    else:
        promoter.rollback()
        promoted = False

    next_shots = gap_finder.gaps(idea, shots)

    kept = set(result.kept_ids)
    cited_losers = [shot for shot in ranked if shot.id not in kept]

    return ConvergeResult(
        better_version=result.better_version,
        cited_losers=cited_losers,
        next_shots=next_shots,
        promoted=promoted,
        score=score,
    )


# ─── Dependency-free fallback adapters ───────────────────────────────


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t}


class LexicalRanker:
    """Rank shots by lexical overlap with the idea (best first), no deps.

    A cheap stand-in for the influence/PageRank order that :class:`MeshRanker`
    produces. Ties broken by descending length then id for determinism.
    """

    def rank(self, idea: str, shots: list[Shot]) -> list[Shot]:
        idea_tokens = _tokens(idea)

        def key(shot: Shot) -> tuple[int, int, str]:
            overlap = len(idea_tokens & _tokens(shot.text))
            return (-overlap, -len(shot.text), shot.id)

        return sorted(shots, key=key)


class DeterministicScorer:
    """Score a distillate by idea-coverage, no deps / no network.

    Fraction of the idea's tokens present in ``better_version``, so an empty or
    off-topic distillate scores low (falls below ``threshold`` → rollback) and a
    distillate that covers the idea scores high (→ promote). Deterministic.
    """

    def score(self, idea: str, better_version: str, shots: list[Shot]) -> float:
        idea_tokens = _tokens(idea)
        if not idea_tokens:
            return 1.0 if better_version.strip() else 0.0
        covered = idea_tokens & _tokens(better_version)
        return len(covered) / len(idea_tokens)


class NoopPromoter:
    """Records promote/rollback calls without external side effects (dry-run)."""

    def __init__(self) -> None:
        self.promoted: tuple[str, str] | None = None
        self.rolled_back = False

    def promote(self, idea: str, better_version: str) -> None:
        self.promoted = (idea, better_version)

    def rollback(self) -> None:
        self.rolled_back = True


class LexicalGapFinder:
    """Surface idea tokens that NO shot covered as next divergent shots, no deps.

    A cheap stand-in for :class:`MeshGapFinder`'s structural dead-zone analysis.
    """

    def gaps(self, idea: str, shots: list[Shot]) -> list[str]:
        idea_tokens = _tokens(idea)
        covered: set[str] = set()
        for shot in shots:
            covered |= _tokens(shot.text)
        missing = sorted(idea_tokens - covered)
        return [f"explore: {term}" for term in missing]


class ConcatSynthesizer:
    """Fallback alchemy: keep the top shots, concatenate them as the distillate.

    Not intelligent — it keeps every shot whose lexical overlap with the idea is at
    least the best shot's, drops the rest, and joins the kept texts. Real distillation
    is :class:`AnthropicSynthesizer`. This keeps ``--dry-run`` fully offline.
    """

    def __init__(self, keep: int = 0) -> None:
        # keep=0 means "keep shots tied for best overlap"; keep>0 keeps the top N.
        self.keep = keep

    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:
        if not ranked:
            return Synthesis(better_version="", kept_ids=[], dropped_ids=[])

        if self.keep > 0:
            kept = ranked[: self.keep]
        else:
            idea_tokens = _tokens(idea)
            best = len(idea_tokens & _tokens(ranked[0].text))
            kept = [s for s in ranked if len(idea_tokens & _tokens(s.text)) >= best] or [ranked[0]]

        kept_ids = [s.id for s in kept]
        dropped_ids = [s.id for s in ranked if s.id not in set(kept_ids)]
        better = "\n\n".join(s.text for s in kept)
        return Synthesis(better_version=better, kept_ids=kept_ids, dropped_ids=dropped_ids)


# ─── REAL adapters (each import-guarded) ─────────────────────────────


class MeshRanker:
    """Rank shots by mesh INFLUENCE (PageRank over the reference graph).

    Wraps ``mesh.primitives.link.InfluenceLinker.pagerank`` from the mesh repo at
    ``~/Workspace/organvm-i-theoria/mesh``. **mesh needs its OWN ``.venv``** — its
    deps are not in limen's environment — so this import is guarded and only fires
    when the adapter is constructed. If mesh's package isn't importable, fall back
    to shelling out to the ``mesh influence`` CLI by passing ``use_cli=True``.

    ``shot.source`` is used as the node hash; ``shot.id`` is the fallback hash.
    Reference edges must be supplied (ideas rarely arrive with a graph), so this
    builds a trivial self-referencing edge set when none is given — real callers
    pass ``edges`` derived from the corpus.
    """

    def __init__(self, *, edges: list | None = None, use_cli: bool = False) -> None:
        self._edges = edges
        self._use_cli = use_cli
        if not use_cli:
            try:
                from mesh.primitives.link import Edge, InfluenceLinker
            except ImportError as exc:  # pragma: no cover - requires mesh .venv
                raise ImportError(
                    "MeshRanker requires the 'mesh' package "
                    "(~/Workspace/organvm-i-theoria/mesh, which needs its own .venv). "
                    "Install it, or construct MeshRanker(use_cli=True) to shell out to "
                    "the 'mesh influence' CLI."
                ) from exc
            self._Edge = Edge
            self._linker = InfluenceLinker()

    def _node_hash(self, shot: Shot) -> str:
        return shot.source or shot.id

    def rank(self, idea: str, shots: list[Shot]) -> list[Shot]:  # pragma: no cover - requires mesh
        if self._use_cli:
            return self._rank_via_cli(idea, shots)

        edges = self._edges
        if edges is None:
            # No reference graph supplied: build self-edges so PageRank is defined.
            edges = [self._Edge(self._node_hash(s), self._node_hash(s), "REFERENCE", 1.0) for s in shots]
        scores = self._linker.pagerank(edges)
        return sorted(shots, key=lambda s: scores.get(self._node_hash(s), 0.0), reverse=True)

    def _rank_via_cli(self, idea: str, shots: list[Shot]) -> list[Shot]:  # pragma: no cover - requires mesh CLI
        import json
        import subprocess

        proc = subprocess.run(["mesh", "influence", "--json"], capture_output=True, text=True, check=True)
        scores = json.loads(proc.stdout or "{}")
        return sorted(shots, key=lambda s: scores.get(self._node_hash(s), 0.0), reverse=True)


class MeshGapFinder:
    """Find dead-zones via mesh structural analysis -> next divergent shots.

    Wraps ``mesh.primitives.query.StructuralDeadZoneEngine.analyze`` (or the
    ``mesh dead-zones --structural`` CLI with ``use_cli=True``). Same mesh-.venv
    caveat as :class:`MeshRanker`. Requires a mesh registry path and a populated
    mesh ``Store``; the highest-severity dead-zones become next shots.
    """

    def __init__(
        self,
        registry_path: str | Path,
        *,
        store=None,
        entity_glob: str | None = None,
        threshold: float = 0.3,
        limit: int = 10,
        use_cli: bool = False,
    ) -> None:
        self._registry_path = Path(registry_path)
        self._store = store
        self._limit = limit
        self._use_cli = use_cli
        if not use_cli:
            try:
                from mesh.primitives.query import StructuralDeadZoneEngine
            except ImportError as exc:  # pragma: no cover - requires mesh .venv
                raise ImportError(
                    "MeshGapFinder requires the 'mesh' package "
                    "(~/Workspace/organvm-i-theoria/mesh, which needs its own .venv). "
                    "Install it, or construct MeshGapFinder(..., use_cli=True) to shell "
                    "out to the 'mesh dead-zones --structural' CLI."
                ) from exc
            self._engine = StructuralDeadZoneEngine(self._registry_path, entity_glob=entity_glob, threshold=threshold)

    def gaps(self, idea: str, shots: list[Shot]) -> list[str]:  # pragma: no cover - requires mesh
        if self._use_cli:
            return self._gaps_via_cli(idea, shots)
        report = self._engine.analyze(self._store)
        out: list[str] = []
        for dz in report.dead_zones[: self._limit]:
            label = getattr(dz, "atom_title", "") or getattr(dz, "atom_content_preview", "")
            out.append(f"explore dead-zone: {label}".strip())
        return out

    def _gaps_via_cli(self, idea: str, shots: list[Shot]) -> list[str]:  # pragma: no cover - requires mesh CLI
        import json
        import subprocess

        proc = subprocess.run(
            ["mesh", "dead-zones", "--structural", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout or "{}")
        zones = payload.get("dead_zones", [])[: self._limit]
        return [f"explore dead-zone: {z.get('atom_title', '')}".strip() for z in zones]


# ─── Earned-tier model ladder (haiku-first-with-cheap-verify) ────────

LADDER_TIERS: tuple[str, ...] = ("haiku", "sonnet", "opus")

# Tier-to-model resolution — derives the concrete API model ID from the claude CLI
# at runtime ([[derive-never-pin]]). Each tier is independently overridable via
# LIMEN_CONVERGE_MODEL_<TIER>. The cache ensures at most one CLI call per tier per
# process lifetime — the model for a tier changes at most with a CLI update.


@functools.lru_cache(maxsize=8)
def _resolve_api_model(tier: str) -> str:
    """Resolve a tier alias to an API model ID by querying the claude CLI.

    Calls ``claude -p ... --model <tier> --output-format json`` and extracts
    the resolved model name from the init/assistant metadata. The result is
    cached per tier so the CLI is called at most once per process lifetime.

    Raises RuntimeError if the claude CLI is not on PATH or the call fails.
    """
    import json as _json
    import shutil as _shutil
    import subprocess as _subprocess

    binary = _shutil.which("claude")
    if not binary:
        raise RuntimeError(
            f"LIMEN_CONVERGE_MODEL_{tier.upper()} not set and 'claude' CLI not found "
            f"on PATH. Set LIMEN_CONVERGE_MODEL_{tier.upper()}=<model-id> or install "
            f"the claude CLI to auto-resolve tier '{tier}'."
        )
    proc = _subprocess.run(
        [binary, "-p", ".", "--model", tier, "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed to resolve tier '{tier}' (rc={proc.returncode}): "
            f"{(proc.stderr or '')[:200]}. "
            f"Set LIMEN_CONVERGE_MODEL_{tier.upper()}=<model-id> to bypass."
        )
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        # The first line of --output-format json is a list containing the init object
        if isinstance(obj, list):
            obj = obj[0] if obj else {}
        if obj.get("type") == "assistant":
            msg = obj.get("message") or {}
            model = msg.get("model")
            if model:
                return model
    raise RuntimeError(
        f"Could not locate model in claude CLI output for tier '{tier}'. "
        f"Set LIMEN_CONVERGE_MODEL_{tier.upper()}=<model-id> to bypass."
    )


def resolve_tier_model(tier: str, *, cli: bool = False) -> str:
    """Resolve a ladder tier to the model string, env-override-first (derive-never-pin).

    Resolution order for this Claude-only synthesis surface:
      1. ``LIMEN_CONVERGE_MODEL_<TIER>`` — an explicit pin always wins (api or cli);
      2. ``cli=True``  → the bare CLI tier alias (``haiku``/``sonnet``/``opus``); the
         ``claude`` CLI resolves it to the current dated model, so nothing is pinned and
         it survives model renames;
         ``cli=False`` → the derived API model id from the ``claude`` CLI
         (:func:`_resolve_api_model`), cached per tier.
    """
    import os

    env = os.environ.get(f"LIMEN_CONVERGE_MODEL_{tier.upper()}")
    if env:
        return env
    if cli:
        return tier
    return _resolve_api_model(tier)


class AnthropicSynthesizer:
    """THE CORE alchemy — fold the ranked shots into ONE better version via Claude.

    Calls the Anthropic SDK (``anthropic`` package, import-guarded) and prompts the
    model to produce a single better version that *supersedes* the shots, and to
    report which shots it kept vs dropped. The model returns a small JSON object so
    the kept/dropped accounting is machine-readable.

    The default model is DERIVED from the sonnet tier via :func:`resolve_tier_model`
    (env ``LIMEN_CONVERGE_MODEL_SONNET``; falls back to the current sonnet model
    via the ``claude`` CLI) rather than pinned here. Override with ``model=``. The
    Anthropic client reads ``ANTHROPIC_API_KEY`` from the environment by default.
    """

    _PROMPT = (
        "You are the convergence organ of a multi-vendor agent conductor. You are "
        "given ONE idea and N divergent shots at it (drafts, lane outputs, dialogue "
        "turns), already ranked best-first by influence/quality.\n\n"
        "Alchemically distill them into ONE better version that SUPERSEDES all of "
        "them: boil to essence, keep what each shot got right, drop what is weaker "
        "or redundant. This is distillation, not concatenation and not janitorial "
        "dedup.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '  "better_version": string  — the single distilled result\n'
        '  "kept_ids": [string]      — ids of shots whose substance you kept\n'
        '  "dropped_ids": [string]   — ids of shots you dropped (cited as losers)\n'
    )

    def __init__(self, *, model: str | None = None, max_tokens: int = 4096, client=None) -> None:
        self.model = model or resolve_tier_model("sonnet", cli=False)
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - requires anthropic
                raise ImportError(
                    "AnthropicSynthesizer requires the 'anthropic' package "
                    "(`pip install anthropic`) and ANTHROPIC_API_KEY in the environment, "
                    "or pass an explicit client=."
                ) from exc
            self._client = anthropic.Anthropic()

    def _render_shots(self, ranked: list[Shot]) -> str:
        blocks = []
        for i, shot in enumerate(ranked, start=1):
            src = f" (source: {shot.source})" if shot.source else ""
            blocks.append(f"[rank {i}] id={shot.id}{src}\n{shot.text}")
        return "\n\n".join(blocks)

    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:  # pragma: no cover - requires network
        import json

        user = f"{self._PROMPT}\n\nIDEA:\n{idea}\n\nSHOTS (best-first):\n{self._render_shots(ranked)}"
        # The resolved model determines which thinking feature set applies.
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Model didn't return clean JSON: treat the whole reply as the distillate,
            # keep the top shot, drop the rest — never lose the alchemy.
            kept = [ranked[0].id] if ranked else []
            return Synthesis(
                better_version=text,
                kept_ids=kept,
                dropped_ids=[s.id for s in ranked[1:]],
            )
        return Synthesis(
            better_version=payload.get("better_version", ""),
            kept_ids=list(payload.get("kept_ids", [])),
            dropped_ids=list(payload.get("dropped_ids", [])),
        )


class ClaudeCliSynthesizer:
    """THE CORE alchemy, KEYLESS — fold the ranked shots into ONE better version via
    the ``claude`` CLI's print mode (``claude -p``) instead of the raw Anthropic API.

    Why this exists: the live daemon dispatches the ``claude`` lane through the CLI,
    which authenticates from the local subscription session — it has **no
    ``ANTHROPIC_API_KEY``**. :class:`AnthropicSynthesizer` needs that key, so under the
    daemon it silently fell back to the offline (concat) kit and the convergence
    write-back never happened ("there and back again" never closed). This synthesizer
    needs no key and spends nothing beyond the CLI budget already in use, so it is the
    middle rung of the kit cascade: raw API (key present) → claude CLI (keyless) →
    offline preview. Same JSON contract + same fail-soft parsing as the API path.
    """

    _PROMPT = AnthropicSynthesizer._PROMPT

    def __init__(self, *, model: str | None = None, timeout: int | None = None, binary: str = "claude") -> None:
        import os
        import shutil

        self.model = model
        # Full face distillation via `claude -p` routinely exceeds a couple minutes
        # (large reduced faces + many shots); a too-short timeout skips the heaviest,
        # most-valuable faces every cadence. Generous default, env-overridable for the
        # outliers — a timeout fail-opens (face skipped, retried next beat), never corrupts.
        self.timeout = int(os.environ.get("LIMEN_CORPUS_SYNTH_TIMEOUT", "600")) if timeout is None else timeout
        self._binary = shutil.which(binary) or binary
        if shutil.which(binary) is None:
            raise FileNotFoundError(
                f"ClaudeCliSynthesizer requires the '{binary}' CLI on PATH "
                "(the keyless, subscription-authed print mode). Install it, or use "
                "AnthropicSynthesizer with ANTHROPIC_API_KEY for the raw-API path."
            )

    def _render_shots(self, ranked: list[Shot]) -> str:
        blocks = []
        for i, shot in enumerate(ranked, start=1):
            src = f" (source: {shot.source})" if shot.source else ""
            blocks.append(f"[rank {i}] id={shot.id}{src}\n{shot.text}")
        return "\n\n".join(blocks)

    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:  # pragma: no cover - requires claude CLI
        import json
        import subprocess

        user = f"{self._PROMPT}\n\nIDEA:\n{idea}\n\nSHOTS (best-first):\n{self._render_shots(ranked)}"
        argv = [self._binary, "-p", *(["--model", self.model] if self.model else []), user]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout, check=False)
        text = (proc.stdout or "").strip()
        if proc.returncode != 0 or not text:
            # Fail LOUD so the kit cascade / per-face guard can fall through to the next
            # rung — never a silent offline no-op masquerading as a converged write.
            raise RuntimeError(f"claude CLI synth failed (rc={proc.returncode}): {(proc.stderr or '')[:200]}")
        # The CLI may wrap the JSON in a ```json fence; strip a single leading/trailing fence.
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[: text.rstrip().rfind("```")]
            text = text.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Not clean JSON: treat the whole reply as the distillate, keep the top shot,
            # drop the rest — never lose the alchemy (same policy as AnthropicSynthesizer).
            kept = [ranked[0].id] if ranked else []
            return Synthesis(
                better_version=text,
                kept_ids=kept,
                dropped_ids=[s.id for s in ranked[1:]],
            )
        return Synthesis(
            better_version=payload.get("better_version", ""),
            kept_ids=list(payload.get("kept_ids", [])),
            dropped_ids=list(payload.get("dropped_ids", [])),
        )


class LadderSynthesizer:
    """Earned-tier ladder — Haiku-first-with-cheap-verify, escalate only on a failed check.

    Wraps a per-tier *factory* (one synthesis MECHANISM — API or CLI — parametrised by
    tier) plus the SAME cheap :class:`Scorer` ``converge()`` uses. Drafts at the cheapest
    tier, scores it, accepts if ``score >= threshold``; only on a failed check does it
    spend the next rung up (haiku → sonnet → opus). The tier ladder nests INSIDE one
    availability rung (api/cli/offline is the kit's job) so it never double-spends the
    cascade, and each tier is built at most once and only when reached — no double-spend
    within the ladder either.

    Fail-open and bounded: a per-rung failure (timeout, API/CLI error) is swallowed and
    the next rung tried; if every rung fails the gate, the BEST-scoring draft is returned;
    if every rung RAISES, an empty :class:`Synthesis` is returned so ``converge()`` scores
    it low and rolls back — never an exception up the stack, never a corrupting write.
    Capped at the top tier (no infinite escalation).

    The cheapest rung is built EAGERLY in ``__init__`` so a missing MECHANISM (no
    ``claude`` CLI / no ``anthropic`` package) raises here at construction — exactly as the
    single-tier synthesizer did — keeping the kit's construction-time api→cli→offline
    fallback intact. Higher rungs stay lazy.
    """

    def __init__(
        self,
        *,
        tier_factory,
        scorer: Scorer,
        threshold: float = 0.7,
        tiers: tuple[str, ...] = LADDER_TIERS,
    ) -> None:
        self._factory = tier_factory
        self._scorer = scorer
        self._threshold = threshold
        self._tiers = tiers
        # Eager cheapest rung: validates the mechanism at construction (see docstring).
        self._built: dict[str, Synthesizer] = {tiers[0]: tier_factory(tiers[0])}

    def _tier(self, tier: str) -> Synthesizer:
        if tier not in self._built:
            self._built[tier] = self._factory(tier)
        return self._built[tier]

    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:
        best: Synthesis | None = None
        best_score = -1.0
        for tier in self._tiers:
            try:
                result = self._tier(tier).synthesize(idea, ranked)
            except Exception:
                continue  # fail-open per rung — try the next, never corrupt
            score = self._scorer.score(idea, result.better_version, ranked)
            if score >= self._threshold:
                return result  # cheap check PASSED — accept, spend no higher rung
            if score > best_score:
                best, best_score = result, score
        if best is not None:
            return best  # all rungs failed the gate → accept the best draft (fail-open)
        # every rung RAISED → empty Synthesis so converge() scores low and rolls back
        return Synthesis(better_version="", kept_ids=[], dropped_ids=[s.id for s in ranked])


class CCEPromoter:
    """Reversible promotion via conversation_corpus_engine.corpus_candidates.

    promote = ``stage_corpus_candidate`` -> ``review_corpus_candidate(decision=
    'approve')`` -> ``promote_corpus_candidate``; rollback =
    ``rollback_corpus_promotion``. All import-guarded (the CCE repo lives at
    ``~/Workspace/organvm-i-theoria/conversation-corpus-engine`` and needs to be
    importable). The better version must already be materialised as a candidate
    corpus directory (``candidate_root``) — CCE promotes corpora, not raw strings —
    so the caller supplies that path; ``promote()`` stages/reviews/promotes it.
    """

    def __init__(
        self,
        project_root: str | Path,
        candidate_root: str | Path,
        *,
        provider: str | None = None,
        live_corpus_id: str | None = None,
    ) -> None:
        try:
            from conversation_corpus_engine import corpus_candidates
        except ImportError as exc:  # pragma: no cover - requires CCE
            raise ImportError(
                "CCEPromoter requires the 'conversation_corpus_engine' package "
                "(~/Workspace/organvm-i-theoria/conversation-corpus-engine on the path)."
            ) from exc
        self._cc = corpus_candidates
        self._project_root = Path(project_root)
        self._candidate_root = Path(candidate_root)
        self._provider = provider
        self._live_corpus_id = live_corpus_id
        self._candidate_id: str | None = None

    def promote(self, idea: str, better_version: str) -> None:  # pragma: no cover - requires CCE
        manifest = self._cc.stage_corpus_candidate(
            self._project_root,
            candidate_root=self._candidate_root,
            live_corpus_id=self._live_corpus_id,
            provider=self._provider,
            note=f"converge: {idea}",
        )
        self._candidate_id = manifest["candidate_id"]
        self._cc.review_corpus_candidate(
            self._project_root, self._candidate_id, decision="approve", note="converge auto-approve"
        )
        self._cc.promote_corpus_candidate(self._project_root, self._candidate_id, note=f"converge: {idea}")

    def rollback(self) -> None:  # pragma: no cover - requires CCE
        # Reversible: undo the most recent promotion. Safe to call even if nothing
        # was promoted in THIS cycle (e.g. score fell below threshold) — CCE raises
        # if there is no promotion history, which we swallow as a no-op.
        try:
            self._cc.rollback_corpus_promotion(self._project_root, target="previous", note="converge rollback")
        except ValueError:
            pass


class CCEScorer:
    """Optional CCE-backed gate via ``conversation_corpus_engine.evaluation``.

    Wraps ``run_corpus_evaluation`` as the promotion gate when CCE is available;
    import-guarded. The mapping from a corpus-evaluation report to a ``[0,1]`` score
    is corpus-specific, so callers pass an ``extract`` callable; the default reads a
    common ``overall_score`` field and falls back to ``0.0``.
    """

    def __init__(self, project_root: str | Path, *, extract=None, **eval_kwargs) -> None:
        try:
            from conversation_corpus_engine.evaluation import run_corpus_evaluation
        except ImportError as exc:  # pragma: no cover - requires CCE
            raise ImportError(
                "CCEScorer requires the 'conversation_corpus_engine' package "
                "(~/Workspace/organvm-i-theoria/conversation-corpus-engine on the path)."
            ) from exc
        self._run = run_corpus_evaluation
        self._project_root = Path(project_root)
        self._eval_kwargs = eval_kwargs
        self._extract = extract or (lambda report: float(getattr(report, "overall_score", 0.0) or 0.0))

    def score(self, idea: str, better_version: str, shots: list[Shot]) -> float:  # pragma: no cover - requires CCE
        report = self._run(self._project_root, **self._eval_kwargs)
        return self._extract(report)


# ─── CLI ─────────────────────────────────────────────────────────────


def _load_shot(spec: str, index: int) -> Shot:
    """Resolve a --shot argument: an existing file path's contents, else literal text."""
    path = Path(spec).expanduser()
    if path.is_file():
        return Shot(id=f"shot-{index}", text=path.read_text(), source=str(path))
    return Shot(id=f"shot-{index}", text=spec, source="inline")


def _build_dry_run_kit() -> dict:
    """The fully offline fallback adapter set used by --dry-run."""
    return {
        "ranker": LexicalRanker(),
        "synthesizer": ConcatSynthesizer(),
        "scorer": DeterministicScorer(),
        "promoter": NoopPromoter(),
        "gap_finder": LexicalGapFinder(),
    }


def _api_tier_factory(client=None):
    """tier → an :class:`AnthropicSynthesizer` at that tier's resolved API model id
    (the raw-API rung, derived from the ``claude`` CLI). ``client`` is the
    test/injection seam, threaded to every rung."""

    def build(tier: str) -> Synthesizer:
        model = resolve_tier_model(tier, cli=False)
        if client is not None:
            return AnthropicSynthesizer(model=model, client=client)
        return AnthropicSynthesizer(model=model)

    return build


def _cli_tier_factory():
    """tier → a :class:`ClaudeCliSynthesizer` at that tier's CLI alias (the keyless,
    subscription-authed live-daemon rung)."""

    def build(tier: str) -> Synthesizer:
        return ClaudeCliSynthesizer(model=resolve_tier_model(tier, cli=True))

    return build


def _build_live_kit(args, *, anthropic_client=None) -> dict:
    """The live adapter set for --live: REAL synthesis, promotion gated OFF by default.

    This is the runbook's Step 3 made runnable — the real :class:`AnthropicSynthesizer`
    (the alchemy) with a :class:`NoopPromoter`, so the distillate can be inspected with
    no irreversible side effect. Ranking/gaps default to the dependency-free lexical
    fallbacks (mesh needs its own ``.venv``); ``--mesh`` opts into the mesh CLI adapters.

    Promotion stays behind the explicit ``--promote`` flag (the "gate the irreversible"
    invariant): only then is the reversible :class:`CCEPromoter` wired in, and it
    requires both candidate paths. ``anthropic_client`` is an injection seam for tests
    — left ``None`` in real use so :class:`AnthropicSynthesizer` builds its own client.
    """
    # Ranker / gap-finder: lexical fallbacks unless --mesh (mesh CLI; its own .venv).
    if getattr(args, "mesh", False):
        ranker: Ranker = MeshRanker(use_cli=True)
        gap_finder: GapFinder = (
            MeshGapFinder(args.mesh_registry, use_cli=True)
            if getattr(args, "mesh_registry", None)
            else LexicalGapFinder()
        )
    else:
        ranker = LexicalRanker()
        gap_finder = LexicalGapFinder()

    # Synthesis: the core alchemy, now an EARNED-TIER LADDER (haiku-first-with-cheap-verify,
    # escalate only on a failed check) nested INSIDE the availability cascade. The cascade
    # ([[cascade-fallback-principle]] / never a silent no) still picks the MECHANISM first —
    #   injected client (tests) or ANTHROPIC_API_KEY → raw API (spends);
    #   else the KEYLESS subscription-authed `claude -p` CLI — the live-daemon path, whose
    #   launchd env carries no key, so this rung closes the capture→converge write-back.
    # The ladder then climbs tiers WITHIN the chosen mechanism (it eagerly builds its
    # cheapest rung, so a missing mechanism still raises here just like before). An explicit
    # --model pins one tier (opts out of the ladder); LIMEN_CONVERGE_LADDER=0 disables it
    # (rollback to single-tier). Threshold = converge's own promote gate, so an accepted
    # rung also promotes — no surprise rollback of a ladder-accepted draft.
    import os

    model_kwarg = {"model": args.model} if getattr(args, "model", None) else {}
    ladder_on = os.environ.get("LIMEN_CONVERGE_LADDER", "1") == "1" and not getattr(args, "model", None)
    threshold = getattr(args, "threshold", 0.7)
    scorer = DeterministicScorer()  # the cheap gate — same instance the kit returns below

    if anthropic_client is not None:
        synthesizer: Synthesizer = (
            LadderSynthesizer(tier_factory=_api_tier_factory(anthropic_client), scorer=scorer, threshold=threshold)
            if ladder_on
            else AnthropicSynthesizer(client=anthropic_client, **model_kwarg)
        )
    elif os.environ.get("ANTHROPIC_API_KEY"):
        synthesizer = (
            LadderSynthesizer(tier_factory=_api_tier_factory(), scorer=scorer, threshold=threshold)
            if ladder_on
            else AnthropicSynthesizer(**model_kwarg)
        )
    else:
        synthesizer = (
            LadderSynthesizer(tier_factory=_cli_tier_factory(), scorer=scorer, threshold=threshold)
            if ladder_on
            else ClaudeCliSynthesizer(**model_kwarg)
        )

    # Promotion: reversible CCE promoter ONLY when explicitly requested; else no-op.
    if getattr(args, "promote", False):
        promoter: Promoter = CCEPromoter(args.promote_project_root, args.promote_candidate_root)
    else:
        promoter = NoopPromoter()

    return {
        "ranker": ranker,
        "synthesizer": synthesizer,
        "scorer": scorer,
        "promoter": promoter,
        "gap_finder": gap_finder,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m limen.converge",
        description="Converge N divergent shots at one idea into the better version.",
    )
    parser.add_argument("--idea", required=True, help="The idea the shots are attempts at.")
    parser.add_argument(
        "--shot",
        action="append",
        default=[],
        metavar="PATH_OR_TEXT",
        help="A divergent shot: a file path (contents read) or literal text. Repeatable.",
    )
    parser.add_argument("--threshold", type=float, default=0.7, help="Promotion gate (default 0.7).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Use dependency-free fallback adapters (no network, no mesh/CCE).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Use the REAL AnthropicSynthesizer (needs the 'anthropic' package + "
        "ANTHROPIC_API_KEY). Promotion stays OFF unless --promote is also given.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the synthesis model (default: AnthropicSynthesizer's). --live only.",
    )
    parser.add_argument(
        "--mesh",
        action="store_true",
        help="Rank/gaps via the mesh CLI instead of lexical fallbacks (needs mesh's .venv). --live only.",
    )
    parser.add_argument(
        "--mesh-registry",
        default=None,
        help="mesh registry path for structural dead-zone gaps (with --mesh).",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="IRREVERSIBLE-GATE: wire the reversible CCEPromoter so a passing distillate is "
        "actually promoted. Requires --promote-project-root and --promote-candidate-root. "
        "--live only.",
    )
    parser.add_argument("--promote-project-root", default=None, help="CCE project root (with --promote).")
    parser.add_argument("--promote-candidate-root", default=None, help="Candidate corpus dir (with --promote).")
    args = parser.parse_args(argv)

    if not args.shot:
        parser.error("provide at least one --shot")
    if not args.dry_run and not args.live:
        parser.error("choose a mode: --dry-run (offline) or --live (real synthesis)")
    if args.promote and not args.live:
        parser.error("--promote requires --live")
    if args.promote and not (args.promote_project_root and args.promote_candidate_root):
        parser.error("--promote requires --promote-project-root and --promote-candidate-root")

    shots = [_load_shot(spec, i) for i, spec in enumerate(args.shot, start=1)]

    kit = _build_live_kit(args) if args.live else _build_dry_run_kit()
    result = converge(args.idea, shots, threshold=args.threshold, **kit)

    print("=== better_version ===")
    print(result.better_version)
    print(f"\n=== score: {result.score:.3f}  promoted: {result.promoted} ===")
    print("\n=== cited_losers ===")
    for shot in result.cited_losers:
        print(f"- {shot.id} ({shot.source})")
    print("\n=== next_shots ===")
    for nxt in result.next_shots:
        print(f"- {nxt}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
