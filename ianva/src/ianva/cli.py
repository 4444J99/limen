"""`ianva` — the doorway's command line.

ianva up                 materialize settings + start the gateway backend
ianva down               stop the backend
ianva status             backend + endpoint + upstream summary
ianva doctor             verify every dependency, path, and the endpoint (no secrets shown)
ianva gen-configs        write the per-agent "point at ianva" entries to ./generated (review-only)
ianva install-configs    apply those entries to real agent configs  (prints plan; needs --apply)
ianva add-upstream ...    add/override an upstream in ~/.config/ianva/upstreams.json
ianva probe              reachability preflight of remote upstreams
ianva version
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, creds, paths
from .config import load_config
from .gen import Endpoint, build_entries, write_golden
from .mcphub import materialize_settings, start, stop
from .mcphub import status as backend_status
from .preflight import unreachable
from .upstreams import load_upstreams


def _endpoint(cfg) -> Endpoint:
    return Endpoint(**cfg.endpoint_kwargs())


def _ups(cfg):
    return load_upstreams(
        registry=Path(cfg.registry).expanduser() if cfg.registry else None,
        extra=Path(cfg.extra).expanduser() if cfg.extra else None,
    )


def cmd_up(args) -> int:
    cfg = load_config()
    ups = _ups(cfg)
    bearer = creds.bearer_token()
    sp = materialize_settings(ups, bearer=bearer)
    ok, msg = start(cfg, sp)
    print(msg)
    print(f"  upstreams: {len(ups)} ({sum(u.oauth for u in ups)} OAuth-held)")
    print(f"  endpoint:  {_endpoint(cfg).url()}")
    print(f"  dashboard: http://{cfg.host}:{cfg.port}/  (admin password printed once to {paths.LOG_DIR}/backend.log)")
    if bearer:
        print("  auth:      bearer ENFORCED — safe to expose via scripts/ianva-tunnel.sh")
    else:
        print("  auth:      UNAUTHENTICATED — loopback only. Do NOT tunnel; run `ianva bearer --new`,")
        print("             store IANVA_BEARER_TOKEN, and restart before exposing publicly.")
    if not ok:
        return 1
    print("  consent:   each OAuth upstream takes ONE human consent at the dashboard; ianva auto-refreshes it after.")
    print("  next:      `ianva gen-configs` then `ianva install-configs --apply` to point agents here.")
    return 0


def cmd_down(args) -> int:
    print(stop(load_config()))
    return 0


def cmd_status(args) -> int:
    cfg = load_config()
    st = backend_status(cfg)
    ups = _ups(cfg)
    print(json.dumps(st, indent=2))
    print(
        f"upstreams: {len(ups)} configured; {sum(u.oauth for u in ups)} OAuth-held; "
        f"{sum(u.is_remote() for u in ups)} remote"
    )
    return 0


def _which(name: str) -> str:
    return shutil.which(name) or "(absent)"


def cmd_doctor(args) -> int:
    cfg = load_config()
    ep = _endpoint(cfg)
    print("ianva doctor — dependencies & wiring (no secret values are ever printed)\n")

    print("runtimes:")
    for t in ("node", "npx", "uv", "uvx", "cloudflared", "docker"):
        print(f"  {t:<12} {_which(t)}")

    print("\nbackend:")
    argv = cfg.backend_cmd.split()[0]
    print(f"  backend       {cfg.backend}")
    print(f"  command       {cfg.backend_cmd}")
    print(f"  resolves      {_which(argv)}")

    print("\nmcp-proxy (stdio bridge for non-HTTP agents):")
    try:
        r = subprocess.run([cfg.proxy_bin, *cfg.proxy_args, "--help"], capture_output=True, text=True, timeout=60)
        print(f"  `{cfg.proxy_bin} {' '.join(cfg.proxy_args)} --help` exit={r.returncode}")
    except Exception as e:  # noqa: BLE001
        print(f"  could not run mcp-proxy: {e}")

    print("\npaths:")
    print(f"  IANVA_HOME    {paths.IANVA_HOME}  ({'ok' if paths.IANVA_HOME.exists() else 'will be created'})")
    print(
        f"  registry      {cfg.registry or paths.DEFAULT_REGISTRY}  "
        f"({'found' if (Path(cfg.registry).expanduser() if cfg.registry else paths.DEFAULT_REGISTRY).exists() else 'missing'})"
    )
    print(f"  limen.env     {paths.LIMEN_ENV}  ({'found' if paths.LIMEN_ENV.exists() else 'missing'})")

    print("\nsecrets present (names only):")
    for k in ("LIMEN_CLAUDE_AUTH_TOKEN", "LIMEN_CLAUDE_API_KEY", "IANVA_BEARER_TOKEN"):
        print(f"  {'✓' if creds.have(k) else '✗'} {k}")

    ups = _ups(cfg)
    print(f"\nupstreams: {len(ups)} configured")
    down = unreachable(ups)
    if down:
        print(f"  unreachable now (skipped this beat): {', '.join(down)}")

    st = backend_status(cfg)
    print(f"\nendpoint {ep.url()} — backend running={st['running']} reachable={st['endpoint_reachable']}")
    print(
        f"  auth: {'bearer enforced (exposable)' if creds.bearer_token() else 'UNAUTHENTICATED — loopback only, do not tunnel'}"
    )
    return 0


def cmd_gen_configs(args) -> int:
    cfg = load_config()
    entries = build_entries(_endpoint(cfg))
    outdir = write_golden(entries)
    print(f"wrote {len(entries)} agent entries to {outdir}\n")
    for e in entries:
        print(f"  {e.label:<22} {e.transport:<6} {e.path}")
    print(f"\nReview {outdir}/INSTALL.md, then `ianva install-configs --apply` to write them in.")
    return 0


def cmd_install_configs(args) -> int:
    here = Path(__file__).resolve().parents[2]
    installer = here / "scripts" / "install_agent_configs.py"
    if not installer.exists():
        print(f"installer not found: {installer}", file=sys.stderr)
        return 1
    # The installer is dry-run by default and backs up every file before writing; we pass
    # --apply straight through. Writing into global agent configs is a deliberate, gated step.
    cmd = [sys.executable, str(installer)]
    if args.apply:
        cmd.append("--apply")
    return subprocess.call(cmd)


def cmd_add_upstream(args) -> int:
    paths.ensure_dirs()
    f = paths.UPSTREAMS_JSON
    data = json.loads(f.read_text()) if f.exists() else {}
    entry: dict = {"enabled": True}
    if args.url:
        entry["url"] = args.url
        entry["type"] = args.transport or "streamable-http"
    if args.command:
        entry["command"] = args.command
        entry["args"] = args.arg or []
    if args.oauth:
        entry["oauth"] = True
    data[args.name] = entry
    f.write_text(json.dumps(data, indent=2) + "\n")
    print(f"added upstream {args.name!r} to {f}")
    return 0


def cmd_probe(args) -> int:
    cfg = load_config()
    ups = _ups(cfg)
    down = unreachable(ups)
    print(f"{len(ups)} upstreams; {len(down)} unreachable")
    for n in down:
        print(f"  DOWN {n}")
    return 0


def cmd_bearer(args) -> int:
    if args.new:
        tok = creds.new_bearer()
        print("New gateway bearer (store it, then restart ianva before exposing the endpoint):\n")
        print(f"  {tok}\n")
        print(
            f"  bash ~/Workspace/limen/scripts/set-credential.sh {creds.BEARER_ENV}"
            "   # paste the value above at the silent prompt"
        )
        return 0
    print(f"{creds.BEARER_ENV}: {'SET — endpoint can be exposed' if creds.bearer_token() else 'unset — loopback only'}")
    return 0


def cmd_version(args) -> int:
    print(f"ianva {__version__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ianva", description="the fleet's single MCP doorway")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("up").set_defaults(fn=cmd_up)
    sub.add_parser("down").set_defaults(fn=cmd_down)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("gen-configs").set_defaults(fn=cmd_gen_configs)
    sub.add_parser("probe").set_defaults(fn=cmd_probe)
    sub.add_parser("version").set_defaults(fn=cmd_version)

    pb = sub.add_parser("bearer")
    pb.add_argument("--new", action="store_true", help="generate a fresh bearer to store before exposing")
    pb.set_defaults(fn=cmd_bearer)

    pi = sub.add_parser("install-configs")
    pi.add_argument("--apply", action="store_true", help="actually write into global agent configs")
    pi.set_defaults(fn=cmd_install_configs)

    pa = sub.add_parser("add-upstream")
    pa.add_argument("name")
    pa.add_argument("--url")
    pa.add_argument("--transport", choices=["streamable-http", "sse"], default=None)
    pa.add_argument("--command")
    pa.add_argument("--arg", action="append")
    pa.add_argument("--oauth", action="store_true")
    pa.set_defaults(fn=cmd_add_upstream)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
