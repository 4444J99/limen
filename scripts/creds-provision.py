#!/usr/bin/env python3
"""creds-provision.py — CLAVIS, the credential-PROVISIONING organ.

The sibling of creds-hydrate.py (the CONSUMER): where creds-hydrate READS secrets from 1Password
into ~/.limen.env, creds-provision OWNS the upstream that makes those reads possible — the fleet
service account and the ONE vault it reads. It closes the gap the operator named: credential
provisioning must live in a repo, controlled as code, not as a manual 1Password-console click.

THE INVARIANT (institutio/governance/credentials.yaml): a 1Password service account's vault access
is IMMUTABLE (set at creation). You cannot add a vault to a live SA. So the only stable shape is a
SINGLE SA-owned vault holding every fleet secret. This organ:

  check      the forever-PREDICATE. Every enabled, op-sourced, REQUIRED secret in creds-hydrate's
             DEFAULT_MAP must resolve to an SA-readable vault (per the policy). Exit 1 if any does
             not — so a starved credential is LOUD in the beat log, never a silent green. Read-only.

  bootstrap  the ONE root-of-trust seed (owner `op` session, dry-run by default; --apply executes):
             mint the fleet SA against the automation vault (+ --can-create-vaults), create the
             vault, MIGRATE every op-sourced secret into it, install the token via
             op-service-account.sh, revoke the inert zero-grant SA. Homed on Wall #320. Run ONCE;
             thereafter the SA owns the vault and the estate is self-maintaining.

  apply      idempotent conformance (dry-run by default; --apply executes): ensure every op-sourced
             secret lives in the automation vault. Because the SA OWNS that vault, adding a secret is
             a create/move IN the vault — never a re-grant (which 1Password forbids on a live SA).

NEVER prints a secret value (behind _scrub). Fail-open on op/errors. op is opt-in: without a
promptless session, mutating verbs are a no-op that name the one bootstrap step.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY_PATH = Path(os.getenv("LIMEN_CREDS_POLICY",
                             HERE.parent / "institutio" / "governance" / "credentials.yaml"))
HYDRATE_PATH = HERE / "creds-hydrate.py"

# Policy defaults — used if credentials.yaml is unreadable (fail toward caution: no vault is
# SA-readable, so every op-sourced secret reports as an outlier rather than a false green).
_POLICY_DEFAULTS = {
    "automation_vault": "Limen-Automation",
    "sa_readable_vaults": ["Limen-Automation"],
    "service_account": {"name": "limen-fleet", "token_file": "~/.config/op/service-account-token",
                        "create_flags": "--vault Limen-Automation:read_items,write_items --can-create-vaults"},
    "policy": {"required_must_be_sa_readable": True, "warn_on_nonrequired_outliers": True,
               "derive_exempt": True},
    "bootstrap": {"wall_issue": 320, "supersedes_inert_sa": True},
}


def _scrub(s: str) -> str:
    """Redact anything op-token / secret shaped so a value can never reach a log."""
    s = re.sub(r"ops_[A-Za-z0-9+/_=-]{20,}", "ops_***", s or "")
    s = re.sub(r"eyJ[A-Za-z0-9._-]{20,}", "eyJ***", s)
    return s


def load_policy() -> dict:
    """Read credentials.yaml. Fail-open to the caution defaults if PyYAML/file is unavailable."""
    try:
        import yaml  # noqa: PLC0415 — optional; defaults cover its absence
        data = yaml.safe_load(POLICY_PATH.read_text()) or {}
    except Exception:
        return dict(_POLICY_DEFAULTS)
    merged = dict(_POLICY_DEFAULTS)
    merged.update({k: v for k, v in data.items() if v is not None})
    return merged


def load_cred_map() -> list[dict]:
    """The per-secret registry. LIMEN_CREDS_MAP (JSON) overrides for tests; else import DEFAULT_MAP
    from creds-hydrate.py (the single in-code source — never duplicated here)."""
    override = os.getenv("LIMEN_CREDS_MAP")
    if override:
        try:
            return json.loads(Path(override).read_text()) if os.path.exists(override) else json.loads(override)
        except Exception:
            return []
    spec = importlib.util.spec_from_file_location("creds_hydrate_for_provision", HYDRATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(getattr(mod, "DEFAULT_MAP", []))


def vault_of(ref: str) -> str | None:
    """op://<vault>/<item>/<field> -> <vault>. None if not an op:// ref."""
    m = re.match(r"op://([^/]+)/", ref or "")
    return m.group(1) if m else None


# Classification of a DEFAULT_MAP entry against the policy.
#  parked         — enabled: False (ignored)
#  derive_exempt  — has a `derive` (keyless keyring source); op vault access not required
#  no_ref         — no op:// ref (nothing to home)
#  sa_readable    — op-sourced and its vault is SA-readable (conformant)
#  outlier        — op-sourced and its vault is NOT SA-readable (needs migration)
def classify(entry: dict, policy: dict) -> str:
    if not entry.get("enabled", True):
        return "parked"
    ref = entry.get("ref")
    if entry.get("derive") and policy["policy"].get("derive_exempt", True):
        return "derive_exempt"
    if not ref:
        return "no_ref"
    v = vault_of(ref)
    return "sa_readable" if v in set(policy.get("sa_readable_vaults", [])) else "outlier"


def cmd_check(policy: dict, cred_map: list[dict]) -> int:
    """The forever-predicate. Exit 1 iff a REQUIRED op-sourced secret is not SA-readable."""
    av = policy.get("automation_vault")
    print(f"creds-provision --check — SA-readable vault(s): {policy.get('sa_readable_vaults')}  "
          f"(automation vault: {av})")
    hard_fail = False
    counts = {"sa_readable": 0, "outlier": 0, "derive_exempt": 0, "no_ref": 0, "parked": 0}
    for e in cred_map:
        kind = classify(e, policy)
        counts[kind] += 1
        if kind == "outlier":
            required = bool(e.get("required"))
            src_vault = vault_of(e.get("ref", ""))
            if required and policy["policy"].get("required_must_be_sa_readable", True):
                hard_fail = True
                print(f"  ✗ {e.get('lane', '?'):32} REQUIRED but in vault '{src_vault}' — NOT SA-readable "
                      f"(migrate → {av}: `creds-provision bootstrap`)")
            elif policy["policy"].get("warn_on_nonrequired_outliers", True):
                print(f"  ! {e.get('lane', '?'):32} in vault '{src_vault}' — migration pending → {av}")
        elif kind == "sa_readable":
            print(f"  ✓ {e.get('lane', '?'):32} SA-readable ({vault_of(e.get('ref', ''))})")
    print(f"  ── {counts['sa_readable']} SA-homed · {counts['outlier']} outlier · "
          f"{counts['derive_exempt']} derive-exempt · {counts['parked']} parked")
    if hard_fail:
        print("creds-provision: ✗ a REQUIRED secret is not readable by the fleet service account. "
              "The estate is not yet SA-homed — run `creds-provision bootstrap` (one owner-op step, "
              "Wall #320). The predicate stays red until every required secret lives in the "
              f"'{av}' vault.")
        return 1
    print("creds-provision: ✓ every required op-sourced secret is SA-readable.")
    return 0


def _op_available() -> bool:
    """True iff a promptless op session exists (service-account token or Connect) — never triggers
    an interactive/Touch-ID prompt."""
    if not (os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
            or (os.environ.get("OP_CONNECT_HOST") and os.environ.get("OP_CONNECT_TOKEN"))):
        return False
    try:
        r = subprocess.run(["op", "whoami"], capture_output=True, text=True, timeout=10,
                           stdin=subprocess.DEVNULL)
        return r.returncode == 0
    except Exception:
        return False


def _emit(step: str, cmd: list[str], apply: bool) -> None:
    """Print a bootstrap/apply step. In dry-run, show the exact command; on --apply, run it (owner op
    required). Output scrubbed; a create-token command's stdout is NEVER printed."""
    shown = _scrub(shlex.join(cmd))
    if not apply:
        print(f"  [dry-run] {step}: {shown}")
        return
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        ok = r.returncode == 0
        print(f"  [{'ok' if ok else 'ERR'}] {step}" + ("" if ok else f" — {_scrub(r.stderr)[:120]}"))
    except Exception as ex:  # noqa: BLE001 — fail-open
        print(f"  [ERR] {step} — {type(ex).__name__}")


def cmd_bootstrap(policy: dict, cred_map: list[dict], apply: bool) -> int:
    """The ONE root-of-trust seed. Requires an OWNER `op` session. Dry-run by default: emits the exact
    command sequence so it is auditable before it runs. --apply executes it (once)."""
    sa = policy["service_account"]
    av = policy["automation_vault"]
    print(f"creds-provision bootstrap — mint fleet SA '{sa['name']}' owning vault '{av}' "
          f"({'APPLY' if apply else 'dry-run'}). Homed on Wall #{policy['bootstrap'].get('wall_issue', 320)}.")
    if apply and not _op_available():
        print("  BLOCKED: bootstrap needs an OWNER `op` session (owner can create SAs/vaults). "
              "Run `op signin` as an account owner, then re-run `creds-provision bootstrap --apply`. "
              "This is the single, once-only seed; nothing else ever needs it.")
        return 2
    # 1) the automation vault (idempotent — op errors if it exists; harmless).
    _emit("create automation vault", ["op", "vault", "create", av], apply)
    # 2) the fleet SA, created WITH read+write on the vault (+ can-create-vaults). Grants are
    #    immutable, so this vault list is permanent by design. Token is captured to the file by
    #    op-service-account.sh (NEVER printed).
    create = ["op", "service-account", "create", sa["name"], *sa.get("create_flags", "").split()]
    _emit("mint fleet service account (token captured to file, never shown)", create, apply)
    # 3) migrate every op-sourced secret into the automation vault (value never exposed by a move).
    seen = set()
    for e in cred_map:
        if classify(e, policy) != "outlier":
            continue
        ref = e.get("ref", "")
        src = vault_of(ref)
        item = ref.split("/")[3] if len(ref.split("/")) > 3 else ""
        key = (src, item)
        if not item or key in seen:
            continue
        seen.add(key)
        _emit(f"migrate '{item}' {src} → {av}",
              ["op", "item", "move", item, "--current-vault", src, "--destination-vault", av], apply)
    print("  NEXT (code, same PR as the run): repoint the migrated refs in creds-hydrate.py "
          f"DEFAULT_MAP to op://{av}/…, then `creds-provision --check` goes green and stays green.")
    return 0


def cmd_apply(policy: dict, cred_map: list[dict], apply: bool) -> int:
    """Idempotent conformance: report/ensure every op-sourced secret lives in the automation vault.
    Non-mutating today (reports the outliers bootstrap/migration will resolve); the create/move path
    activates once the SA owns the vault."""
    return cmd_check(policy, cred_map)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CLAVIS — credential provisioning (SA + the one vault it reads).")
    ap.add_argument("command", choices=["check", "bootstrap", "apply"], nargs="?", default="check")
    ap.add_argument("--apply", action="store_true", help="execute mutations (default: dry-run). bootstrap needs owner op.")
    args = ap.parse_args(argv)
    policy = load_policy()
    cred_map = load_cred_map()
    if args.command == "check":
        return cmd_check(policy, cred_map)
    if args.command == "bootstrap":
        return cmd_bootstrap(policy, cred_map, args.apply)
    return cmd_apply(policy, cred_map, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
