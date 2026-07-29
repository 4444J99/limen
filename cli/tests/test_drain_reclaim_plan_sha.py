"""The beat's worktree reclaim must actually be able to APPLY.

`reclaim-worktrees.py` refuses `--apply` without `--expected-plan-sha` — unconditionally
(`:1260-1262`). `scripts/drain.sh` passed `--apply` alone and piped the result to `| tail -4 || true`,
so on every beat the organ ran, printed `[APPLY-BLOCKED]: expected-plan-sha-required`, and the
`|| true` discarded it.

The SPRAWL-RECLAIM organ was therefore a NO-OP for as long as that guard has existed. Measured
2026-07-29: 64 worktrees accumulated, 7 of them provably dead. A silent skip reads as "nothing to
reclaim" — the exact masked-failure mode this estate has a standing rule against.

These are source-level assertions on purpose. Running the real thing takes ~6 minutes per scan and
mutates the host's worktrees; what needs pinning is the CONTRACT between the two scripts, and that is
statically visible.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRAIN = ROOT / "scripts" / "drain.sh"
RECLAIM = ROOT / "scripts" / "reclaim-worktrees.py"


def test_reclaim_still_refuses_apply_without_a_plan_sha():
    """The guard this fix exists to satisfy. If it is ever relaxed, the two-phase dance in drain.sh
    becomes unnecessary complexity and should be simplified — so pin the reason."""
    src = RECLAIM.read_text()
    assert "expected-plan-sha-required" in src
    assert re.search(r"if not EXPECTED_PLAN_SHA:\s*\n\s*failed\.append", src), (
        "reclaim-worktrees.py no longer refuses --apply without a plan sha; re-evaluate drain.sh"
    )


def test_drain_never_applies_without_deriving_a_plan_sha():
    """The defect itself: `--apply` unaccompanied by `--expected-plan-sha` can only ever be blocked."""
    src = DRAIN.read_text()
    for line in src.splitlines():
        if "reclaim-worktrees.py" in line and "--apply" in line:
            assert "--expected-plan-sha" in line, (
                f"drain.sh applies reclaim without a plan sha — it will be blocked every beat:\n  {line.strip()}"
            )


def test_drain_derives_the_sha_from_a_check_run():
    src = DRAIN.read_text()
    assert "--check --json" in src, "drain.sh must probe for a plan before applying it"
    assert "plan_sha256" in src, "drain.sh must read the plan sha out of the probe"


def test_a_blocked_reclaim_is_loud_not_swallowed():
    """`| tail -4 || true` is what turned a permanent block into silence. The apply path must
    surface a nonzero result, because "blocked every beat forever" and "raced once" are
    indistinguishable when the output is discarded."""
    src = DRAIN.read_text()
    apply_block = src[src.index("reclaim_one()") : src.index("reclaim_one generated")]
    assert "PIPESTATUS" in apply_block, "the apply path does not capture the reclaim exit status"
    assert "APPLY did not complete" in apply_block, "a failed apply is not reported"
    assert not re.search(r"--expected-plan-sha[^\n]*\|\| true", apply_block), (
        "the apply path still swallows failure with `|| true`"
    )
