#!/usr/bin/env python3
"""pr-lifecycle-autotype.py — the continuous typing rung for newly-arrived mechanical PRs.

The GITVS estate drain typed 283 lifecycle-untyped PRs to zero and the discharge predicate
(gitvs.py pr-debt --check) rebounded 0→2 within the hour, because arrivals — overwhelmingly
dependabot — had no continuous typing organ. The one-shot drain organ (the estate manifest)
is deliberately the wrong tool here: its exact-head preflight aborts a whole batch on one
drifted head, and dependabot rebases constantly. This rung is the trickle organ:

  * enumerate the untyped MECHANICAL residual with one cheap `gh search prs` per configured
    bot author (negated `-label:lifecycle:*` qualifiers — the query returns only the
    residual, normally empty), plus one authorless search to COUNT human-authored untyped
    arrivals, which are surfaced and never auto-typed (the census owns them);
  * re-check each candidate at effect time (`gh pr view`): closed, already labeled, archived,
    or not actually bot-authored → per-item skip with a named reason — NEVER a batch abort;
  * armed, apply the same fail-closed disposition the drain used (lifecycle:blocked); the
    delivery upgrade stays the separate human lever L-DEPENDABOT-DELIVERY-ARM.

SCOPE IS THE PREDICATE'S SCOPE. The owner set is DERIVED from the same estate authority
gitvs.py uses (see owners() below), never from a second narrower literal — a rung that reads
2 of the 10 governed owners would deliver a fraction of its contract while printing a
confident cohort=0, and the predicate it defends would keep rebounding red forever.

ABSENCE IS NEVER RENDERED AS HEALTH. Every read here can fail, and a failed read produces the
same empty list a genuinely drained estate does. So the search returns (rows, ok); a failed
visit is receipted as `read-failed`, reported as `cohort=UNKNOWN`, and exits non-zero so the
sensor's advisory escalation actually fires (an advisory non-zero prints the escalation and
still leaves the beat green). This matters most for the ARMING lever, whose review step reads
the receipt ledger: an empty ledger must never be mistakable for "nothing needed typing".

Posture (the owner-route-drain shape):
  * dry-run by default; --apply or LIMEN_PR_AUTOTYPE_APPLY=1 arms mutations
    (lever L-PR-AUTOTYPE-ARM).
  * observation-only under logs/AUTONOMY_PAUSED regardless of arming.
  * bounded: --limit caps EFFECTS per run (default 20), --scan-max caps how much is examined.
  * every verdict appends one receipt row to logs/pr-lifecycle-autotype.jsonl, applied or
    not; receipts go there and nowhere else.
"""

# NB (the owner-route-drain lesson, verbatim class): the tracked PR-debt scoreboard under
# docs/ is deliberately not named in this file — check-ledger-custody's B-check reads raw
# substrings, docstrings included. Nothing here reads or writes that document.

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
RECEIPTS = ROOT / "logs" / "pr-lifecycle-autotype.jsonl"
PAUSE_MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"
AUTHORS = [a.strip() for a in os.environ.get("LIMEN_PR_AUTOTYPE_AUTHORS", "app/dependabot").split(",") if a.strip()]
DISPOSITION = "lifecycle:blocked"

BASE_SCRIPT = Path(__file__).resolve().parent / "pr-lifecycle-manifest.py"
ESTATE_SCRIPT = Path(__file__).resolve().parent / "pr-lifecycle-estate-manifest.py"
GITVS_SCRIPT = Path(__file__).resolve().parent / "gitvs.py"

# Last-resort scope if the estate authority cannot be read at all. Deliberately NOT a config
# knob: a second declared owner list is exactly the divergence owners() exists to prevent.
FALLBACK_OWNERS = ("organvm", "4444J99")


def _load_sibling(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if spec is None:
        raise RuntimeError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


BASE = _load_sibling("pr_lifecycle_manifest_base", BASE_SCRIPT)
ESTATE = _load_sibling("pr_lifecycle_estate_manifest", ESTATE_SCRIPT)
GITVS = _load_sibling("pr_lifecycle_autotype_gitvs", GITVS_SCRIPT)
LIFECYCLE_LABELS = BASE.LIFECYCLE_LABELS


def owners() -> list[str]:
    """The SAME owner set the predicate this rung defends actually measures.

    gitvs.py pr-debt --check scopes itself on owners(load_estate()) — the orgs derived from
    institutio/github/estate.yaml class globs plus shelf assignments. Sibling drains carry a
    hardcoded two-owner literal; copying it here would leave the majority of the arrival
    stream unread while this rung reported a healthy cohort=0, and the predicate would rebound
    red on every arrival it never saw. Deriving keeps ONE authority and ONE declared override
    (LIMEN_GITVS_OWNERS, which is in the parameter panel) instead of a second undeclared one.
    """
    try:
        derived = [str(o).strip() for o in GITVS.owners(GITVS.load_estate()) if str(o).strip()]
    except Exception as exc:  # estate unreadable — say so; do not silently narrow the scope
        print(
            f"  pr-lifecycle-autotype: estate owner derivation FAILED ({type(exc).__name__}) — "
            f"falling back to {','.join(FALLBACK_OWNERS)}; this scope is NARROWER than the predicate's"
        )
        return list(FALLBACK_OWNERS)
    return derived or list(FALLBACK_OWNERS)


class _GhFailure:
    """A synthetic non-zero result.

    gh() converts every transport error into one of these so a hung, missing, or killed gh
    becomes a NAMED per-item skip that flows through the existing returncode checks — never an
    exception escaping into the caller, which would batch-abort the run this organ's contract
    says can never batch-abort.
    """

    def __init__(self, stderr: str) -> None:
        self.returncode = 124
        self.stdout = ""
        self.stderr = stderr


def gh(args, timeout=60):
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.SubprocessError as exc:
        return _GhFailure(f"gh transport: {type(exc).__name__}: {str(exc)[:160]}")
    except OSError as exc:
        return _GhFailure(f"gh unavailable: {str(exc)[:160]}")


def _query_terms() -> list[str]:
    """Positional search terms for the residual query.

    `archived:false` is load-bearing, not an optimisation. An archived repo is read-only AND
    the census already types its PRs from a non-label source, so those rows can never leave a
    label-absence search: without this qualifier they sit in the cohort permanently and, since
    the cohort is sorted, occupy the SAME leading slots every visit — a permanent residual that
    would eat the effect budget real arrivals need. Measured live at introduction: 6 estate
    rows, 5 of the 7 in the mechanical cohort.
    """
    return ["archived:false", *(f"-label:{label}" for label in sorted(LIFECYCLE_LABELS))]


def _search_untyped(owner_list, gh_fn, max_total: int, author: str | None) -> tuple[list[tuple[str, int]], bool]:
    """One `gh search prs` for open PRs carrying NO lifecycle label.

    Returns (rows, ok). The `ok` half is the point: a read FAILURE and a genuinely empty
    residual both produce [], and collapsing the two is the exact defect that already bit this
    file once (see the "--" comment below). Callers must never treat [] alone as "nothing to do".
    """
    cmd = ["search", "prs", "--state", "open", "--limit", str(max_total)]
    if author:
        cmd.extend(["--author", author])
    cmd.extend([*sum([["--owner", o] for o in owner_list], []), "--json", "number,repository,labels"])
    # The "--" separator is load-bearing: without it gh parses each "-label:…" negation as an
    # unknown FLAG and errors, which the fail-open turns into a silent empty cohort.
    cmd.extend(["--", *_query_terms()])
    r = gh_fn(cmd)
    if getattr(r, "returncode", 1) != 0:
        return [], False
    try:
        rows = json.loads(r.stdout or "[]")
    except (TypeError, ValueError):
        return [], False
    if not isinstance(rows, list):
        return [], False
    if len(rows) >= max_total:
        # Silent truncation would understate both the cohort and the human count.
        print(
            f"  pr-lifecycle-autotype: search hit the {max_total}-row scan cap "
            f"(author={author or 'any'}) — the real residual is larger than this visit can see"
        )
    out = []
    for row in rows:
        try:
            repo = row["repository"]["nameWithOwner"]
            num = int(row["number"])
        except (KeyError, TypeError, ValueError):
            continue
        if BASE.lifecycle_labels(row):
            continue  # search index lagged a labeling that already happened
        out.append((repo, num))
    return sorted(set(out)), True


def enumerate_untyped(authors, owner_list, gh_fn, max_total: int = 300) -> tuple[list[tuple[str, int]], bool]:
    cohort: set[tuple[str, int]] = set()
    ok = True
    for author in authors:
        rows, author_ok = _search_untyped(owner_list, gh_fn, max_total, author)
        ok = ok and author_ok
        cohort.update(rows)
    return sorted(cohort), ok


def human_unlabeled_count(mechanical, owner_list, gh_fn, max_total: int = 300) -> tuple[int, bool]:
    everyone, ok = _search_untyped(owner_list, gh_fn, max_total, None)
    return len(set(everyone) - set(mechanical)), ok


def _bot_logins() -> set[str]:
    """Both forms per author: gh search takes `app/dependabot`, pr view reports `dependabot`."""
    logins = set()
    for author in AUTHORS:
        logins.add(author)
        logins.add(author.removeprefix("app/"))
    return logins


def _current(repo: str, num: int, gh_fn) -> dict | None:
    r = gh_fn(["pr", "view", str(num), "-R", repo, "--json", "state,labels,author"], 40)
    if getattr(r, "returncode", 1) != 0:
        return None
    try:
        return json.loads(r.stdout)
    except (TypeError, ValueError):
        return None


def _receipt(row: dict) -> None:
    try:
        RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
        with open(RECEIPTS, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:
        # A silently-unwritten receipt is worse than a noisy one: the arming lever's review step
        # reads this ledger, so an empty file would read as "nothing needed typing".
        print(f"  pr-lifecycle-autotype: RECEIPT WRITE FAILED ({exc}) — the ledger is INCOMPLETE")


def _repo_archived(repo: str, cache: dict[str, bool]) -> bool:
    """Effect-time rail behind the query's `archived:false`.

    Deliberately redundant with the search qualifier: the guarantee that this organ never
    retries a doomed write must not rest on one read's behaviour. Fail-open to False — an
    unreadable repo state falls through to the per-item gates below.
    """
    if repo not in cache:
        try:
            cache[repo] = bool(ESTATE._repo_is_archived(repo))
        except Exception:
            cache[repo] = False
    return cache[repo]


def _classify(repo: str, num: int, archived: dict[str, bool], gh_fn) -> tuple[str, str, str]:
    """One (verdict, reason, author) per candidate — the per-item drift gate."""
    if _repo_archived(repo, archived):
        return "skip", "repo-archived-immutable (census owns it)", ""
    facts = _current(repo, num, gh_fn)
    if facts is None:
        return "skip", "gh-view-failed", ""
    author = str((facts.get("author") or {}).get("login") or "")
    if str(facts.get("state") or "") != "OPEN":
        return "skip", "closed-since-search", author
    if BASE.lifecycle_labels(facts):
        return "skip", "labeled-since-search", author
    if author not in _bot_logins():
        # The hard human-safety rail, enforced at effect time: only the configured
        # mechanical authors are ever auto-typed, whatever the search returned.
        return "skip", "not-mechanical", author
    return "type", f"untyped mechanical arrival -> {DISPOSITION}", author


def _apply_label(repo: str, num: int, ensured: dict[str, bool], gh_fn) -> str:
    if repo not in ensured:
        try:
            ESTATE._ensure_label(repo, DISPOSITION)
            ensured[repo] = True
        except Exception as exc:
            # Deliberately broad: _ensure_label reaches gh through BASE._run_gh, so it can raise
            # ManifestError, JSONDecodeError (a ValueError), or a subprocess timeout. Any of them
            # must be one repository's problem, never the whole run's.
            ensured[repo] = False
            return f"label-ensure-failed: {type(exc).__name__}: {str(exc)[:100]}"
    if not ensured[repo]:
        return "label-ensure-failed: cached"
    r = gh_fn(["pr", "edit", str(num), "-R", repo, "--add-label", DISPOSITION], 40)
    return "typed" if getattr(r, "returncode", 1) == 0 else f"edit-failed: {(r.stderr or '').strip()[:120]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_PR_AUTOTYPE_LIMIT", "20")))
    parser.add_argument("--scan-max", type=int, default=300)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="force dry-run even when the env valve is armed")
    args = parser.parse_args()

    armed = args.apply or os.environ.get("LIMEN_PR_AUTOTYPE_APPLY", "0") == "1"
    if args.dry_run:
        armed = False
    paused = PAUSE_MARKER.exists()
    if paused and armed:
        print("  pr-lifecycle-autotype: AUTONOMY_PAUSED present — observation-only this run")
        armed = False
    mode = "APPLY" if armed else ("PAUSED" if paused else "DRY-RUN")

    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    owner_list = owners()
    cohort, cohort_ok = enumerate_untyped(AUTHORS, owner_list, gh, max_total=args.scan_max)
    human, human_ok = human_unlabeled_count(cohort, owner_list, gh, max_total=args.scan_max)

    if not cohort_ok:
        # The whole point of the ok flag: absence must never render as health. Receipt the
        # failed visit so the ledger records that we looked, and exit non-zero so the sensor's
        # advisory escalation fires (advisory non-zero prints the escalation, beat stays green).
        _receipt(
            {
                "ts": stamp,
                "repo": "",
                "pr": 0,
                "author": "",
                "verdict": "read-failed",
                "reason": f"arrival search failed across owners={','.join(owner_list)}",
                "applied": False,
                "outcome": "read-failed",
                "paused": paused,
            }
        )
        print(
            f"  pr-lifecycle-autotype: {mode} cohort=UNKNOWN — the arrival search FAILED "
            "(gh unreachable/unauthenticated/rate-limited); nothing was read and nothing typed"
        )
        return 1

    if not human_ok:
        print("  pr-lifecycle-autotype: human-residual count UNKNOWN this visit — its search failed")
    elif human:
        print(
            f"  pr-lifecycle-autotype: {human} open PR(s) without lifecycle labels from other "
            "authors — never auto-typed here (label absence is not census-untyped: the census "
            "also types by non-label sources)"
        )

    ensured: dict[str, bool] = {}
    archived: dict[str, bool] = {}
    typed = 0
    skipped = 0
    examined = 0
    truncated = False
    for repo, num in cohort:
        # --limit bounds EFFECTS, not iterations — which is what the parameter panel declares it
        # to be. Slicing the cohort before classification would let candidates that can never be
        # typed consume the budget a real arrival needs, and because the cohort is sorted they
        # would consume the SAME slots every visit.
        if typed >= args.limit or examined >= args.scan_max:
            truncated = True
            break
        examined += 1
        verdict, reason, author = _classify(repo, num, archived, gh)
        outcome = "dry-run"
        if verdict == "type" and armed:
            outcome = _apply_label(repo, num, ensured, gh)
        if verdict == "type" and outcome in ("typed", "dry-run"):
            typed += 1
        else:
            skipped += 1
        _receipt(
            {
                "ts": stamp,
                "repo": repo,
                "pr": num,
                "author": author,
                "verdict": verdict,
                "reason": reason,
                "applied": armed,
                "outcome": outcome,
                "paused": paused,
            }
        )
        print(f"  pr-lifecycle-autotype: {repo}#{num} -> {verdict} ({reason[:90]}) [{outcome}]")

    tail = f" residual={len(cohort) - examined}" if truncated else ""
    print(
        f"  pr-lifecycle-autotype: {mode} owners={len(owner_list)} cohort={len(cohort)} "
        f"examined={examined} typed={typed} skipped={skipped} "
        f"human_unlabeled={human if human_ok else 'UNKNOWN'}{tail}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
