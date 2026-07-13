"""The unified daily brief — one report, both faces, one experiment.

This is where OBSERVATORY's two faces converge. The selector scores every gap on one
scale — external mechanism gaps carry a computed ``priority``; internal legibility gaps
(claim drift, severed pipe) get a priority from the same formula shape (a definite truth
violation is high-strength, cheap, fully controllable, so it naturally ranks high early) —
and picks the single highest-priority gap as the day's one reversible experiment. The
brief carries 3 mechanisms + 3 confounders + 1 hero + 1 experiment + 1 measurement
contract, and hands the experiment to :mod:`limen.observatory.lever` as a human-gated
proposal (dry by default).
"""

from __future__ import annotations

import json

from . import config, interpret, ledger, lever

# internal-legibility gap priorities (formula-shaped: strength≈1, controllability≈0.9, sim=1,
# ev≈0.8, cost small → a known truth-violation outranks a hypothesised external mechanism early).
_INTERNAL_PRIORITY = {"severed_pipe": 3.6, "claim_drift": 2.4}
_ADVISORY_FACTOR = 0.3


def _internal_gap_priority(gap: dict) -> float:
    kind = gap.get("kind")
    base = _INTERNAL_PRIORITY.get(kind, 1.0) if isinstance(kind, str) else 1.0
    return round(base * (_ADVISORY_FACTOR if gap.get("advisory") else 1.0), 4)


def _external_gaps() -> list[dict]:
    latest = config_latest("gap-latest.json")
    gaps = (latest or {}).get("gaps", []) if isinstance(latest, dict) else []
    out = []
    for g in gaps:
        out.append({**g, "face": "external", "priority": float(g.get("priority") or 0.0)})
    return out


def _internal_gaps() -> list[dict]:
    latest = config_latest("reconcile-latest.json")
    gaps = (latest or {}).get("gaps", []) if isinstance(latest, dict) else []
    out = []
    for g in gaps:
        out.append({**g, "face": "internal", "priority": _internal_gap_priority(g)})
    return out


def config_latest(name: str):
    """Read a regenerated derived doc from logs/observatory/ (None when absent)."""
    path = config.data_dir() / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _top_mechanisms(n: int = 3) -> list[dict]:
    claims = ledger.read_jsonl("mechanisms.jsonl")
    claims.sort(key=lambda c: (-float(c.get("priority") or 0.0), str(c.get("mechanism"))))
    out: list[dict] = []
    seen: set[str] = set()
    for c in claims:  # dedupe by mechanism — keep the highest-priority instance of each
        mech = str(c.get("mechanism"))
        if mech in seen:
            continue
        seen.add(mech)
        row = {"mechanism": c.get("mechanism"), "priority": c.get("priority"), "winner": c.get("winner")}
        if c.get("field_prevalence") is not None:
            row["field_prevalence"] = c.get("field_prevalence")
        out.append(row)
        if len(out) >= n:
            break
    return out


def _top_confounders(n: int = 3) -> list[dict]:
    seen = set()
    out = []
    for coh in ledger.read_jsonl("cohorts.jsonl"):
        for conf in coh.get("confounders") or []:
            key = conf.get("kind")
            if key and key not in seen:
                seen.add(key)
                out.append(conf)
    return out[:n]


def _experiment_from_gap(gap: dict, hero: str | None) -> dict:
    kind = gap.get("kind")
    # A gap row that names its own estate repo targets THAT repo; older/internal rows fall back
    # to the portfolio hero.
    target_repo = gap.get("repo") or hero
    if gap.get("face") == "external":
        # External gaps carry no VVLTVS kind — their one class is a mechanism transfer.
        kind = kind or "mechanism_transfer"
        mech = gap.get("mechanism")
        change = f"Add '{mech}' to {target_repo or 'the hero repo'}'s first screen (one reversible surface edit)."
        measure_hint = f"{gap.get('target_component', 'activation')} proxy over the window vs baseline"
        target = gap.get("target_component", "activation")
    elif kind == "severed_pipe":
        change = f"Revive the severed '{gap.get('register')}' conduit ({gap.get('detail', '')})."
        measure_hint = "the frozen face auto-unfreezes and matches its source"
        target = "trust"
    else:  # claim_drift
        change = f"Reconcile face '{gap.get('face_name') or gap.get('face')}' to its canonical source."
        measure_hint = "the surface value equals the canonical source (zero drift)"
        target = "trust"

    measurement = {
        "metric_vector": [target, "reach"],
        "baseline_source": "github-estate-ledger signals + repo traffic (manual)",
        "observation_window_days": int(config.get("OBSERVATORY_TRENDING_WINDOW_DAYS", 14, cast=int)),
        "success_predicate": f"the {target} proxy rises vs the baseline, holding star growth constant",
        "failure_criterion": "no movement or a regression at the evaluation date",
        "reversal_path": "git revert the change (additive/reversible by construction)",
        "confounder_controls": ["exclude days with an external launch event"],
    }
    return {
        "id": "L-OBS-EXP",
        "task_id": "OBS-EXP",
        "hero": target_repo,
        "repo": target_repo,
        "kind": kind,
        "change": change,
        "reversible": True,
        "revert": "git revert",
        "measure_hint": measure_hint,
        "measurement_contract": measurement,
    }


def select_experiment(gaps: list[dict], hero: str | None) -> dict | None:
    """The single highest-priority gap across both faces becomes the day's experiment."""
    if not gaps:
        return None
    top = max(gaps, key=lambda g: float(g.get("priority") or 0.0))
    return _experiment_from_gap(top, hero)


def build_brief(date: str | None = None) -> dict:
    ext = _external_gaps()
    inte = _internal_gaps()
    all_gaps = ext + inte
    latest_gap = config_latest("gap-latest.json") or {}
    hero = latest_gap.get("hero")
    experiment = select_experiment(all_gaps, hero)
    brief = {
        "schema": "limen.observatory.brief.v1",
        "date": date or lever._today(),
        "hero": hero,
        "mechanisms": _top_mechanisms(3),
        "confounders": _top_confounders(3),
        "internal_gaps": len(inte),
        "external_gaps": len(ext),
        "experiment": experiment,
        "measurement_contract": experiment.get("measurement_contract") if experiment else None,
    }
    # Portfolio + field views — additive keys, absent when the engine ran offline/pre-field,
    # so the brief stays byte-identical for the ships-dark determinism proof.
    by_repo = latest_gap.get("gaps_by_repo")
    if isinstance(by_repo, dict) and by_repo:
        portfolio = []
        for repo, rgaps in by_repo.items():
            top = (rgaps or [{}])[0]
            portfolio.append(
                {
                    "repo": repo,
                    "top_mechanism": top.get("mechanism"),
                    "priority": top.get("priority"),
                    "gap_count": len(rgaps or []),
                }
            )
        portfolio.sort(key=lambda r: (-(r.get("priority") or 0.0), r["repo"]))
        brief["portfolio"] = portfolio
    field = latest_gap.get("field")
    if isinstance(field, dict) and field.get("studied"):
        brief["field"] = field
    return brief


def render_markdown(brief: dict) -> str:
    lines = [
        "# OBSERVATORY — daily brief",
        "",
        f"**Hero:** {brief.get('hero') or '(none — no gap today)'}",
        f"**Gaps:** {brief.get('external_gaps', 0)} external · {brief.get('internal_gaps', 0)} internal",
    ]
    field = brief.get("field") or {}
    if field.get("studied"):
        lines.append(
            f"**Field:** {field.get('studied', 0)} trending repos studied"
            f" (of {field.get('total', 0)} found) · {field.get('facing', 0)} face our repos"
        )
    lines += [
        "",
        "## Three success mechanisms",
    ]
    for m in brief.get("mechanisms") or []:
        lines.append(f"- `{m['mechanism']}` (priority {m['priority']}, from {m['winner']})")
    if not brief.get("mechanisms"):
        lines.append("- (none observed yet)")
    lines += ["", "## Three confounders"]
    for c in brief.get("confounders") or []:
        lines.append(f"- {c.get('kind')}: {c.get('evidence', '')}")
    if not brief.get("confounders"):
        lines.append("- (none flagged)")
    if brief.get("portfolio"):
        lines += ["", "## Portfolio (per-repo top gap)"]
        for row in brief["portfolio"][:10]:
            lines.append(
                f"- `{row['repo']}` — {row.get('top_mechanism')}"
                f" (priority {row.get('priority')}, {row.get('gap_count')} gaps)"
            )
    exp = brief.get("experiment")
    lines += ["", "## One reversible experiment"]
    if exp:
        lines.append(f"- **{exp['change']}**")
        lines.append(f"  - revert: {exp['revert']}; measure: {exp['measure_hint']}")
    else:
        lines.append("- (no experiment — every surface is coherent and no transferable gap found)")
    lines.append("")
    return "\n".join(lines)


def run(*, apply: bool = False) -> dict:
    """The executive brief stage: assemble both faces → one brief + one proposed experiment."""
    brief = build_brief()
    # P2-LLM — attach an evidence-constrained interpretation ONLY when OBSERVATORY_LLM is armed and
    # the synthesis model returned text. Off (default) → no key, brief stays byte-deterministic.
    enrichment = interpret.interpret(brief, apply=apply)
    if enrichment.get("interpretation"):
        brief["interpretation"] = enrichment["interpretation"]
        brief["interpretation_model"] = enrichment.get("model")
    ledger.write_latest("brief-latest.json", brief)
    ledger.write_text("brief-latest.md", render_markdown(brief))
    ledger.snapshot_line("briefs.jsonl", brief)
    proposal = lever.propose(brief, apply=apply)
    return {
        "hero": brief.get("hero"),
        "mechanisms": len(brief.get("mechanisms") or []),
        "has_experiment": bool(brief.get("experiment")),
        "proposed": proposal.get("proposed", False),
        "armed": proposal.get("armed", False),
    }
