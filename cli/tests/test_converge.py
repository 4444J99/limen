"""Tests for the converge() organ.

These use FAKE in-memory adapters only — no network, no mesh, no CCE, no anthropic.
They assert the five contracted behaviours of converge():

  (a) the synthesizer's better_version is returned,
  (b) shots the synthesizer dropped appear in cited_losers,
  (c) next_shots come from the gap_finder,
  (d) promoter.promote is called when score >= threshold,
  (e) promoter.rollback is called when score < threshold.
"""

from __future__ import annotations

import argparse

import pytest

from limen.converge import (
    AnthropicSynthesizer,
    ClaudeCliSynthesizer,
    ConcatSynthesizer,
    ConvergeResult,
    DeterministicScorer,
    LexicalGapFinder,
    LexicalRanker,
    NoopPromoter,
    Shot,
    Synthesis,
    _build_live_kit,
    converge,
    main,
)


# ─── Fake adapters ───────────────────────────────────────────────────


class FakeRanker:
    """Ranks by reversing the input order so we can prove rank order is honoured."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Shot]]] = []

    def rank(self, idea: str, shots: list[Shot]) -> list[Shot]:
        self.calls.append((idea, shots))
        return list(reversed(shots))


class FakeSynthesizer:
    """Returns a fixed distillate, keeping only the ids in ``keep``."""

    def __init__(self, better: str, keep: list[str]) -> None:
        self.better = better
        self.keep = keep
        self.seen_ranked: list[Shot] | None = None

    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:
        self.seen_ranked = ranked
        kept = [s.id for s in ranked if s.id in self.keep]
        dropped = [s.id for s in ranked if s.id not in self.keep]
        return Synthesis(better_version=self.better, kept_ids=kept, dropped_ids=dropped)


class FakeScorer:
    """Returns a fixed score so we can drive the threshold branch deterministically."""

    def __init__(self, value: float) -> None:
        self.value = value
        self.args: tuple | None = None

    def score(self, idea: str, better_version: str, shots: list[Shot]) -> float:
        self.args = (idea, better_version, shots)
        return self.value


class RecordingPromoter:
    def __init__(self) -> None:
        self.promote_args: tuple[str, str] | None = None
        self.rollback_called = False

    def promote(self, idea: str, better_version: str) -> None:
        self.promote_args = (idea, better_version)

    def rollback(self) -> None:
        self.rollback_called = True


class FakeGapFinder:
    def __init__(self, gaps: list[str]) -> None:
        self._gaps = gaps
        self.called_with: tuple | None = None

    def gaps(self, idea: str, shots: list[Shot]) -> list[str]:
        self.called_with = (idea, shots)
        return list(self._gaps)


@pytest.fixture
def shots() -> list[Shot]:
    return [
        Shot(id="a", text="first draft", source="laneA"),
        Shot(id="b", text="second draft", source="laneB"),
        Shot(id="c", text="third draft", source="laneC"),
    ]


# ─── The five contracted behaviours ──────────────────────────────────


def test_better_version_chosen_and_returned(shots):
    synth = FakeSynthesizer(better="THE DISTILLATE", keep=["a"])
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=synth,
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=FakeGapFinder([]),
    )
    assert isinstance(result, ConvergeResult)
    assert result.better_version == "THE DISTILLATE"


def test_dropped_shots_appear_in_cited_losers(shots):
    # keep only "a"; "b" and "c" must show up as cited losers.
    synth = FakeSynthesizer(better="x", keep=["a"])
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=synth,
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=FakeGapFinder([]),
    )
    loser_ids = {s.id for s in result.cited_losers}
    assert loser_ids == {"b", "c"}
    assert "a" not in loser_ids
    # cited_losers carries full Shot provenance, not just ids.
    assert all(isinstance(s, Shot) for s in result.cited_losers)


def test_cited_losers_follow_rank_order(shots):
    # FakeRanker reverses -> [c, b, a]; keep "a" -> losers in rank order are [c, b].
    synth = FakeSynthesizer(better="x", keep=["a"])
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=synth,
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=FakeGapFinder([]),
    )
    assert [s.id for s in result.cited_losers] == ["c", "b"]


def test_next_shots_surface_from_gap_finder(shots):
    gaps = ["explore: edge-case", "explore: failure-mode"]
    gf = FakeGapFinder(gaps)
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="x", keep=["a"]),
        scorer=FakeScorer(0.9),
        promoter=RecordingPromoter(),
        gap_finder=gf,
    )
    assert result.next_shots == gaps
    assert gf.called_with is not None  # gap_finder was actually consulted


def test_promote_called_when_score_meets_threshold(shots):
    promoter = RecordingPromoter()
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="GOOD", keep=["a"]),
        scorer=FakeScorer(0.8),
        promoter=promoter,
        gap_finder=FakeGapFinder([]),
        threshold=0.7,
    )
    assert result.promoted is True
    assert result.score == 0.8
    assert promoter.promote_args == ("the idea", "GOOD")
    assert promoter.rollback_called is False


def test_promote_called_at_exact_threshold(shots):
    promoter = RecordingPromoter()
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="OK", keep=["a"]),
        scorer=FakeScorer(0.7),
        promoter=promoter,
        gap_finder=FakeGapFinder([]),
        threshold=0.7,
    )
    assert result.promoted is True
    assert promoter.promote_args == ("the idea", "OK")


def test_rollback_called_when_score_below_threshold(shots):
    promoter = RecordingPromoter()
    result = converge(
        "the idea",
        shots,
        ranker=FakeRanker(),
        synthesizer=FakeSynthesizer(better="WEAK", keep=["a"]),
        scorer=FakeScorer(0.4),
        promoter=promoter,
        gap_finder=FakeGapFinder([]),
        threshold=0.7,
    )
    assert result.promoted is False
    assert result.score == 0.4
    assert promoter.rollback_called is True
    assert promoter.promote_args is None  # promote NOT called


# ─── The dependency-free fallback adapters also satisfy the contract ─


def test_fallback_adapters_end_to_end():
    """The shipped fallback kit (used by --dry-run) runs converge() with no deps."""
    shots = [
        Shot(id="1", text="cats are great pets and very fluffy", source="x"),
        Shot(id="2", text="completely unrelated text about taxes", source="y"),
    ]
    promoter = NoopPromoter()
    result = converge(
        "cats are great pets",
        shots,
        ranker=LexicalRanker(),
        synthesizer=ConcatSynthesizer(),
        scorer=DeterministicScorer(),
        promoter=promoter,
        gap_finder=LexicalGapFinder(),
        threshold=0.7,
    )
    # The on-topic shot covers the whole idea -> high score -> promoted.
    assert result.promoted is True
    assert promoter.promoted is not None
    assert "cats" in result.better_version
    # The off-topic shot is a cited loser.
    assert any(s.id == "2" for s in result.cited_losers)


def test_fallback_rollback_on_empty_idea_coverage():
    """An off-topic-only shot set scores 0 -> rollback, nothing promoted."""
    shots = [Shot(id="1", text="something about quarterly tax filings", source="z")]
    promoter = NoopPromoter()
    result = converge(
        "kittens and puppies",
        shots,
        ranker=LexicalRanker(),
        synthesizer=ConcatSynthesizer(),
        scorer=DeterministicScorer(),
        promoter=promoter,
        gap_finder=LexicalGapFinder(),
        threshold=0.7,
    )
    assert result.promoted is False
    assert promoter.rolled_back is True
    # The uncovered idea tokens become next shots.
    assert any("kittens" in nxt or "puppies" in nxt for nxt in result.next_shots)


# ─── --live CLI wiring (hermetic: fake Anthropic client, no network) ──────


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [type("Block", (), {"type": "text", "text": text})()]


class FakeAnthropicClient:
    """Mimics anthropic.Anthropic().messages.create(...) -> message with .content."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeMessage(self._reply)


def _live_args(**overrides):
    """An argparse.Namespace shaped like main()'s --live args, with safe defaults."""
    base = dict(
        live=True,
        model=None,
        mesh=False,
        mesh_registry=None,
        promote=False,
        promote_project_root=None,
        promote_candidate_root=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_live_kit_wires_real_synthesizer_and_noop_promoter():
    """--live builds the REAL AnthropicSynthesizer; default promoter is the no-op."""
    client = FakeAnthropicClient(
        '{"better_version": "the distilled one", "kept_ids": ["a"], "dropped_ids": ["b"]}'
    )
    kit = _build_live_kit(_live_args(), anthropic_client=client)

    assert isinstance(kit["synthesizer"], AnthropicSynthesizer)
    assert isinstance(kit["promoter"], NoopPromoter)  # promotion gated OFF by default
    assert isinstance(kit["ranker"], LexicalRanker)  # mesh off -> lexical fallback

    shots = [Shot(id="a", text="first shot at the goal", source="laneA"),
             Shot(id="b", text="weaker second shot", source="laneB")]
    result = converge("the goal", shots, threshold=0.0, **kit)

    # The real synth path ran through the injected client and returned its distillate.
    assert result.better_version == "the distilled one"
    assert client.calls, "the synthesizer must have called the client"
    # 'b' was dropped by the synth -> cited as a loser; nothing was promoted irreversibly.
    assert any(s.id == "b" for s in result.cited_losers)


def test_live_kit_model_override_is_passed_through():
    """--model overrides the synthesis model without re-pinning a default."""
    client = FakeAnthropicClient('{"better_version": "x", "kept_ids": [], "dropped_ids": []}')
    kit = _build_live_kit(_live_args(model="claude-opus-4-8"), anthropic_client=client)
    assert kit["synthesizer"].model == "claude-opus-4-8"


# ─── Keyless claude-CLI synthesizer (the live-daemon path; no ANTHROPIC_API_KEY) ──


class _FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _shots():
    return [Shot(id="a", text="first draft", source="laneA"),
            Shot(id="b", text="weaker second", source="laneB")]


def test_claude_cli_synthesizer_parses_json(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _FakeProc('{"better_version": "the one", "kept_ids": ["a"], "dropped_ids": ["b"]}'),
    )
    syn = ClaudeCliSynthesizer()
    out = syn.synthesize("idea", _shots())
    assert out.better_version == "the one"
    assert out.kept_ids == ["a"] and out.dropped_ids == ["b"]


def test_claude_cli_synthesizer_strips_code_fence(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    fenced = '```json\n{"better_version": "fenced", "kept_ids": [], "dropped_ids": []}\n```'
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeProc(fenced))
    out = ClaudeCliSynthesizer().synthesize("idea", _shots())
    assert out.better_version == "fenced"


def test_claude_cli_synthesizer_non_json_keeps_top_shot(monkeypatch):
    """Non-JSON reply: the whole text is the distillate, top shot kept — never lose alchemy."""
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeProc("a plain prose distillate"))
    out = ClaudeCliSynthesizer().synthesize("idea", _shots())
    assert out.better_version == "a plain prose distillate"
    assert out.kept_ids == ["a"] and out.dropped_ids == ["b"]


def test_claude_cli_synthesizer_raises_loud_on_failure(monkeypatch):
    """A CLI failure must raise (so the kit cascade / per-face guard falls through) —
    never a silent empty write masquerading as convergence."""
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeProc("", returncode=1, stderr="boom"))
    with pytest.raises(RuntimeError):
        ClaudeCliSynthesizer().synthesize("idea", _shots())


def test_claude_cli_synthesizer_missing_binary_raises(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(FileNotFoundError):
        ClaudeCliSynthesizer()


def test_live_kit_uses_keyless_cli_when_no_api_key(monkeypatch):
    """The crux fix: with no ANTHROPIC_API_KEY (the daemon's launchd env), the live kit
    wires the KEYLESS claude CLI synthesizer instead of silently degrading to offline."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    kit = _build_live_kit(_live_args())
    assert isinstance(kit["synthesizer"], ClaudeCliSynthesizer)


def test_live_kit_prefers_api_when_key_present(monkeypatch):
    """When a key IS present, the raw-API rung wins over the CLI rung."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")

    class _FakeAPISynth:
        def __init__(self, **kw):
            self.model = kw.get("model")

    monkeypatch.setattr("limen.converge.AnthropicSynthesizer", _FakeAPISynth)
    kit = _build_live_kit(_live_args())
    assert isinstance(kit["synthesizer"], _FakeAPISynth)


def test_cli_requires_a_mode():
    """Neither --dry-run nor --live is an error (no silent default)."""
    with pytest.raises(SystemExit):
        main(["--idea", "x", "--shot", "y"])


def test_cli_promote_requires_live():
    """--promote without --live is rejected (irreversible gate guarded)."""
    with pytest.raises(SystemExit):
        main(["--idea", "x", "--shot", "y", "--dry-run", "--promote"])


def test_cli_promote_requires_candidate_paths():
    """--promote without the CCE paths is rejected before any side effect."""
    with pytest.raises(SystemExit):
        main(["--idea", "x", "--shot", "y", "--live", "--promote"])


def test_cli_dry_run_still_works():
    """The pre-existing offline path is unchanged."""
    assert main(["--idea", "cats", "--shot", "cats are great", "--dry-run"]) == 0
