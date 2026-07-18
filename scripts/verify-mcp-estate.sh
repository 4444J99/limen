#!/usr/bin/env bash
set -euo pipefail

# verify-mcp-estate.sh — the MCP-estate fixed-point predicate (the Ω of the MCP organ).
#
# Exit 0 ⟺ the local MCP estate holds three invariants:
#   1. BOOT     — every configured local/stdio MCP server across every agent CLI boots/reaches
#                 (scripts/mcp-server-boot.py, the Lane-A sensor).
#   2. DOORWAY  — the ianva aggregator has ≥1 upstream (a doorway that forwards nothing is a defect).
#                 Fail-OPEN when ianva isn't installed at all (a CI host), fail-CLOSED when ianva is
#                 present but its registries are empty (the real host defect the recon found).
#   3. OWNERSHIP— no PLACEHOLDER secret sits in any agent config (a `YOUR_…_TOKEN` placeholder means
#                 the server 401s — the github defect). A real literal token and a not-yet-cartridge-
#                 templated config are reported as WARN (Phase C hardens these into cartridge owners).
#
# Report-only today (NOT yet a gates.yaml gate or an omega rung): the estate has known-red defects
# (empty ianva registry, github placeholder PAT) that Phase B closes. Promotion to a hard omega rung
# is Phase C — you do not wire a red rung, you green the estate first. A RED here now is the sensor
# proving it can SEE the defects that were invisible before, not a bug.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() {
  printf '\n==> %s\n' "$*"
}

FAIL=0
fail() { printf 'FAIL  %s\n' "$*"; FAIL=1; }
ok()   { printf 'ok    %s\n' "$*"; }
warn() { printf 'warn  %s\n' "$*"; }

# ── Invariant 1: BOOT ─────────────────────────────────────────────────────────────────────────────
step "MCP boot — every configured local server across every agent CLI starts/reaches"
if python3 scripts/mcp-server-boot.py; then
  ok "all configured MCP servers boot/reach"
else
  fail "one or more configured MCP servers fail to boot/reach (see above)"
fi

# ── Invariant 2: DOORWAY ──────────────────────────────────────────────────────────────────────────
step "ianva doorway — the aggregator forwards ≥1 upstream (empty hub = every agent routes to nothing)"
if ! command -v ianva >/dev/null 2>&1 && [[ ! -d "$HOME/.config/ianva" ]]; then
  ok "ianva not present on this host — doorway check fail-open (CI/bare host)"
else
  # Count upstreams offline across ianva's two registry sources + its materialized settings. Any
  # non-empty source counts. Shapes handled: {name:{…}}, {"servers":[…]}, {"mcpServers":{…}}.
  UPSTREAMS="$(python3 - <<'PY'
import json, os
from pathlib import Path
home = Path.home()
sources = [
    Path(os.environ.get("IANVA_REGISTRY", home / ".agents" / "mcp" / "servers.json")),
    home / ".config" / "ianva" / "upstreams.json",
    home / ".config" / "ianva" / "mcp_settings.json",
]
total = 0
for p in sources:
    try:
        data = json.loads(p.read_text())
    except Exception:
        continue
    for key in ("mcpServers", "servers", "upstreams"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, dict):
            total += len(v)
        elif isinstance(v, list):
            total += len(v)
    # bare top-level name->spec map (no envelope)
    if isinstance(data, dict) and not any(k in data for k in ("mcpServers", "servers", "upstreams")):
        total += sum(1 for k in data if isinstance(data[k], dict))
print(total)
PY
)"
  if [[ "${UPSTREAMS:-0}" -ge 1 ]]; then
    ok "ianva has $UPSTREAMS upstream(s)"
  else
    fail "ianva is present but has 0 upstreams — the doorway forwards nothing (deploy ianva/upstreams.example.json or \`ianva add-upstream …\`)"
  fi
fi

# ── Invariant 3: OWNERSHIP (no placeholder secret; cartridge-ownership reported) ────────────────────
step "MCP config ownership — no placeholder secret; each config cartridge-owned (WARN until Phase C)"
CONFIGS=(
  "$HOME/.copilot/mcp-config.json"
  "$HOME/.codex/config.toml"
  "$HOME/.gemini/settings.json"
  "$HOME/.gemini/config/mcp_config.json"
  "$HOME/.claude.json"
  "$HOME/.cline/data/settings/cline_mcp_settings.json"
  "$HOME/.config/opencode/opencode.jsonc"
)
# Placeholder tokens = a broken server (github's YOUR_GITHUB_PERSONAL_ACCESS_TOKEN 401s). Hard fail.
PLACEHOLDER_RE='YOUR_[A-Z0-9_]*(TOKEN|KEY|SECRET|PAT)|<[A-Za-z0-9_]*(TOKEN|KEY|SECRET|PAT)[A-Za-z0-9_]*>|CHANGEME|PLACEHOLDER_TOKEN'
# Real literal tokens = a Phase-C cartridge-templating concern (should be op://-hydrated). Reported WARN.
LITERAL_RE='ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}'
for cfg in "${CONFIGS[@]}"; do
  [[ -f "$cfg" ]] || continue
  base="${cfg/#$HOME/\~}"
  if grep -Eq "$PLACEHOLDER_RE" "$cfg" 2>/dev/null; then
    fail "$base holds a PLACEHOLDER secret — the server boots but 401s (route it through the credential organ)"
  fi
  if grep -Eq "$LITERAL_RE" "$cfg" 2>/dev/null; then
    warn "$base holds a literal token — cartridge-template it via op:// (Phase C: dot_copilot/mcp-config.json.tmpl)"
  fi
  # Cartridge-ownership (informational until the Phase-C templates land).
  if command -v chezmoi >/dev/null 2>&1 && chezmoi managed 2>/dev/null | grep -Fq "${cfg#"$HOME"/}"; then
    ok "$base is cartridge-owned (chezmoi-managed)"
  else
    warn "$base has no cartridge owner yet — Phase C adds a chezmoi source template"
  fi
done

# ── Verdict ─────────────────────────────────────────────────────────────────────────────────────
echo
if [[ "$FAIL" -eq 0 ]]; then
  printf '\nMCP estate verification passed\n'
  exit 0
fi
printf '\nMCP estate verification FAILED — %s\n' "the RED invariants above are the real defects the organ now senses (Phase B closes them; Phase C promotes this to an omega rung)."
exit 1
