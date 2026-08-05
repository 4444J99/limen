"""``python -m limen.observatory`` — the heartbeat's handle on the organ.

Every subcommand fails open and **always exits 0** so an organ bug never wedges the
beat (VIGILIA's contract). The human-facing mirror is the Click group
``limen observatory`` in ``cli/src/limen/cli.py``.

Subcommands:
  run          the whole loop (collect → analyze → reconcile → brief); dry by default
  collect      discovery only (built in the research step)
  analyze      scoring only (built in the research step)
  reconcile    the internal-legibility face (built in the reconcile step)
  brief        assemble/emit the daily brief (built in the brief step)
  doctor       the self-verifying predicate (``--offline`` to skip the live probe)
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys


def _run_stage(stage: str, apply: bool) -> int:
    """Run a single pipeline stage if its module is built; report cleanly if not."""
    module_by_stage = {
        "collect": ("limen.observatory.collect", "run"),
        "analyze": ("limen.observatory.mechanism", "run"),
        "reconcile": ("limen.observatory.reconcile", "run"),
        "brief": ("limen.observatory.brief", "run"),
    }
    module, entry = module_by_stage[stage]
    try:
        mod = importlib.import_module(module)
        fn = getattr(mod, entry)
    except Exception:
        print(f"observatory: {stage} not built yet (pending)")
        return 0
    try:
        result = fn(apply=apply)
        print(f"observatory: {stage} — {json.dumps(result, sort_keys=True)[:200]}")
    except Exception as exc:
        print(f"observatory: {stage} error — {str(exc)[:160]}")
    return 0


def _run(apply: bool) -> int:
    try:
        from . import executive

        status = executive.run_beat(apply=apply)
        print(executive.summary_line(status))
    except Exception as exc:
        print(f"observatory: run error — {str(exc)[:160]}")
    return 0


def _doctor(offline: bool) -> int:
    try:
        from . import doctor

        report = doctor.run(offline=offline)
        print(
            f"observatory: doctor ok={report['ok']} "
            + " ".join(f"{r['rung']}={'ok' if r.get('ok') else 'FAIL'}" for r in report["rungs"])
        )
    except Exception as exc:
        print(f"observatory: doctor error — {str(exc)[:160]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="limen.observatory")
    sub = parser.add_subparsers(dest="cmd")
    for name in ("run", "collect", "analyze", "reconcile", "brief"):
        p = sub.add_parser(name)
        p.add_argument("--apply", action="store_true", help="arm lever/task writes (default: dry)")
    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--offline", action="store_true", help="skip the live gh probe")

    try:
        args = parser.parse_args(argv)
    except SystemExit:  # a bad arg must never wedge the beat
        return 0

    if args.cmd == "doctor":
        return _doctor(args.offline)
    if args.cmd == "run":
        return _run(args.apply)
    if args.cmd in ("collect", "analyze", "reconcile", "brief"):
        return _run_stage(args.cmd, args.apply)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
