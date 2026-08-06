#!/usr/bin/env bash
# dialogs-silenced.sh — the executable predicate for "no more permission/auth/fingerprint dialogs".
#
# Anthony's standing demand: never be asked for a permission, a fingerprint, or an OS dialog
# again — across Claude, the fleet, and the whole machine. The recurring dialogs are not random;
# they come from NINE named classes (0, 1, 1b, 1c, 1d, 2, 3, 4, 4b), in two kinds.
#
# HUMAN-GATED (1, 1c, 1d, 2, 3): security boundaries only a human with privilege can lower — a
# background agent physically cannot turn off the OS firewall, mint a 1Password service account, or
# widen its own permission gate; that impossibility IS the guardrail.
# AGENT-CURABLE (0, 1b, 4, 4b): each has a shipped beat effector behind a LIMEN_*_HEAL valve, checked
# here so none can silently reseed. `--agent-curable-only` scores this half alone, which is what lets
# the beat drive it to a durable HOLDS while a self-mod class keeps the bare predicate red.
#
# This script names each class, reports whether it is silenced, and prints the EXACT one-time cure for
# any that is not. Each cure is one action, then silent forever.
#
# Idempotent, read-only, no sudo. Run anytime:  bash scripts/dialogs-silenced.sh
# Exit 0  ⟺  every recurring dialog class is silenced (the done-predicate).
set -uo pipefail

# --agent-curable-only: count the classes that have a shipped beat effector (1b hook-drift,
# 4 gatekeeper-cask, 4b lsregister-stub) plus the stable-host identity invariant toward the exit
# status. Human-gated classes (defaultMode /
# ask-list / hook-wiring self-mod, 1Password, firewall) and the effectorless quarantined-binary case
# still PRINT as advisory but do not fail this mode. This is the form the omega fixed point
# (scripts/omega.sh) holds against: the bare predicate can never reach exit 0 while a self-mod class
# exists, but the agent-curable estate can — so the beat can drive THAT half to a durable HOLDS.
AGENT_ONLY=0
case "${1:-}" in
  --agent-curable-only) AGENT_ONLY=1 ;;
  "") : ;;
  -h|--help) echo "usage: $0 [--agent-curable-only]"; exit 0 ;;
  *) echo "usage: $0 [--agent-curable-only]" >&2; exit 2 ;;
esac

gaps=0            # every dialog class that still prompts (the bare predicate)
curable_gaps=0    # subset with a shipped beat effector (drives the omega rung + --agent-curable-only)
green(){ printf '  \033[32m✓\033[0m %s\n' "$1"; }
red(){   printf '  \033[31m✗\033[0m %s\n' "$1"; gaps=$((gaps+1)); }
redx(){  printf '  \033[31m✗\033[0m %s\n' "$1"; gaps=$((gaps+1)); curable_gaps=$((curable_gaps+1)); }
redb(){  printf '  \033[31m✗\033[0m %s\n' "$1"; gaps=$((gaps+1)); curable_gaps=$((curable_gaps+1)); }
cure(){  printf '      ↳ %s\n' "$1"; }
note(){  printf '      · %s\n' "$1"; }
ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"

echo "== dialogs-silenced — recurring permission classes + stable TCC identity =="
echo

# ── 0. macOS responsibility identity — updates rotate below one fixed native host. ──
# This is the structural cure for version-path TCC churn. The audit is read-only and itself enters
# through DomusAgentHost before opening TCC.db, so Python cannot become the new permission client.
# It fails when update-disabling variables reappear, the fixed app/signature drifts, a managed
# identity appears outside the redacted baseline, any App Management path row remains visible
# (disabled included), a tracked GUI ingress bypasses `domus-agent-host ensure --`, or a malformed
# Claude helper is registered.
TCC_AUDIT="$ROOT/scripts/tcc-identity-audit"
if [ ! -f "$TCC_AUDIT" ] || [ ! -r "$TCC_AUDIT" ] || [ ! -x "$TCC_AUDIT" ]; then
  tcc_output="tcc-identity-audit wrapper is missing, unreadable, or not executable: $TCC_AUDIT"
  tcc_status=69
else
  tcc_output="$("$TCC_AUDIT" --strict 2>&1)"
  tcc_status=$?
fi
if [ "$tcc_status" -eq 0 ]; then
  green "TCC identity: automatic updates enabled; stable host valid; active leaks, visible path rows, and unhosted ingresses all zero"
else
  redb "TCC identity invariant is not contained (audit exit $tcc_status)"
  while IFS= read -r audit_line; do
    [ -n "$audit_line" ] && note "$audit_line"
  done <<EOF
$tcc_output
EOF
  cure "Install/apply DomusAgentHost, route the named launch seam through it, then run: tcc-identity-audit --strict"
  note "Never cure this by setting DISABLE_AUTOUPDATER, DISABLE_UPDATES, HOMEBREW_NO_AUTO_UPDATE, pinning a tool, resetting all TCC, or editing TCC.db."
fi
echo

# ── 1. Claude Code in-app permission prompts — the highest-volume "asking permission". ──
SETTINGS="$HOME/.claude/settings.json"
mode="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(""); raise SystemExit
print((d.get("permissions") or {}).get("defaultMode", ""))
PY
)"
# THE SURGICAL PATH IS A GREEN, NOT A CONSOLATION PRIZE (fixed 2026-07-31).
# This class used to demand bypassPermissions for green, so the estate could NEVER reach
# ALL CLEAR while holding the configuration the spec and IF-NO-MODAL actually recommend —
# the predicate contradicted its own doctrine and manufactured a permanent red. `auto` with
# the trust hook wired, the five ask rules in place, and autoMode.allow teaching the
# classifier IS the ideal (never-hang-permission-spec §Design-consequences-2): it reaches
# zero prompts on non-destructive work while KEEPING the instrument that measures it.
surgical="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("no"); raise SystemExit
perms = d.get("permissions") or {}
want = {"Bash(git push* --force*)", "Bash(git push* -f*)", "Bash(rm:*)", "Bash(rmdir:*)", "Bash(shred:*)"}
hooks = (d.get("hooks") or {}).get("PreToolUse") or []
wired = any("allow-trusted-cd-git.sh" in str(h.get("command", ""))
            for g in hooks for h in (g.get("hooks") or []))
allow = ((perms.get("autoMode") or {}).get("allow") or [])
ok = (perms.get("defaultMode") == "auto" and wired
      and set(perms.get("ask") or []) == want
      and bool(allow) and allow[0] == "$defaults")
print("yes" if ok else "no")
PY
)"
if [ "$mode" = "bypassPermissions" ]; then
  green "Claude prompts: permissions.defaultMode = bypassPermissions (no in-app prompts)"
elif [ "$surgical" = "yes" ]; then
  green "Claude prompts: the surgical estate is complete — defaultMode 'auto' + trust hook wired + five ask rules + autoMode.allow"
  note "This is the RECOMMENDED terminal state, not a partial one: zero prompts on non-destructive"
  note "  work, while destruction outside disposable paths, force-push and sudo still gate — and the"
  note "  gauge that measures 'does it ask?' stays alive. bypassPermissions would delete that gauge."
else
  red "Claude prompts: defaultMode is '${mode:-unset}' — Claude still asks for off-allowlist tools"
  cure "PREFER the surgical path (class 1d below): python3 scripts/heal-hook-wiring.py --apply"
  note "An AI cannot set this for you: disabling one's own approval gate is guard-railed by design."
  note "acceptEdits is NOT enough — it still prompts for Bash. bypassPermissions = truly zero prompts."
  note "But bypassPermissions is NOT recommended and is NOT this repo's contract (never-hang-permission-spec"
  note "  §Design-consequences-2): it does not close the distance to the ideal, it DELETES the instrument —"
  note "  you cannot measure 'does it ask?' where nothing can ask, and it silently un-gates the rm class that"
  note "  once wiped the live checkout. Keep defaultMode 'auto'; make the hook good enough that auto never asks."
  note "If you still want it: edit the CARTRIDGE SOURCE (domus-genoma private_dot_claude/settings.json.tmpl),"
  note "  NOT $SETTINGS — that file is rendered and the next \`chezmoi apply\` overwrites a hand edit (Rule #6)."
fi

# ── 1b. Live-hook drift — deployed hooks must match the repo canonical sources. ──
# The PreToolUse trust hook is THE mechanism that silences fleet/auto-mode prompts
# (`--permission-mode auto` overrides bypassPermissions; no settings allow rule can
# suppress the compound-cd guard, and only a hook `allow` preempts the destructive
# ask rules for path-gated reap work — docs/never-hang-permission-spec.md). A stale
# live copy silently reintroduces the prompt flood, so parity is a checked class.
for hf in allow-trusted-cd-git.sh insights-capture.sh; do
  canon="$ROOT/scripts/hooks/$hf"; live="$HOME/.claude/hooks/$hf"
  [ -f "$canon" ] || continue
  if [ ! -f "$live" ]; then
    redx "Hook drift: $live is MISSING (repo canonical exists)"
    cure "LIMEN_HOOK_DRIFT_HEAL=1 bash scripts/heal-hook-drift.sh   # effector; or by hand: install -m 755 $canon $live"
  elif [ "$(shasum -a 256 < "$canon" | cut -d' ' -f1)" != "$(shasum -a 256 < "$live" | cut -d' ' -f1)" ]; then
    redx "Hook drift: $live differs from repo canonical scripts/hooks/$hf"
    cure "LIMEN_HOOK_DRIFT_HEAL=1 bash scripts/heal-hook-drift.sh   # effector; or by hand: install -m 755 $canon $live"
    note "Run from the MAIN checkout — comparing against a stale worktree copy will false-red."
  else
    green "Hook parity: $hf live == repo canonical"
  fi
done

# ── 1c. Ask-list policy — the five destructive ask rules are the fail-safe backstop. ──
# If the trust hook ever breaks, behavior must degrade to PROMPTING on rm/force-push,
# never to silent approval (Bash(*) is in allow, so removing an ask rule = silent allow).
askdelta="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
want = sorted(["Bash(git push* --force*)", "Bash(git push* -f*)", "Bash(rm:*)", "Bash(rmdir:*)", "Bash(shred:*)"])
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("settings unreadable"); raise SystemExit
got = sorted((d.get("permissions") or {}).get("ask") or [])
if got != want:
    missing = [r for r in want if r not in got]
    extra = [r for r in got if r not in want]
    print(f"missing={missing} extra={extra}")
PY
)"
if [ -z "$askdelta" ]; then
  green "Ask-list policy: the five destructive ask rules are exactly in place (fail-safe backstop)"
else
  red "Ask-list policy drift: $askdelta"
  cure "python3 scripts/heal-hook-wiring.py --apply   # same effector asserts these five in the CARTRIDGE SOURCE"
  note "Exactly: Bash(git push* --force*), Bash(git push* -f*), Bash(rm:*), Bash(rmdir:*), Bash(shred:*)."
  note "Assert them in domus-genoma private_dot_claude/settings.json.tmpl — $SETTINGS is rendered (Rule #6)."
fi

# ── 1d. Hook wiring — settings must actually run the trust hook on Bash PreToolUse. ──
wired="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("no"); raise SystemExit
# SUBSTRING, never endswith (fixed 2026-07-31). The wiring is a GUARDED invocation —
#   H=$HOME/.claude/hooks/allow-trusted-cd-git.sh; [ -x "$H" ] && "$H" || true
# so a machine without the hook deployed cannot error. That command ends in `|| true`, so
# the old endswith test reported NOT WIRED against a correctly wired, live, working gate —
# measured on the first successful arming. A sensor that only recognises one spelling of a
# correct state manufactures phantom work; match the hook identity, not its call syntax.
for m in (d.get("hooks") or {}).get("PreToolUse") or []:
    for h in m.get("hooks") or []:
        if "allow-trusted-cd-git.sh" in str(h.get("command", "")):
            print("yes"); raise SystemExit
print("no")
PY
)"
if [ "$wired" = "yes" ]; then
  green "Hook wired: hooks.PreToolUse runs ~/.claude/hooks/allow-trusted-cd-git.sh"
else
  # `red`, NOT `redx`: the effector below exists, but the auto-mode classifier blocks the AGENT
  # from running it (verified 2026-07-31 — the block covers the chezmoi SOURCE, not just the
  # rendered target). So this class has a shipped cure but no agent-executable path; counting it
  # curable would wedge --agent-curable-only and the omega fixed point forever.
  red "Trust hook NOT wired in $SETTINGS hooks.PreToolUse — the compound-cd guard floods every fleet job"
  cure "python3 scripts/heal-hook-wiring.py --apply   # effector: asserts hook + ask + autoMode in the CARTRIDGE SOURCE, then chezmoi apply"
  note "$SETTINGS is RENDERED (owner: cartridge, mechanism: template — config-ownership.json)."
  note "Editing it by hand is futile: the next \`chezmoi apply\` overwrites it. Fix the base, never the output (Rule #6)."
  note "The effector is OPERATOR-ARMED and deliberately NOT beat-wired: an agent must never be the actor that widens its own gate."
fi
echo

# ── 2. 1Password / Touch-ID — the fingerprint dialogs. ──
# SILENCED when NO automated path calls `op` — then a locked vault can never pop Touch-ID unattended.
# creds-hydrate.py is the only `op` caller; it now reads op ONLY with an explicit --op flag (opt-in),
# so a bare TTY (every daemon beat AND every interactive session) no longer triggers it — that TTY
# clause WAS the storm. A service-account token (the only promptless `op`) is the PERMANENT cure: install
# it ONCE at $SA_FILE and every op:// read goes silent forever — the daemon beat, the op:// lanes, and the
# --sweep-all catch-all all hydrate with ZERO Touch-ID. Absent the token, op stays strictly opt-in (--op),
# so nothing pops unattended either way. Install via scripts/op-service-account.sh. [[macos-tcc-gatekeeper-dialogs-solved]]
CREDS="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/scripts/creds-hydrate.py"
SA_FILE="${LIMEN_OP_SA_TOKEN_FILE:-$HOME/.config/op/service-account-token}"
if [ -f "$CREDS" ] && grep -q 'op_ok = op_can_read_silently() or args\.op' "$CREDS" \
   && ! grep -Eq 'op_ok *=.*running_interactively\(\)' "$CREDS"; then
  green "1Password: op:// reads are OPT-IN (--op only) → no daemon beat or session can pop Touch-ID"
  note "SSH agent routing is also opt-in (LIMEN_USE_1PASSWORD_SSH; organvm/domus-genoma#130) — git is HTTPS, so SSH never hits 1Password either."
  if [ -n "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] || { [ -f "$SA_FILE" ] && [ -s "$SA_FILE" ]; }; then
    green "service-account token present → op:// lanes AND --sweep-all hydrate unattended, promptless, forever."
  else
    note "op:// lanes hydrate via 'creds-hydrate --apply --op' at a terminal (one deliberate touch), OR — to go"
    note "promptless FOREVER (no touch, ever) — install the service-account token once:  scripts/op-service-account.sh install"
  fi
else
  red "1Password: creds-hydrate still auto-reads 'op' (no opt-in gate) → can pop Touch-ID unattended"
  cure "Make 'op read' opt-in in scripts/creds-hydrate.py:  op_ok = op_can_read_silently() or args.op  (drop the running_interactively() clause; add a --op flag)."
  note "This is a CODE fix an agent CAN land (no human needed). To also make op:// promptless forever, install a service-account token: scripts/op-service-account.sh install."
fi
echo

# ── 3. macOS Application Firewall — 'python/node wants to accept incoming connections'. ──
FW=/usr/libexec/ApplicationFirewall/socketfilterfw
if [ ! -x "$FW" ]; then
  green "Firewall: socketfilterfw not present — nothing to silence"
elif "$FW" --getglobalstate 2>/dev/null | grep -qi 'disabled'; then
  green "Firewall: application firewall is off → no incoming-connection prompts, ever"
else
  cur_node="$(readlink -f "$(command -v node 2>/dev/null)" 2>/dev/null || true)"
  if [ -n "$cur_node" ] && "$FW" --listapps 2>/dev/null | grep -qF "$cur_node"; then
    green "Firewall: on, but the current node ($cur_node) is allow-listed"
    note "A future 'brew upgrade node' rotates the path and re-prompts — turn the firewall off, or 'brew pin node', to make it durable."
  else
    red "Firewall: on, and the current node is not allow-listed → mcphub (binds all interfaces) will re-prompt"
    cure "Zero prompts forever (recommended — single-user box behind NAT, fully reversible):"
    cure "   sudo $FW --setglobalstate off"
    cure "Or keep the firewall on and allow the one offender (re-prompts on each node upgrade unless you also 'brew pin node'):"
    cure "   N=\"\$(readlink -f \$(command -v node))\"; sudo $FW --add \"\$N\" --unblockapp \"\$N\""
    note "Homed as L-FIREWALL-PROMPT."
  fi
fi
echo

# ── 4. Gatekeeper — "'claude' is an app downloaded from the Internet" (Dialog 6, 2026-07-04). ──
# ROOT: a DUPLICATE install of Claude Code via a Homebrew cask. Casks (unlike bottled formulae)
# stamp com.apple.quarantine on every download, so each cask upgrade = a fresh quarantined binary
# at a new Caskroom path = a Gatekeeper first-open prompt. It is an independent rotating install,
# not the sanctioned updater-managed native ~/.local/bin/claude. Agent-curable.
if command -v brew >/dev/null 2>&1 && brew list --cask 2>/dev/null | grep -qx 'claude-code'; then
  redx "Gatekeeper: duplicate Homebrew cask 'claude-code' installed → quarantined per upgrade, prompts on first exec"
  cure "LIMEN_CASK_DUPLICATE_HEAL=1 bash scripts/heal-claude-cask.sh   # effector; or by hand: brew uninstall --cask claude-code (native ~/.local/bin/claude is the sanctioned install)"
  note "Never click Open/Allow on the dialog — futile vs version churn; never brew-install claude in provisioning."
else
  quarantined=""
  for c in $(which -a claude 2>/dev/null | sort -u); do
    xattr -p com.apple.quarantine "$(readlink -f "$c" 2>/dev/null || echo "$c")" >/dev/null 2>&1 && quarantined="$quarantined $c"
  done
  if [ -n "$quarantined" ]; then
    red "Gatekeeper: quarantined claude binary on PATH:$quarantined → will prompt on first exec"
    cure "xattr -d com.apple.quarantine <binary>   # or remove the duplicate install entirely"
  else
    green "Gatekeeper: single unquarantined claude install (no brew-cask duplicate) — no first-open prompt possible"
  fi
fi
echo

# ── 4b. Gatekeeper — a REGISTERED, unassessable ClaudeCode.app ("damaged, move to Trash"). ──
# ROOT — corrected 2026-08-05, reproduced from scratch. The prior text ("an older CLI shipped a stub";
# "steady state for 2.1.190+ is ZERO registrations") was false on both halves, and that premise is why
# this recurred ~10-15x across five cures. The LIVE binary materializes the bundle on EVERY start, and
# the bundle is Gatekeeper-invalid BY CONSTRUCTION: a bare-Mach-O signature seals no resources
# (`Sealed Resources=none`), while bundle-form `--strict` demands a Contents/_CodeSignature/CodeResources
# it never sealed. The same inode passes bare and fails bundled, so "absent" and "valid" are BOTH
# unreachable — the only reachable fixed point is PRESENT (for exec, and for the TCC identity 0g8d
# keeps) and UNREGISTERED (so Gatekeeper is never asked to assess it). `execve` needs no registration;
# only the dialog does. The "Move to Trash" button still reseeds into ~/.Trash, which IS swept.
# scripts/heal-claude-lsregister.sh is the effector; this block is its sensor. Agent-curable.
# Ideal form: IF-GATEKEEPER-INERT. [[macos-tcc-gatekeeper-dialogs-solved]]
# Same seam as scripts/heal-claude-lsregister.sh, and for the same reason: this block reimplements
# condemnable()'s decision in a SECOND file, and both copies narrowed to one exact codesign string
# for six weeks — so the sensor reported green on precisely the state the effector could not cure.
# A text assertion can only catch re-introducing that one string; the seam lets the contract in
# scripts/tests/heal-claude-lsregister.test.sh drive this block against a fixture and check what it
# actually CONCLUDES. Unset in production.
LSREG="${LIMEN_CLAUDE_LSREGISTER_BIN:-/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Support/lsregister}"
stub_bad=""
if [ -x "$LSREG" ]; then
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    case "$p" in "$HOME"/.local/share/claude/*|"$HOME"/.Trash/*) : ;; *) continue ;; esac
    # ANY non-zero verdict, not one exact string. The old exact-string filter missed the mid-write
    # state ("code object is not signed at all") — which is precisely the state macOS renders as
    # "damaged" — so the sensor reported green on the condition it exists to catch. Kept in lockstep
    # with condemnable() in scripts/heal-claude-lsregister.sh; both are contract-tested.
    codesign --verify --strict "$p" >/dev/null 2>&1 || stub_bad="$stub_bad $p"
  done <<EOF
$("$LSREG" -dump 2>/dev/null | grep -oE '/[^ ()]*ClaudeCode\.app' | sort -u)
EOF
fi
if [ -z "$stub_bad" ]; then
  green "Gatekeeper: ClaudeCode.app is inert — 0 unassessable LaunchServices registrations (IF-GATEKEEPER-INERT)"
else
  redx "Gatekeeper: LaunchServices-registered ClaudeCode.app cannot be assessed → 'damaged, move to Trash' on launch:$stub_bad"
  cure "LIMEN_CLAUDE_LSREGISTER_HEAL=1 bash scripts/heal-claude-lsregister.sh   # UNREGISTER (leaving the bundle in place), sweep ~/.Trash, re-verify count 0"
  note "Never click 'Move to Trash' — it reseeds the loop into ~/.Trash, where LaunchServices keeps it registered. And never DELETE the bundle: the vendor recreates it every start, and removal destroys the stable TCC identity sensor 0g8d keeps. Unregistration is the convergent cure; removal is a duty cycle."
fi
echo

if [ "$AGENT_ONLY" = 1 ]; then
  if [ "$curable_gaps" -eq 0 ]; then
    if [ "$gaps" -eq 0 ]; then
      echo "ALL CLEAR (agent-curable) — every beat-healable dialog class is silenced (and no human-gated class prompts either)."
    else
      printf 'ALL CLEAR (agent-curable) — every beat-healable dialog class is silenced. (%s human-gated advisory item(s) above are not beat-curable and do not gate this mode.)\n' "$gaps"
    fi
    exit 0
  fi
  printf '%s agent-curable class(es) still prompt — the beat effector cures each on its next armed hygiene tick.\n' "$curable_gaps"
  echo "Arm the matching LIMEN_*_HEAL valve(s) in ~/.limen.env (homed as lever L-DIALOGS-HEAL), or run the cure shown above by hand."
  exit 1
fi

if [ "$gaps" -eq 0 ]; then
  echo "ALL CLEAR — no recurring permission dialog remains. (re-run anytime to confirm it stays so)"
  exit 0
fi
printf '%s class(es) still prompt. Each cure above is ONE one-time action, then silent forever.\n' "$gaps"
echo "Do them, then re-run this script — it must print ALL CLEAR."
echo "(Residual one-offs like 'python wants to access Documents' = grant Full Disk Access to your terminal in"
echo " System Settings ▸ Privacy & Security ▸ Full Disk Access — a catch-all for file-access TCC dialogs.)"
exit 1
