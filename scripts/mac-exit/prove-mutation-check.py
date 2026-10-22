#!/usr/bin/env python3
"""Prove the self-test of prove-remote-held.py can fail: break the tool on purpose and require a red self-test.

WHY: a passing self-test only matters if it goes red when the logic is wrong. Each mutant is a copy of the tool with
one deliberate defect (a proof that always succeeds, a guard removed, a listing error read as an empty listing, a
redaction disabled). A mutant is KILLED when `--self-test` exits non-zero; a SURVIVOR means the self-test cannot see that
defect; an INVALID mutant is one whose anchor text no longer occurs exactly once in its target (the tool changed, so the
mutant guards nothing) or whose result does not compile. Exit 0 only if the unmodified copy passes and every mutant is
valid and killed.

Mutants live in a scratch directory, by default a fresh one under the system temp dir (or the OUT_DIR you name). It is
removed when everything passed, kept (and its path printed) when anything failed or with --keep. Nothing is ever written
next to the tool.

  python3 -I prove-mutation-check.py [OUT_DIR] [--workers 3] [--only NAME ...] [--keep]
  python3 -I prove-mutation-check.py --check-anchors     # validate the anchors only, no self-test runs

Exit codes: 0 = baseline green and every mutant valid and killed (by the check that guards it); 1 = a survivor, an
invalid or mis-killed mutant, or a red baseline; 64 = usage error (an unknown --only name, a non-empty OUT_DIR); 70 =
internal error. The copies it runs carry PROVE_SELFTEST_MUTANT_COPY=1: they hold only the tool and its helper, so the
tool's own self-test skips, visibly, the sub-checks that need this script.
"""

from __future__ import annotations

import argparse
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NoReturn

EXIT_USAGE, EXIT_INTERNAL = 64, 70
# Set in the environment of every self-test this script runs: the tool's self-test then knows it is in a copy that holds
# only the tool and its helper, and says so instead of failing on the missing script.
COPY_ENV = "PROVE_SELFTEST_MUTANT_COPY"
HERE = Path(__file__).resolve().parent
TOOL = HERE / "prove-remote-held.py"
HELPER = HERE / "gh-merged-pr-proof.sh"

# (name, exact text in the target, replacement[, target]) -- target is "tool" (default) or "helper".
# The "# finding" tag says which review finding the mutant re-opens.
MUTANTS: list[tuple[str, ...]] = [
    # --- the original guards -------------------------------------------------------------------------------------
    ("ancestor-proves-everything", "    return {c for c in commits if c in listed}", "    return set()"),
    (
        "local-path-remote-counts",
        '            return "network"\n        return "local"\n',
        '            return "network"\n        return "network"\n',
    ),
    (
        "failed-listing-treated-as-fresh",
        "        if rc == 0:\n            try:\n                remote.fresh = ctx.fresh_ok[key]",
        "        if True:\n            try:\n                remote.fresh = ctx.fresh_ok[key]",
    ),
    ("dirty-ignored", "    if dirty_wts:", "    if False:"),
    ("stash-ignored", "    if res.stashes:", "    if False:"),
    (
        "helper-answer-not-matched-to-question",
        'if status in {"PROVEN", "ANCESTOR", "NONE"} and not asked:',
        "if False:",
    ),
    (
        "candidate-branches-not-passed",
        'ctx.default_branch.get(slug.lower(), "-"), *candidates]',
        'ctx.default_branch.get(slug.lower(), "-")]',
    ),
    ("compare-accepted-for-any-branch", "(branch in candidates or branch == default)", "True"),
    (
        "redaction-disabled",
        '    return SECRET_QS_RE.sub(r"\\1***", USERINFO_RE.sub(_userinfo, text))',
        "    return text",
    ),
    (  # repaired: the old anchor named an `res.verdict = "UNPROVEN"` line that no longer exists
        "vanished-path-reported-proven",
        "        res.reasons = [(code, group.error)]\n",
        '        res.reasons, res.verdict = [], "PROVEN-ALL"\n',
    ),
    ("detached-heads-ignored", "if wt.detached and wt.head and not wt.bare:", "if False:"),
    (
        "tags-ignored",
        'ref.startswith(("refs/remotes/", "refs/stash", *PER_WORKTREE_PREFIXES))',
        'ref.startswith(("refs/remotes/", "refs/stash", "refs/tags/", *PER_WORKTREE_PREFIXES))',
    ),
    ("bot-author-not-checked", "    return bool(BOT_AUTHOR_RE.search(author)) and (", "    return True and ("),
    ("superseded-blocks-verdict", "return not self.proven and self.status != SUPERSEDED", "return not self.proven"),
    (
        "branches-verdict-ignores-dirt-and-stash",
        'BRANCHES_PROVEN if not common and not branch_tip_reasons else "UNPROVEN"',
        'BRANCHES_PROVEN if not branch_tip_reasons else "UNPROVEN"',
    ),
    (
        "branches-verdict-ignores-unproven-branches",
        'BRANCHES_PROVEN if not common and not branch_tip_reasons else "UNPROVEN"',
        'BRANCHES_PROVEN if not common else "UNPROVEN"',
    ),
    (
        "orphan-worktree-reported-as-plain-error",
        'code = R_VANISHED if vanished else R_ORPHAN if group.key.startswith("NOMETA:") else R_ERROR',
        "code = R_VANISHED if vanished else R_ERROR",
    ),
    ("helper-error-read-as-not-merged", 'elif pr_state == "ERROR":', "elif False:"),
    (
        "only-one-remote-consulted",
        '    live = [r for r in remotes if r.kind == "network" and r.fresh is not None]\n    failed =',
        '    live = [r for r in remotes if r.kind == "network" and r.fresh is not None][-1:]\n    failed =',
    ),
    # --- the independent reviewer's eight survivors ----------------------------------------------------------------
    ("status-error-ignored", "    if status_errors:", "    if False:"),
    ("tips-listing-error-ignored", "        common.append((R_ERROR, tips_or_err))", "        pass"),
    ("bot-branch-name-not-checked", " or not BOT_BRANCH_RE.match(tip.name)", ""),
    ("replace-objects-honored", '        GIT_NO_REPLACE_OBJECTS="1",\n', ""),
    (
        "revlist-failure-proves-all",
        "    if rc != 0:\n        return None\n    listed",
        "    if rc != 0:\n        return set()\n    listed",
    ),
    (
        "helper-proven-rc-not-checked",
        'elif status == "PROVEN" and rc == 0 and len(fields) == 6:',
        'elif status == "PROVEN" and len(fields) == 6:',
    ),
    (
        "notes-original-replace-refs-ignored",
        'ref.startswith(("refs/remotes/", "refs/stash", *PER_WORKTREE_PREFIXES))',
        'ref.startswith(("refs/remotes/", "refs/stash", "refs/notes/", "refs/original/", "refs/replace/", *PER_WORKTREE_PREFIXES))',
    ),
    (
        "prunable-worktree-detached-tip-skipped",
        "if wt.detached and wt.head and not wt.bare:",
        "if wt.detached and wt.head and not wt.bare and not wt.missing:",
    ),
    # --- finding 1: commits only reflogs / tracking refs / refs/stash name ----------------------------------------
    (
        "sweep-skipped",
        "        common += sweep_beyond_tips(ctx, anchor, group.key, tips, res.remotes, stash_shas, res.gaps)",
        "        common += []",
    ),
    (
        "sweep-ignores-reflogs",
        '    walk = ["rev-list", "--reflog", "--remotes", "--stdin"]',
        '    walk = ["rev-list", "--remotes", "--stdin"]',
    ),
    (
        "sweep-ignores-tracking-refs",
        '    walk = ["rev-list", "--reflog", "--remotes", "--stdin"]',
        '    walk = ["rev-list", "--reflog", "--stdin"]',
    ),
    (
        "sweep-walk-failure-ignored",
        '    if rc != 0:\n        return [(R_ERROR, f"reflog / tracking-ref reachability failed',
        '    if False:\n        return [(R_ERROR, f"reflog / tracking-ref reachability failed',
    ),
    (
        "sweep-ancestry-failure-ignored",
        '    if rc != 0:\n        return [(R_ERROR, f"reflog / tracking-ref ancestry failed',
        '    if False:\n        return [(R_ERROR, f"reflog / tracking-ref ancestry failed',
    ),
    (
        "sweep-stash-commits-not-excluded",
        "    held = {t.commit for t in tips if t.commit} | set(stash_shas)",
        "    held = {t.commit for t in tips if t.commit}",
    ),
    (
        "sweep-fresh-remote-shas-not-excluded",
        "        held |= present\n",
        "        pass\n",
    ),
    (
        "sweep-helper-none-read-as-held",
        '                if state in {"PROVEN", "ANCESTOR"}:\n                    proven = True',
        '                if state in {"PROVEN", "ANCESTOR", "NONE"}:\n                    proven = True',
    ),
    (
        "sweep-lookup-cap-ignored",
        "        if index < MAX_SWEEP_LOOKUPS and ctx.helper is not None:",
        "        if ctx.helper is not None:",
    ),
    (
        "sweep-not-reduced-to-heads",
        "    inner = {p for line in parents.splitlines() for p in line.split()[1:] if p in rest}",
        "    inner: set[str] = set()",
    ),
    (
        "stash-ref-without-reflog-not-counted",
        "    return max(len(listed), 1), sorted(set(listed) | set(top)), errors",
        "    return len(listed), sorted(set(listed) | set(top)), errors",
    ),
    (
        "stash-ref-listing-error-ignored",
        """        return 0, [], [f"stash ref listing failed: {flat(err or f'rc={rc}', 90)}"]""",
        "        return 0, [], []",
    ),
    (
        "stash-reflog-listing-error-ignored",
        """        errors.append(f"stash reflog listing failed: {flat(err or f'rc={rc}', 90)}")""",
        "        pass",
    ),
    # --- finding 2: a checkout that holds .git is not deletable because its own HEAD is held -------------------
    (
        "head-held-not-forced-for-the-main-checkout",
        'if fact.held == "yes" and holds_common_dir(wt.path, res.common_dir) and res.verdict != "PROVEN-ALL":',
        "if False:",
    ),
    (
        "head-held-forced-for-linked-worktrees-too",
        '    return os.path.realpath(os.path.join(path, ".git")) == os.path.realpath(common_dir)',
        "    return True",
    ),
    # --- finding 3: tag objects, bot copies, submodules, grafts, shallow remotes ----------------------------------
    (
        "annotated-tag-held-by-its-commit",
        "            ref = remote.fresh.by_sha.get(tip.sha)\n",
        "            ref = remote.fresh.by_sha.get(tip.sha) or (remote.fresh.by_sha.get(tip.commit) if tip.commit else None)\n",
    ),
    (
        "annotated-tag-proven-as-ancestor",
        "    pending = [t for t in tips if not t.status and t.commit and not t.annotated]",
        "    pending = [t for t in tips if not t.status and t.commit]",
    ),
    (
        "annotated-tag-asked-of-github",
        '        if tip.commit and tip.kind != "other" and not tip.annotated and slug_remotes and ctx.helper is not None:',
        '        if tip.commit and tip.kind != "other" and slug_remotes and ctx.helper is not None:',
    ),
    (
        "bot-committer-not-checked",
        "        bool(BOT_AUTHOR_RE.search(committer)) or committer.strip() == GITHUB_COMMITTER",
        "        True",
    ),
    (
        "bot-copy-needs-only-one-bot-commit",
        "        if all(bot_commit(line) for line in lines):",
        "        if any(bot_commit(line) for line in lines):",
    ),
    (
        "submodules-not-analysed",
        '        ("submodule", R_SUBMODULE, module_gitdirs(common_dir)),',
        '        ("submodule", R_SUBMODULE, ([], "")),',
    ),
    (
        "alternates-lenders-not-analysed",
        '        ("alternates lender", R_ALTERNATES, alternate_gitdirs(common_dir)),',
        '        ("alternates lender", R_ALTERNATES, ([], "")),',
    ),
    ("nested-repository-verdict-ignored", '            if sub.verdict != "PROVEN-ALL":', "            if False:"),
    (
        "grafts-honoured",
        "        GIT_GRAFT_FILE=os.devnull,  # finding 3d: info/grafts would rewrite ancestry just like refs/replace\n",
        "",
    ),
    ("ancestor-proof-off-github", "        if not remote.slug:\n            continue\n", ""),
    # --- finding 4: offsite classification, cache identity, no answering remote, listing errors --------------------
    (
        "loopback-and-private-addresses-are-offsite",
        '    return "network" if ip.is_global else "local"',
        '    return "network"',
    ),
    (
        "localhost-and-lan-names-are-offsite",
        '    if host == "localhost" or host.endswith(LOCAL_HOST_SUFFIXES):',
        "    if False:",
    ),
    (
        "single-label-aliases-are-offsite",
        '    return "network" if "." in host else "unsupported"',
        '    return "network"',
    ),
    (
        "remote-helper-transport-is-network",
        "    if not url or TRANSPORT_HELPER_RE.match(url):",
        "    if not url:",
    ),
    (
        "listing-cache-key-drops-user",
        '    return f"{scheme.lower()}://{user}@{host}:{port_text}{path}"',
        '    return f"{scheme.lower()}://{host}:{port_text}{path}"',
    ),
    (
        "listing-cache-key-drops-port",
        '    return f"{scheme.lower()}://{user}@{host}:{port_text}{path}"',
        '    return f"{scheme.lower()}://{user}@{host}{path}"',
    ),
    (
        "listing-cache-key-folds-case-everywhere",
        '    if host == "github.com":\n        path = path.lower()',
        "    if True:\n        path = path.lower()",
    ),
    (
        "no-answering-remote-still-proves",
        "        if not answered:  # finding 4c: GitHub lookups alone never stand in for a fresh listing",
        "        if False:  # finding 4c: GitHub lookups alone never stand in for a fresh listing",
    ),
    (
        "worktree-listing-error-ignored",
        """        return [], f"worktree listing failed: {flat(err or f'rc={rc}', 90)}\"""",
        '        return [], ""',
    ),
    (
        "remote-listing-error-ignored",
        """        return [], f"remote listing failed: {flat(err or f'rc={rc}', 90)}\"""",
        '        return [], ""',
    ),
    ("lfs-store-ignored", "    if has_lfs_objects(common_dir):", "    if False:"),
    (
        "helper-404-reads-as-plain-absence",
        'emit NONE "$repo" "$sha" "commit-unknown-to-github-or-no-access" "$default_branch"',
        'emit NONE "$repo" "$sha" "commit-unknown-to-github" "$default_branch"',
        "helper",
    ),
    # --- finding 4g and 5 --------------------------------------------------------------------------------------------
    (
        "completion-row-not-written",
        """            self.fh.write("\\t".join([f"{END_MARK} rows={self.rows}"] + [END_MARK] * (len(self.cols) - 1)) + "\\n")""",
        "            pass",
    ),
    (
        "trusted-directory-cannot-speak-file-protocol",
        "    ALLOW_FILE_PROTOCOL = bool(trusted)",
        "    ALLOW_FILE_PROTOCOL = False",
    ),
    (
        "proven-all-keeps-scope-partial",
        '        res.scope = "nothing-to-preserve"',
        '        res.scope = "partial"',
    ),
    (
        "hidden-edits-never-compared",
        "        edited += [n for n, sha in zip(hashable, listed, strict=True) if sha != index_sha[n][1]]",
        "        edited += []",
    ),
    ("hidden-edits-do-not-block", "    if hidden_wts:", "    if False:"),
    # --- round 2, contract 1: join keys are lossless (INT-3). Each re-opens the base behaviour of one defect. ------------
    (
        "paths-flattened-and-truncated",
        "        paths=paths_cell([os.path.realpath(r.path) for r in res.rows]),",
        '        paths=flat(";".join(r.path for r in res.rows), 4000),',
    ),
    (
        "key-columns-collapsed-by-the-writer",
        "        return key_cell(str(value)) if col in self.lossless else cell(value)",
        "        return cell(value)",
    ),
    (
        "paths-not-realpathed",
        "        paths=paths_cell([os.path.realpath(r.path) for r in res.rows]),",
        "        paths=paths_cell([r.path for r in res.rows]),",
    ),
    (
        "unrepresentable-key-does-not-fail-the-repository",
        "        return refuse_unrepresentable(analyze_repo(ctx, group, depth))",
        "        return analyze_repo(ctx, group, depth)",
    ),
    (
        "list-separator-inside-a-path-kept",
        '    return ";".join(key_cell(p).replace(";", FFFD) for p in paths)',
        '    return ";".join(key_cell(p) for p in paths)',
    ),
    ("row-breaking-characters-kept-in-a-key", "    return KEY_UNSAFE_RE.sub(FFFD, value)", "    return value"),
    # --- round 2, contract 2: tips.tsv is keyed the way the predicate looks refs up (INT-5), and per-worktree refs (P3) ----
    (
        "tips-written-with-short-branch-names",
        "            ref=tip.ref,\n            kind=tip.kind,",
        "            ref=tip.name,\n            kind=tip.kind,",
    ),
    (
        "detached-tip-not-qualified-by-its-worktree",
        'Tip(f"HEAD@{os.path.realpath(wt.path)}", "detached", wt.head, wt.head)',
        'Tip(f"(detached HEAD) {wt.path}", "detached", wt.head, wt.head)',
    ),
    ("per-worktree-refs-not-collected", "    tips += per_worktree\n", "    pass\n"),
    (
        "per-worktree-refs-of-linked-worktrees-not-collected",
        "        sources.append((admin, os.path.realpath(os.path.dirname(target))))",
        "        pass",
    ),
    (
        "per-worktree-refs-of-the-anchor-listed-as-bare-names",
        'if worktree is None and ref.startswith(("refs/remotes/", "refs/stash", *PER_WORKTREE_PREFIXES)):',
        'if worktree is None and ref.startswith(("refs/remotes/", "refs/stash")):',
    ),
    (
        "per-worktree-status-does-not-reach-the-verdict",
        "        if tip.blocking and tip.status in {R_NETWORK, R_NOT_HELD, R_PER_WORKTREE}:",
        "        if tip.blocking and tip.status in {R_NETWORK, R_NOT_HELD}:",
    ),
    # --- round 2: one listing must not answer for another repository (P1), a mirror is not GitHub (P2) --------------------
    (
        "scp-home-relative-path-keyed-as-absolute",
        '        path = path if path.startswith("/") else "/~/" + path',
        '        path = "/" + path.lstrip("/")',
    ),
    (
        "github-slug-taken-from-the-spelling-insteadof-replaced",
        "github_slug(resolved)",
        "github_slug(resolved, raw)",
    ),
    # --- round 2: SHA-256 repositories, and a line nothing can parse is never skipped (P5) --------------------------------
    (
        "sha256-object-ids-rejected",
        'OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")',
        'OID_RE = re.compile(r"^[0-9a-f]{40}$")',
    ),
    (
        "ls-remote-unparseable-line-skipped",
        '            raise ValueError(f"unparseable ls-remote line: {flat(line, 60)}")',
        "            continue",
    ),
    (
        "ref-listing-unparseable-line-skipped",
        '            return f"unparseable ref listing line: {flat(line, 100)}"',
        "            continue",
    ),
    (
        "stash-ref-unparseable-ignored",
        '        errors.append(f"stash ref listing unparseable: {flat(out, 60)}")',
        "        pass",
    ),
    # --- round 2: the exit code says what the run proved, and an aborted run never looks finished (PS-9) -------------
    (
        "unproven-repositories-exit-zero",
        '    return EXIT_PROVEN if all(r.verdict == "PROVEN-ALL" and not r.gaps for r in results) else EXIT_NOT_PROVEN',
        "    return EXIT_PROVEN",
    ),
    (
        "aborted-run-files-get-a-completion-row",
        "            out.close(complete=False)",
        "            out.close()",
    ),
    (
        "internal-error-exits-zero",
        "        print(INTERNAL_ERROR_MESSAGE, file=sys.stderr)\n        return EXIT_INTERNAL\n",
        "        print(INTERNAL_ERROR_MESSAGE, file=sys.stderr)\n        return EXIT_PROVEN\n",
    ),
    ("limit-truncation-is-not-an-incomplete-run", "    if args.limit and total > args.limit:", "    if False:"),
    ("deadline-timeouts-are-not-an-incomplete-run", "    if timed_out:", "    if False:"),
    (
        "usage-error-creates-the-out-dir",
        "    out_dir = args.out_dir\n    problems = usage_problems(args)\n",
        "    out_dir = args.out_dir\n    out_dir.mkdir(parents=True, exist_ok=True)\n    problems = usage_problems(args)\n",
    ),
    ("usage-error-exits-two", "self.exit(EXIT_USAGE,", "self.exit(2,"),
    ("empty-sweep-is-a-vacuous-green", "        if not has_rows:", "        if False:"),
    # --- round 2: the documented gaps of a proof are machine codes, not prose (contract 4, PS-5, P10) ----------------
    ("trust-remote-under-leaves-no-gap", "    if any(r.trusted for r in res.remotes):", "    if False:"),
    (
        "nongithub-exact-proof-leaves-no-gap",
        "        if any(t.status == EXACT and t.via in by_name and not by_name[t.via].slug for t in tips):",
        "        if False:",
    ),
    ("nongithub-sweep-exclusion-leaves-no-gap", "        if not remote.slug and present - held:", "        if False:"),
    (
        "exact-proof-prefers-a-non-github-remote",
        "        for remote in sorted(live, key=lambda r: (not r.slug, r.name)):  # GitHub first: it holds the history too",
        "        for remote in sorted(live, key=lambda r: (bool(r.slug), r.name)):  # GitHub first: it holds the history too",
    ),
    (
        "bare-without-reflog-leaves-no-gap",
        "    if any(w.bare for w in res.worktrees) and not has_reflogs(group.key):",
        "    if False:",
    ),
    (
        "every-bare-repository-gets-the-reflog-gap",
        "    if any(w.bare for w in res.worktrees) and not has_reflogs(group.key):",
        "    if any(w.bare for w in res.worktrees):",
    ),
    (
        "nested-gaps-not-propagated",
        "            gaps |= sub.gaps  # a submodule's assumptions are the superproject's",
        "            pass",
    ),
    ("gaps-column-not-written", "        gaps=res.gaps_cell,", '        gaps="",'),
    (
        "trust-flag-leaves-no-line-in-the-summary",
        "    if ctx.trusted:\n        relying = ",
        "    if False:\n        relying = ",
    ),
    # --- round 2: a submodule's files are read in its checkout, a swept path's HEAD from git (P4, P8) -----------------
    (
        "hidden-edits-resolve-names-against-the-git-dir",
        '    top = top.rstrip("\\n")\n    rc, out, err = git(top, "ls-files", "-v", "-z")',
        '    top = path\n    rc, out, err = git(top, "ls-files", "-v", "-z")',
    ),
    ("nested-repository-anchored-at-the-git-dir", "else module_worktree(real)", "else real"),
    (
        "submodule-listing-keeps-the-git-dir-as-its-worktree",
        "        elif not wt.bare and looks_like_gitdir(wt.path):",
        "        elif False:",
    ),
    (
        "hidden-edits-are-not-part-of-a-rows-cleanliness",
        "            clean = fact.dirty == 0 and wt.hidden == 0",
        "            clean = fact.dirty == 0",
    ),
    (
        "unlisted-swept-path-is-always-unborn",
        "    wt.unborn = wt.branch is not None and wt.head is None",
        "    wt.unborn = True",
    ),
    (
        "unlisted-swept-path-reads-no-head",
        "    wt.head = sha.strip() if rc == 0 and OID_RE.match(sha.strip()) else None",
        "    wt.head = None",
    ),
    # --- round 2: large-file stores outside <git dir>/lfs/objects (P9) -------------------------------------------
    (
        "relocated-lfs-storage-ignored",
        '        tops.append(os.path.join(common_dir, storage, "objects"))',
        "        pass",
    ),
    (
        "relative-lfs-storage-resolved-against-the-cwd",
        '        tops.append(os.path.join(common_dir, storage, "objects"))',
        '        tops.append(os.path.join(os.path.abspath(storage), "objects"))',
    ),
    ("annex-content-ignored", "    if has_annex_objects(common_dir):", "    if False:"),
    # --- round 2: legacy and embedded IPv4 spellings of a local address are not offsite (P11) -------------------------
    ("legacy-ipv4-spellings-are-offsite", "        ip = legacy_ipv4(host)", "        ip = None"),
    ("wildcard-dns-for-a-local-address-is-offsite", "    embedded = embedded_ipv4(host)", "    embedded = None"),
    # --- round 2: the self-test never skips its mutation-check sub-checks silently, the helper has a usage (PS-14) -------
    (
        "mutation-check-absence-is-skipped",
        '    return "present" if (here / "prove-mutation-check.py").exists() else "missing"',
        '    return "present" if (here / "prove-mutation-check.py").exists() else "copy"',
    ),
    ("mutant-copy-marker-ignored", '    if environ.get(COPY_ENV) == "1":', "    if False:"),
    (
        "helper-help-flag-is-a-bad-argument",
        "  -h | --help)\n    usage\n",
        "  --no-such-flag)\n    usage\n",
        "helper",
    ),
    ("helper-bad-arguments-print-no-usage", "  usage >&2\n  emit ERROR", "  emit ERROR", "helper"),
    # --- round 2 (G1): a non-bare repository whose reflogs cannot enumerate abandoned commits ----------------------
    (
        "non-bare-without-reflogs-leaves-no-gap",
        "    if not any(w.bare for w in res.worktrees) and reflog_disabled(group.key):",
        "    if False:",
    ),
    (
        "every-non-bare-repository-gets-the-no-reflog-gap",
        "    if not any(w.bare for w in res.worktrees) and reflog_disabled(group.key):",
        "    if not any(w.bare for w in res.worktrees):",
    ),
    (
        "log-all-ref-updates-false-is-not-a-gap",
        '    if rc == 0 and out.strip().lower() in {"false", "no", "off", "0"}:',
        "    if False:",
    ),
    ("missing-reflog-files-are-not-a-gap-for-non-bare", "    return not has_reflogs(common_dir)", "    return False"),
    # --- round 2 (G2): exit 0 only for a PROVEN-ALL that carries no documented gap -------------------------------
    (
        "proven-all-with-gaps-exits-zero",
        '    return EXIT_PROVEN if all(r.verdict == "PROVEN-ALL" and not r.gaps for r in results) else EXIT_NOT_PROVEN',
        '    return EXIT_PROVEN if all(r.verdict == "PROVEN-ALL" for r in results) else EXIT_NOT_PROVEN',
    ),
    (
        "proven-all-with-gaps-exits-silently",
        '    if with_gaps := [r for r in results if r.verdict == "PROVEN-ALL" and r.gaps]:',
        "    if False:",
    ),
]

# mutant -> text that must occur in a failed self-test check when it is killed. A mutant killed only by a crash or by an
# unrelated check proves nothing about the defect it re-opens, so these are reported MISKILLED instead of KILLED.
KILLED_BY: dict[str, str] = {
    "paths-flattened-and-truncated": "INT-3",
    "key-columns-collapsed-by-the-writer": "INT-3",
    "paths-not-realpathed": "symlink",
    "unrepresentable-key-does-not-fail-the-repository": "UNPROVEN-UNREPRESENTABLE",
    "list-separator-inside-a-path-kept": "`;` in a checkout path",
    "row-breaking-characters-kept-in-a-key": "cell count differs",
    "tips-written-with-short-branch-names": "INT-5: every live ref",
    "detached-tip-not-qualified-by-its-worktree": "INT-5: a detached worktree is keyed",
    "per-worktree-refs-not-collected": "P3: a per-worktree ref of a LINKED",
    "per-worktree-refs-of-linked-worktrees-not-collected": "P3: a per-worktree ref of a LINKED",
    "per-worktree-refs-of-the-anchor-listed-as-bare-names": "P3: the anchor's own per-worktree refs",
    "per-worktree-status-does-not-reach-the-verdict": "P3: a per-worktree ref of a LINKED",
    "scp-home-relative-path-keyed-as-absolute": "P1 norm_key: scp",
    "github-slug-taken-from-the-spelling-insteadof-replaced": "P2: a github.com URL that insteadOf rewrites",
    "sha256-object-ids-rejected": "P5",
    "ls-remote-unparseable-line-skipped": "P5: an ls-remote line",
    "ref-listing-unparseable-line-skipped": "P5: a for-each-ref line",
    "stash-ref-unparseable-ignored": "P5: an unreadable refs/stash listing",
    "unproven-repositories-exit-zero": "exit code 1",
    "aborted-run-files-get-a-completion-row": "an exception is exit 70",
    "internal-error-exits-zero": "an exception is exit 70",
    "limit-truncation-is-not-an-incomplete-run": "--limit that drops entries",
    "deadline-timeouts-are-not-an-incomplete-run": "a deadline that leaves repositories unexamined",
    "usage-error-creates-the-out-dir": "a missing --tsv is exit 64",
    "usage-error-exits-two": "no arguments is a usage error",
    "empty-sweep-is-a-vacuous-green": "a sweep with no entries is exit 64",
    "trust-remote-under-leaves-no-gap": "contract 4 / PS-5: a remote counted as offsite",
    "nongithub-exact-proof-leaves-no-gap": "contract 4 / P10: a tip held by SHA",
    "nongithub-sweep-exclusion-leaves-no-gap": "contract 4 / P10: a commit excluded from the sweep",
    "exact-proof-prefers-a-non-github-remote": "contract 4 control: a non-GitHub backup",
    "bare-without-reflog-leaves-no-gap": "contract 4 / P10: a bare repository without reflogs",
    "every-bare-repository-gets-the-reflog-gap": "contract 4 / P10: a bare repository without reflogs",
    "nested-gaps-not-propagated": "a submodule's gap is the superproject's",
    "gaps-column-not-written": "contract 4 / P10: a tip held by SHA",
    "trust-flag-leaves-no-line-in-the-summary": "PS-5: summary.txt carries a loud TEST ONLY line",
    "hidden-edits-resolve-names-against-the-git-dir": "P4: the hidden-edit probe finds the edit",
    "nested-repository-anchored-at-the-git-dir": "P4: the nested analysis is anchored",
    "submodule-listing-keeps-the-git-dir-as-its-worktree": "P4: the nested analysis is anchored",
    "hidden-edits-are-not-part-of-a-rows-cleanliness": "P8: a linked worktree with a file edited",
    "unlisted-swept-path-is-always-unborn": "P8: probe_worktree",
    "unlisted-swept-path-reads-no-head": "P8: probe_worktree",
    "relocated-lfs-storage-ignored": "P9: git-lfs content in a store relocated",
    "relative-lfs-storage-resolved-against-the-cwd": "P9: git-lfs content in a store relocated",
    "annex-content-ignored": "P9: git-annex content",
    "legacy-ipv4-spellings-are-offsite": "4a classify_remote: IPv4 shorthand 127.1",
    "wildcard-dns-for-a-local-address-is-offsite": "4a classify_remote: wildcard DNS for loopback",
    "mutation-check-absence-is-skipped": "PS-14: a checkout without prove-mutation-check.py",
    "mutant-copy-marker-ignored": "PS-14: prove-mutation-check.py sits next to the tool",
    "helper-help-flag-is-a-bad-argument": "PS-14: the helper answers --help",
    "helper-bad-arguments-print-no-usage": "PS-14: no arguments",
    "proven-all-with-gaps-exits-zero": "PS-9: CLI with --trust-remote-under: exit code 1",
    "proven-all-with-gaps-exits-silently": "G2: CLI with --trust-remote-under: stderr names",
    "non-bare-without-reflogs-leaves-no-gap": "G1: a NON-bare repository whose reflogs",
    "every-non-bare-repository-gets-the-no-reflog-gap": "G1 control",
    "log-all-ref-updates-false-is-not-a-gap": "G1: a NON-bare repository whose reflogs",
    "missing-reflog-files-are-not-a-gap-for-non-bare": "G1: a NON-bare repository whose reflogs",
}


def self_test(path: Path) -> tuple[int, str, float, list[str]]:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-I", str(path), "--self-test"],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
        env={**os.environ, COPY_ENV: "1"},
    )
    seconds = time.monotonic() - started
    failed = [ln.strip().removeprefix("[FAIL] ") for ln in proc.stdout.splitlines() if "[FAIL]" in ln]
    if failed:
        note = failed[0][:110] + (f" (+{len(failed) - 1} more)" if len(failed) > 1 else "")
        return proc.returncode, note, seconds, failed
    last = (proc.stdout.strip().splitlines() or [""])[-1]
    crash = proc.stderr.strip().splitlines()[-1:] or [""]
    note = last if proc.returncode == 0 else f"crash, no failed check: {crash[0][:90]}"
    return proc.returncode, note, seconds, failed


def build(mutant: tuple[str, ...], sources: dict[str, str], out_dir: Path) -> tuple[Path | None, str]:
    """Write the mutant's directory (tool + helper, one of them mutated). (tool path, "") or (None, why invalid)."""
    name, old, new = mutant[0], mutant[1], mutant[2]
    target = mutant[3] if len(mutant) > 3 else "tool"
    count = sources[target].count(old)
    if count != 1:
        return None, f"INVALID: anchor occurs {count} times in the {target}"
    folder = out_dir / name
    folder.mkdir()
    tool = folder / TOOL.name
    helper = folder / HELPER.name
    tool.write_text(sources["tool"].replace(old, new) if target == "tool" else sources["tool"], encoding="utf-8")
    helper.write_text(
        sources["helper"].replace(old, new) if target == "helper" else sources["helper"], encoding="utf-8"
    )
    helper.chmod(0o755)
    if target == "tool":
        try:
            py_compile.compile(str(tool), cfile=str(folder / "check.pyc"), doraise=True)
        except py_compile.PyCompileError as exc:
            return None, f"INVALID: the mutant does not compile ({str(exc)[:80]})"
    return tool, ""


class UsageParser(argparse.ArgumentParser):
    """argparse with the family's exit code for a usage error (64), not argparse's 2."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main() -> int:
    parser = UsageParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=3, help="self-tests run at once (default 3; each runs git)")
    parser.add_argument("--only", nargs="+", metavar="NAME", help="run only these mutants (plus the unmodified copy)")
    parser.add_argument(
        "out_dir",
        metavar="OUT_DIR",
        nargs="?",
        type=Path,
        help="scratch directory for the mutant copies (must not exist or be empty); default: a fresh directory under "
        "the system temp dir",
    )
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory even when everything passed")
    parser.add_argument("--check-anchors", action="store_true", help="only validate that every anchor is unique")
    args = parser.parse_args()
    names = [m[0] for m in MUTANTS]
    if len(set(names)) != len(names):
        print("duplicate mutant names", file=sys.stderr)
        return EXIT_INTERNAL
    unknown = sorted(set(args.only or []) - set(names))
    if unknown:  # a typo must not read as 'zero mutants, all killed'
        print(f"unknown mutant name(s): {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    if args.out_dir is None:
        out_dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="mutants-")))  # realpath: macOS /var is a symlink
    else:
        out_dir = args.out_dir.resolve()
        if out_dir.exists() and any(out_dir.iterdir()):
            print(f"refusing to write into non-empty {out_dir}", file=sys.stderr)
            return EXIT_USAGE
        out_dir.mkdir(parents=True, exist_ok=True)
    rc = 1
    try:
        rc = sweep(args, out_dir)
        return rc
    finally:
        if args.keep or rc != 0:  # a failing run keeps its mutants so the survivor can be reproduced
            print(f"kept {out_dir}")
        else:
            shutil.rmtree(out_dir, ignore_errors=True)


def sweep(args: argparse.Namespace, out_dir: Path) -> int:
    sources = {"tool": TOOL.read_text(encoding="utf-8"), "helper": HELPER.read_text(encoding="utf-8")}
    chosen = [m for m in MUTANTS if not args.only or m[0] in args.only]
    built = {m[0]: build(m, sources, out_dir) for m in chosen}
    invalid = {name: why for name, (path, why) in built.items() if path is None}
    if args.check_anchors:
        for name, why in invalid.items():
            print(f"{name}: {why}")
        print(f"anchors: {len(chosen) - len(invalid)} valid, {len(invalid)} invalid")
        return 1 if invalid else 0
    baseline = out_dir / "unmodified"
    baseline.mkdir()
    (baseline / TOOL.name).write_text(sources["tool"], encoding="utf-8")
    shutil.copy(HELPER, baseline / HELPER.name)
    jobs = {"unmodified": baseline / TOOL.name} | {n: p for n, (p, _) in built.items() if p is not None}
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        outcomes = dict(zip(jobs, pool.map(self_test, jobs.values()), strict=True))
    rc, note, seconds, _failed = outcomes["unmodified"]
    ok = rc == 0 and not invalid
    print(f"{'unmodified copy':58s} {'PASSES' if rc == 0 else 'FAILS ':8s} exit {rc:<3d} {seconds:5.0f}s  {note}")
    print("-" * 140)
    killed = survived = 0
    for mutant in chosen:
        name = mutant[0]
        if name in invalid:
            print(f"{name:58s} INVALID  {invalid[name]}")
            continue
        rc, note, seconds, failed = outcomes[name]
        wanted = KILLED_BY.get(name)
        if rc != 0 and wanted and not any(wanted in label for label in failed):
            # killed, but not by the assertion that guards this defect (a crash or an unrelated failure): no proof
            survived += 1
            ok = False
            print(f"{name:58s} MISKILLED exit {rc:<3d} {seconds:5.0f}s  wanted {wanted!r}; got {note}")
        elif rc != 0:
            killed += 1
            print(f"{name:58s} KILLED   exit {rc:<3d} {seconds:5.0f}s  {note}")
        else:
            survived += 1
            ok = False
            print(f"{name:58s} SURVIVED exit {rc:<3d} {seconds:5.0f}s")
    print("-" * 140)
    print(
        f"mutants: {len(chosen)}; killed {killed}; survived {survived}; invalid {len(invalid)}; "
        f"baseline {'green' if outcomes['unmodified'][0] == 0 else 'RED'}; all killed and baseline green: {ok}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
