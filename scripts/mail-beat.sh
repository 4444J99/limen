#!/usr/bin/env bash
# mail-beat.sh — the C_MAIL organ: the inbound mail lane, autonomic + fail-open.
#
# Each C_MAIL beat:
#   1. SWEEP every Apple Mail account, keylessly + reversibly — flag the fires (a status
#      bit Gmail respects) and archive folder-store noise (iCloud/Outlook, reliable). The
#      futile/blocked Gmail bulk-archive is SKIPPED (--flag-only-gmail) so the beat stays
#      bounded. Mutating; needs the one-time macOS Automation grant (lever
#      L-MAIL-AUTOMATION-GRANT). Fails SAFE: if accounts can't be enumerated (no grant on
#      the daemon), the sweep is skipped with a note — it never hangs or aborts the beat.
#   2. BUILD the obligations ledger from the fresh receipts (derived, no LLM, no network).
#   3. DRAFT — enrich each reply-owed obligation with a voice-matched draft (NEVER sent).
#      Enrich-only by default (draft_text visible in the ledger/face, no mailbox touch);
#      persist real Drafts only when LIMEN_MAIL_DRAFTS=1 (idempotent; needs the grant).
#   4. STATUS — refresh the UMA mail-status receipt (read-only census for the beat MAIL: line).
#   5. RENDER the pervasive faces (obligations.html → 127.0.0.1:8788/obligations.html).
#
# Reversible-only (flag/archive/draft; never delete, never send). Every step is wrapped so
# one failure never aborts the beat or the daemon ([[no-never-happens-again]]).
# Opt out of the mutating sweep with LIMEN_MAIL_SWEEP=0 (still rebuilds the ledger/face).
set -uo pipefail

export HOME="${HOME:-/Users/4jp}"
LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
UMA_ROOT="${UMA_ROOT:-$HOME/Workspace/universal-mail--automation}"
LEDGER="${LIMEN_OBLIGATIONS_LEDGER:-$LIMEN_ROOT/obligations-ledger.json}"
PY="${LIMEN_PY:-python3}"
STATUS_OUT="${LIMEN_MAIL_STATUS_OUT:-$LIMEN_ROOT/logs/uma-mail-status.json}"
OPS_REPORT="${UMA_OPS_REPORT_PATH:-$HOME/System/Reports/mail-triage/latest.json}"
HISTORY_REPORT="${UMA_HISTORICAL_MAIL_PATH:-$HOME/System/Reports/mail-history/latest.json}"
MAX_AGE_HOURS="${LIMEN_MAIL_STATUS_MAX_AGE_HOURS:-24}"

# DAEMON-SAFETY: never let a hung/slow Mail AppleScript block the heartbeat beat. Two
# structural bounds: (1) the sweep reads only the most-recent N messages (new arrivals —
# the full backlog was already swept), so each account is a couple of paged reads, not the
# whole inbox; (2) every step runs under `timeout` when available (homebrew coreutils on the
# daemon PATH). Without `timeout`, the small --limit + the provider's per-call 30s AppleScript
# cap keep it bounded anyway.
SWEEP_LIMIT="${LIMEN_MAIL_SWEEP_LIMIT:-80}"
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
bounded() {  # bounded <secs> <cmd...>  — time-box if a timeout binary exists, else run plain
  if [ -n "$TIMEOUT_BIN" ]; then "$TIMEOUT_BIN" "$@"; else shift; "$@"; fi
}
run_tmp() {  # run_tmp <secs> <cmd...>  — run with cwd=/tmp (avoids the platform/ shadow), bounded, fail-open
  local secs="$1"; shift
  bounded "$secs" bash -c 'cd /tmp && exec "$@"' _ "$@" 2>&1 | tail -1 || true
}

uma_cmd_json() {
  if [ -n "${UMA_BIN:-}" ]; then
    printf '%s\n' "[\"$UMA_BIN\"]"
  elif [ -f "$UMA_ROOT/cli.py" ]; then
    "$PY" - "$PY" "$UMA_ROOT/cli.py" <<'PY'
import json
import sys

print(json.dumps([sys.argv[1], sys.argv[2]]))
PY
  else
    printf '%s\n' '["umail"]'
  fi
}

run_status() {
  "$PY" - "$STATUS_OUT" "$OPS_REPORT" "$HISTORY_REPORT" "$MAX_AGE_HOURS" "$(uma_cmd_json)" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

out = Path(sys.argv[1])
ops = sys.argv[2]
history = sys.argv[3]
max_age = sys.argv[4]
cmd = json.loads(sys.argv[5])
command = [
    *cmd,
    "mail-status",
    "--ops-report",
    ops,
    "--history",
    history,
    "--max-age-hours",
    max_age,
    "--output",
    str(out),
]
proc = subprocess.run(command, text=True, capture_output=True, check=False)
if proc.returncode not in (0, 2):
    out.parent.mkdir(parents=True, exist_ok=True)
    detail = (proc.stderr.strip() or proc.stdout.strip() or "unknown failure")[:500]
    fallback = {
        "schema": "uma.mail.status.v1",
        "status": "blocked",
        "mode": {"read_only": True, "mailbox_mutations": False, "sends": False},
        "privacy": {"redacted": True, "public_safe": True},
        "blockers": [
            {
                "surface": "uma_mail_status",
                "status": "blocked",
                "detail": detail,
            }
        ],
        "current_ops": {"available": False, "kpis": {}},
        "historical_crosswalk": {"available": False, "kpis": {}},
        "answers": {},
        "next_queue": [],
    }
    out.write_text(json.dumps(fallback, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "blocked", "output": str(out), "returncode": proc.returncode}, sort_keys=True))
    raise SystemExit(0)

print(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else json.dumps({"status": "ok", "output": str(out)}))
PY
}

if [ "${1:-}" = "--census" ]; then
  "$PY" - "$LIMEN_ROOT" "$UMA_ROOT" "$STATUS_OUT" "$OPS_REPORT" "$HISTORY_REPORT" "$(uma_cmd_json)" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
uma = Path(sys.argv[2])
status_path = Path(sys.argv[3])
ops = Path(sys.argv[4])
history = Path(sys.argv[5])
cmd = json.loads(sys.argv[6])


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


status = load_json(status_path)
mode = status.get("mode") if isinstance(status.get("mode"), dict) else {}
current = status.get("current_ops") if isinstance(status.get("current_ops"), dict) else {}
historical = status.get("historical_crosswalk") if isinstance(status.get("historical_crosswalk"), dict) else {}
historical_kpis = historical.get("kpis") if isinstance(historical.get("kpis"), dict) else {}

print(json.dumps({
    "limen_root_present": root.exists(),
    "uma_root_present": uma.exists(),
    "uma_cli_present": (uma / "cli.py").exists() or bool(cmd),
    "uma_command": cmd[0] if cmd else None,
    "status_receipt_present": status_path.exists(),
    "status_schema": status.get("schema"),
    "status_value": status.get("status"),
    "current_ops_available": bool(current.get("available")),
    "historical_crosswalk_available": bool(historical.get("available")),
    "historical_reconciled": historical_kpis.get("reconciled"),
    "historical_source_messages": historical_kpis.get("source_messages"),
    "next_queue_count": len(status.get("next_queue") or []),
    "blocker_count": len(status.get("blockers") or []),
    "mailbox_mutations_allowed": bool(mode.get("mailbox_mutations")),
    "sends_allowed": bool(mode.get("sends")),
    "ops_report_present": ops.exists(),
    "history_report_present": history.exists(),
    "wrapper": True,
}, indent=2, sort_keys=True))
PY
  exit 0
fi

# 0) SYNC the UMA checkout so the beat never runs stale mail code. The beat executes scripts
#    straight out of $UMA_ROOT, and nothing kept that checkout current — it drifted commits
#    behind origin (the archived-scan feature merged while the beat ran the pre-merge tree).
#    ONLY a clean, on-`main`, fast-forwardable checkout is advanced: a dirty tree or a work
#    branch is left untouched (never a merge/rebase — fail-open). Untracked files (e.g. a local
#    .worktrees/) don't count as dirty. Opt out with LIMEN_MAIL_UMA_SYNC=0.
if [ "${LIMEN_MAIL_UMA_SYNC:-1}" = "1" ] && [ -d "$UMA_ROOT/.git" ]; then
  uma_branch="$(git -C "$UMA_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  uma_dirty="$(git -C "$UMA_ROOT" status --porcelain --untracked-files=no 2>/dev/null)"
  if [ "$uma_branch" = "main" ] && [ -z "$uma_dirty" ]; then
    if bounded 60 git -C "$UMA_ROOT" fetch --quiet origin main 2>/dev/null \
       && bounded 30 git -C "$UMA_ROOT" merge --ff-only --quiet origin/main 2>/dev/null; then
      echo "mail-beat: UMA checkout fast-forwarded to origin/main"
    else
      echo "mail-beat: UMA sync skipped (offline, non-fast-forward, or busy) — running current checkout"
    fi
  else
    echo "mail-beat: UMA checkout off-main ($uma_branch) or dirty — sync skipped, running as-is"
  fi
fi

# 1) SWEEP — reversible flag+archive per account (mutating; needs the Automation grant).
#    Account names come straight from Mail (no creds, no python import). The futile Gmail
#    archive is skipped; iCloud/Outlook (folder stores) archive reliably; fires flag
#    everywhere. Heavy AppleScript reads, so this runs on the C_MAIL cadence. The account
#    enumeration is time-boxed so a TCC-denied Mail query on the daemon can't hang the beat.
if [ "${LIMEN_MAIL_SWEEP:-1}" = "1" ]; then
  accts="$(bounded 20 osascript -e 'tell application "Mail" to get name of every account' 2>/dev/null || true)"
  if [ -n "$accts" ]; then
    OLDIFS="$IFS"; IFS=','
    for a in $accts; do
      a="${a#"${a%%[![:space:]]*}"}"; a="${a%"${a##*[![:space:]]}"}"   # trim
      [ -z "$a" ] && continue
      run_tmp 240 "$PY" "$UMA_ROOT/inbox_sweep.py" --account "$a" --apply --flag-only-gmail --limit "$SWEEP_LIMIT"
    done
    IFS="$OLDIFS"
  else
    echo "mail-beat: no Mail accounts enumerated (Automation grant? skipping sweep)"
  fi
fi

# 1b) ARCHIVE Gmail noise over RAW IMAP — the one store Apple Mail cannot archive. The
#     AppleScript sweep above only --flag-only-gmail (a label store: "move to All Mail" is a
#     no-op that Gmail re-asserts on next sync). gmail_imap_sweep.py drops the \Inbox label
#     via the X-GM-LABELS extension — a TRUE archive that sticks. Runs ONLY when the keyed
#     credential is hydrated (GMAIL_APP_PASSWORD + GMAIL_USER, from creds-hydrate); a no-op
#     otherwise. Reversible: drops only \Inbox (stays in All Mail), JSON receipt = undo
#     manifest, starred/protected-sender gated. NEVER deletes, NEVER sends. Opt out with
#     LIMEN_MAIL_GMAIL_ARCHIVE=0.
if [ "${LIMEN_MAIL_SWEEP:-1}" = "1" ] && [ "${LIMEN_MAIL_GMAIL_ARCHIVE:-1}" = "1" ]; then
  [ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; }
  if [ -n "${GMAIL_APP_PASSWORD:-}" ] && [ -n "${GMAIL_USER:-}" ]; then
    IMAP_USER="$GMAIL_USER" IMAP_PASS="$GMAIL_APP_PASSWORD" \
      run_tmp 240 "$PY" "$UMA_ROOT/gmail_imap_sweep.py" --apply \
      --limit "$SWEEP_LIMIT" --receipt "$LIMEN_ROOT/logs/gmail-archive-latest.json"
  else
    echo "mail-beat: Gmail IMAP archive SKIPPED — GMAIL_APP_PASSWORD/GMAIL_USER not hydrated; the Gmail inbox will NOT auto-clean (creds-hydrate --verify flags this; root cause: op:// item unreadable by the service account, Wall #320)"
  fi
fi

# 1c) ARCHIVED-SCAN — surface archived-but-UNANSWERED threads the INBOX-only sweep can't see (a
#     reply owed on a thread that was archived drops out of the ledger silently). READ-ONLY +
#     count-first: it FLAGS/MOVES nothing, just writes a per-account receipt (audit/archived_scan-
#     *.json) that step 2's obligations_build folds in. Runs BEFORE the build so the receipt is
#     fresh. It's expensive (AppleScript over Archive + Sent), so exactly ONE account per beat,
#     round-robin via a persisted cursor — every account is covered over a full cycle without ever
#     fanning out. Independent of the mutation gate (read-only); gated by its own
#     LIMEN_MAIL_ARCHIVED_SCAN=1 (default on), fail-open, bounded. No grant / no accounts ⇒ skipped.
if [ "${LIMEN_MAIL_ARCHIVED_SCAN:-1}" = "1" ] && [ -f "$UMA_ROOT/archived_scan.py" ]; then
  scan_accts="$(bounded 20 osascript -e 'tell application "Mail" to get name of every account' 2>/dev/null || true)"
  if [ -n "$scan_accts" ]; then
    CURSOR_FILE="${LIMEN_MAIL_ARCHIVED_CURSOR:-$LIMEN_ROOT/logs/.mail-archived-scan-cursor}"
    OLDIFS="$IFS"; IFS=','; set -f
    ACCT_LIST=()
    for a in $scan_accts; do
      a="${a#"${a%%[![:space:]]*}"}"; a="${a%"${a##*[![:space:]]}"}"   # trim
      [ -z "$a" ] && continue
      ACCT_LIST+=("$a")
    done
    IFS="$OLDIFS"; set +f
    n="${#ACCT_LIST[@]}"
    if [ "$n" -gt 0 ]; then
      last="$(cat "$CURSOR_FILE" 2>/dev/null || echo -1)"
      case "$last" in ''|*[!0-9-]*) last=-1 ;; esac   # non-numeric cursor ⇒ restart the cycle
      next=$(( (last + 1) % n ))
      target="${ACCT_LIST[$next]}"
      printf '%s\n' "$next" > "$CURSOR_FILE" 2>/dev/null || true
      echo "mail-beat: archived-scan account $((next + 1))/$n — $target"
      run_tmp 240 "$PY" "$UMA_ROOT/archived_scan.py" --account "$target" --limit "${LIMEN_MAIL_ARCHIVED_LIMIT:-500}"
    fi
  fi
fi

# 2) BUILD the ledger from the receipts (keyless, derived, fail-open) — includes the
#    propose-mode unsubscribe noise-killers.
run_tmp 120 "$PY" "$UMA_ROOT/obligations_build.py" --out "$LEDGER"

# 2b) DRAFT — enrich reply-owed obligations with a voice-matched draft (NEVER sent).
#     Persist to Drafts only when LIMEN_MAIL_DRAFTS=1 (idempotent; needs the Automation
#     grant); else enrich-only so the ready draft is visible in the ledger/face without
#     touching the mailbox.
DRAFT_SAVE=""; [ "${LIMEN_MAIL_DRAFTS:-0}" = "1" ] && DRAFT_SAVE="--save"
# shellcheck disable=SC2086  # DRAFT_SAVE is an intentional optional single flag
run_tmp 180 "$PY" "$UMA_ROOT/draft_writer.py" --ledger "$LEDGER" $DRAFT_SAVE

# 2c) SEND — the tiered, fail-closed auto-send leaf (SAFE tier only, when armed). Ships DISARMED:
#     with LIMEN_MAIL_SEND unset, send_drafts.py DRY-RUNS (logs would-sends, sends nothing). Even
#     armed it sends only opt-in SAFE-tier obligations with complete bracket-free text, per the
#     declared mail-tiers.yaml registry — legal/money/personal HOLD is never sent. Guarded on the
#     file so the beat is safe before the live UMA checkout carries send_drafts.py.
if [ -f "$UMA_ROOT/send_drafts.py" ]; then
  run_tmp 120 "$PY" "$UMA_ROOT/send_drafts.py" --ledger "$LEDGER" --max "${LIMEN_MAIL_SEND_MAX:-10}" || true
fi

# 2d) WALK-TO-TERMINAL — stamp EVERY reply-owed obligation with a terminal disposition (the
#     correspondence organ's fixed-point driver; "never a one-off"). Reversible + fail-open: it
#     classifies with the SAME tier logic as SEND, composes held drafts, discovers a LinkedIn
#     reply path, and records dispositions to logs/correspondence-dispositions.json (counts-only)
#     + a sealed sidecar. It NEVER auto-sends HOLD — that invariant lives in send_drafts.py above;
#     a `held` row is terminal-for-the-beat (drafted, awaiting the operator's explicit keyed fire).
#     Guarded on the gate + file so the beat is safe before the script lands.
if [ "${LIMEN_CORRESPONDENCE_WALK:-1}" = "1" ] && [ -f "$LIMEN_ROOT/scripts/correspondence-walk.py" ]; then
  run_tmp 120 "$PY" "$LIMEN_ROOT/scripts/correspondence-walk.py" --drain --notify || true
fi

# 3) STATUS — refresh the read-only UMA mail-status receipt (feeds the beat MAIL: census line).
run_status || true

# 4) RENDER the pervasive faces (pure stdlib, no Mail I/O — short bound).
if [ -f "$LIMEN_ROOT/scripts/obligations-view.py" ]; then
  bounded 60 "$PY" "$LIMEN_ROOT/scripts/obligations-view.py" 2>&1 | tail -1 || true
fi
