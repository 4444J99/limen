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
    LADDER_TIERS,
    AnthropicSynthesizer,
    ClaudeCliSynthesizer,
    ConcatSynthesizer,
    ConvergeResult,
    DeterministicScorer,
    LadderSynthesizer,
    LexicalGapFinder,
    LexicalRanker,
    NoopPromoter,
    Shot,
    Synthesis,
    _build_live_kit,
    converge,
    main,
    resolve_tier_model,
)


@pytest.fixture(autouse=True)
def _mock_api_model_resolution(monkeypatch):
    """Prevent ALL tests from shelling out to the claude CLI for model resolution."""
    monkeypatch.setattr(
        "limen.converge._resolve_api_model",
        lambda tier: f"claude-{tier}-4-6",
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
    client = FakeAnthropicClient('{"better_version": "the distilled one", "kept_ids": ["a"], "dropped_ids": ["b"]}')
    kit = _build_live_kit(_live_args(), anthropic_client=client)

    # The ladder (default on) wraps the REAL AnthropicSynthesizer mechanism via the
    # injected client — its eagerly-built cheapest rung is a true AnthropicSynthesizer.
    assert isinstance(kit["synthesizer"], LadderSynthesizer)
    assert isinstance(kit["synthesizer"]._built["haiku"], AnthropicSynthesizer)
    assert isinstance(kit["promoter"], NoopPromoter)  # promotion gated OFF by default
    assert isinstance(kit["ranker"], LexicalRanker)  # mesh off -> lexical fallback

    shots = [
        Shot(id="a", text="first shot at the goal", source="laneA"),
        Shot(id="b", text="weaker second shot", source="laneB"),
    ]
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
    return [Shot(id="a", text="first draft", source="laneA"), Shot(id="b", text="weaker second", source="laneB")]


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
    # The ladder (default on) rides the KEYLESS CLI rung; its cheapest rung is a real
    # ClaudeCliSynthesizer pinned to the bare 'haiku' CLI alias.
    assert isinstance(kit["synthesizer"], LadderSynthesizer)
    haiku_rung = kit["synthesizer"]._built["haiku"]
    assert isinstance(haiku_rung, ClaudeCliSynthesizer)
    assert haiku_rung.model == "haiku"


def test_live_kit_prefers_api_when_key_present(monkeypatch):
    """When a key IS present, the raw-API rung wins over the CLI rung."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")

    class _FakeAPISynth:
        def __init__(self, **kw):
            self.model = kw.get("model")

    monkeypatch.setattr("limen.converge.AnthropicSynthesizer", _FakeAPISynth)
    kit = _build_live_kit(_live_args())
    # Ladder default on → a LadderSynthesizer whose eager rung is the (faked) API mechanism.
    assert isinstance(kit["synthesizer"], LadderSynthesizer)
    assert isinstance(kit["synthesizer"]._built["haiku"], _FakeAPISynth)


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


# ─── Earned-tier ladder (haiku-first-with-cheap-verify) ──────────────────


class _StubTierSynth:
    """One mechanism rung: records how many times it synthesized; returns a fixed draft."""

    def __init__(self, tier: str, better: str) -> None:
        self.tier = tier
        self.better = better
        self.calls = 0

    def synthesize(self, idea: str, ranked: list[Shot]) -> Synthesis:
        self.calls += 1
        return Synthesis(
            better_version=self.better,
            kept_ids=[ranked[0].id] if ranked else [],
            dropped_ids=[s.id for s in ranked[1:]],
        )


class _ScriptedScorer:
    """Returns a score per better_version string — drives pass/fail per rung deterministically."""

    def __init__(self, table: dict[str, float]) -> None:
        self.table = table

    def score(self, idea: str, better_version: str, shots: list[Shot]) -> float:
        return self.table.get(better_version, 0.0)


def _make_factory(mapping: dict[str, str], builds: list[str] | None = None):
    """A tier_factory building a _StubTierSynth per tier. The ladder memoizes, so `builds`
    records exactly which tiers were ever constructed (eager haiku + each escalation)."""

    def build(tier: str) -> _StubTierSynth:
        if builds is not None:
            builds.append(tier)
        return _StubTierSynth(tier, mapping[tier])

    return build


def test_ladder_accepts_haiku_on_pass_no_escalation():
    """Cheap check passes at haiku → accept; sonnet/opus never built or run (no double-spend)."""
    builds: list[str] = []
    ladder = LadderSynthesizer(
        tier_factory=_make_factory({"haiku": "H", "sonnet": "S", "opus": "O"}, builds),
        scorer=_ScriptedScorer({"H": 0.9}),
        threshold=0.7,
    )
    out = ladder.synthesize("idea", _shots())
    assert out.better_version == "H"
    assert builds == ["haiku"]  # only the eager cheapest rung was ever constructed
    assert ladder._built["haiku"].calls == 1
    assert "sonnet" not in ladder._built and "opus" not in ladder._built


def test_ladder_escalates_to_sonnet_on_failed_check():
    """Haiku fails the cheap check → escalate one rung to sonnet, which passes. Opus untouched."""
    builds: list[str] = []
    ladder = LadderSynthesizer(
        tier_factory=_make_factory({"haiku": "H", "sonnet": "S", "opus": "O"}, builds),
        scorer=_ScriptedScorer({"H": 0.3, "S": 0.9}),
        threshold=0.7,
    )
    out = ladder.synthesize("idea", _shots())
    assert out.better_version == "S"
    assert builds == ["haiku", "sonnet"]
    assert ladder._built["haiku"].calls == 1 and ladder._built["sonnet"].calls == 1
    assert "opus" not in ladder._built


def test_ladder_climbs_to_opus_only_when_lower_rungs_fail():
    """Opus is reached only after BOTH haiku and sonnet fail the cheap check."""
    builds: list[str] = []
    ladder = LadderSynthesizer(
        tier_factory=_make_factory({"haiku": "H", "sonnet": "S", "opus": "O"}, builds),
        scorer=_ScriptedScorer({"H": 0.1, "S": 0.2, "O": 0.95}),
        threshold=0.7,
    )
    out = ladder.synthesize("idea", _shots())
    assert out.better_version == "O"
    assert builds == ["haiku", "sonnet", "opus"]


def test_ladder_fail_open_returns_best_so_far():
    """No rung clears the gate → return the BEST-scoring draft (fail-open), never raise.
    Then converge()'s own gate rejects it and the promoter rolls back — nothing destroyed."""
    ladder = LadderSynthesizer(
        tier_factory=_make_factory({"haiku": "H", "sonnet": "S", "opus": "O"}),
        scorer=_ScriptedScorer({"H": 0.1, "S": 0.4, "O": 0.2}),
        threshold=0.7,
    )
    assert ladder.synthesize("idea", _shots()).better_version == "S"  # 0.4 is the best
    promoter = NoopPromoter()
    result = converge(
        "idea",
        _shots(),
        threshold=0.7,
        ranker=LexicalRanker(),
        synthesizer=ladder,
        scorer=_ScriptedScorer({"S": 0.0}),  # converge's gate rejects the best-so-far
        promoter=promoter,
        gap_finder=LexicalGapFinder(),
    )
    assert result.promoted is False
    assert promoter.rolled_back is True


def test_ladder_fail_open_empty_synthesis_when_all_rungs_raise():
    """Every rung's synthesize raises → empty Synthesis (no exception up the stack), so
    converge() scores it low and rolls back. Never a corrupting write."""

    class _Boom:
        def synthesize(self, idea, ranked):
            raise RuntimeError("rung down")

    ladder = LadderSynthesizer(tier_factory=lambda tier: _Boom(), scorer=_ScriptedScorer({}), threshold=0.7)
    out = ladder.synthesize("idea", _shots())
    assert out.better_version == ""
    assert out.dropped_ids == ["a", "b"]  # all shots cited, nothing kept


def test_ladder_memoizes_tiers_across_calls():
    """A tier is built once and reused — no re-build on a second synthesize."""
    builds: list[str] = []
    ladder = LadderSynthesizer(
        tier_factory=_make_factory({"haiku": "H", "sonnet": "S", "opus": "O"}, builds),
        scorer=_ScriptedScorer({"H": 0.3, "S": 0.9}),
        threshold=0.7,
    )
    ladder.synthesize("idea", _shots())
    ladder.synthesize("idea", _shots())
    assert builds == ["haiku", "sonnet"]  # haiku eager, sonnet on first escalation; never rebuilt


def test_ladder_over_cli_climbs_aliases_in_order(monkeypatch):
    """The keyless production path: the ladder rides ClaudeCliSynthesizer and passes the bare
    CLI tier aliases haiku→sonnet→opus (derive-never-pin) as it escalates."""
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    used_models: list[str] = []

    def fake_run(argv, **kw):
        used_models.append(argv[argv.index("--model") + 1])
        return _FakeProc('{"better_version": "weak", "kept_ids": [], "dropped_ids": []}')

    monkeypatch.setattr("subprocess.run", fake_run)
    from limen.converge import _cli_tier_factory

    ladder = LadderSynthesizer(tier_factory=_cli_tier_factory(), scorer=_ScriptedScorer({"weak": 0.1}), threshold=0.7)
    ladder.synthesize("idea", _shots())
    assert used_models == ["haiku", "sonnet", "opus"]


def test_resolve_tier_model_env_override_and_cli_alias(monkeypatch):
    """Derive-never-pin: env pin wins; else CLI path returns the bare alias, API path the
    derived model from the claude CLI."""
    monkeypatch.delenv("LIMEN_CONVERGE_MODEL_SONNET", raising=False)
    monkeypatch.delenv("LIMEN_CONVERGE_MODEL_HAIKU", raising=False)
    assert resolve_tier_model("sonnet", cli=False) == "claude-sonnet-4-6"
    assert resolve_tier_model("sonnet", cli=True) == "sonnet"  # CLI resolves the alias itself
    assert set(LADDER_TIERS) == {"haiku", "sonnet", "opus"}
    monkeypatch.setenv("LIMEN_CONVERGE_MODEL_SONNET", "my-pin")
    assert resolve_tier_model("sonnet", cli=False) == "my-pin"
    assert resolve_tier_model("sonnet", cli=True) == "my-pin"  # explicit pin wins even on cli
    monkeypatch.setenv("LIMEN_CONVERGE_MODEL_HAIKU", "h-pin")
    assert resolve_tier_model("haiku", cli=True) == "h-pin"


def test_live_kit_ladder_off_uses_single_tier(monkeypatch):
    """LIMEN_CONVERGE_LADDER=0 reverts to the old single-tier synthesizer (instant rollback)."""
    monkeypatch.setenv("LIMEN_CONVERGE_LADDER", "0")
    client = FakeAnthropicClient('{"better_version": "x", "kept_ids": [], "dropped_ids": []}')
    kit = _build_live_kit(_live_args(), anthropic_client=client)
    assert isinstance(kit["synthesizer"], AnthropicSynthesizer)
    assert not isinstance(kit["synthesizer"], LadderSynthesizer)


def test_anthropic_synthesizer_default_model_derives_to_sonnet(monkeypatch):
    """The lone hardcoded fallback is gone: the default derives to the sonnet tier (env-overridable)."""
    monkeypatch.delenv("LIMEN_CONVERGE_MODEL_SONNET", raising=False)
    client = FakeAnthropicClient('{"better_version": "x", "kept_ids": [], "dropped_ids": []}')
    assert AnthropicSynthesizer(client=client).model == "claude-sonnet-4-6"
    monkeypatch.setenv("LIMEN_CONVERGE_MODEL_SONNET", "pinned")
    assert AnthropicSynthesizer(client=client).model == "pinned"


def test_ladder_eager_rung_propagates_missing_mechanism(monkeypatch):
    """The eager cheapest-rung build is the LOAD-BEARING cascade fallback: a missing mechanism
    (no claude CLI) must raise at CONSTRUCTION so the kit's api→cli→offline fallback fires. A
    regression that swallowed this would silently break the offline fallback at runtime."""
    from limen.converge import _cli_tier_factory

    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(FileNotFoundError):
        LadderSynthesizer(tier_factory=_cli_tier_factory(), scorer=DeterministicScorer(), threshold=0.7)


def test_live_kit_no_key_no_cli_raises_so_caller_falls_to_offline(monkeypatch):
    """_build_live_kit with no API key AND no claude CLI raises at build (same as the old
    single-tier path) — corpus-converge's outer try/except then degrades to the offline kit."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(FileNotFoundError):
        _build_live_kit(_live_args())
