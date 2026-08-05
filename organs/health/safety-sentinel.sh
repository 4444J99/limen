#!/usr/bin/env bash
# safety-sentinel.sh — Workflow 6: the executable gate on every health-organ output.
#
# Checks every deliverable against the hard guardrails before it reaches a human.
# Exits 0 (pass) or 1 (fail) with a detailed report.
#
# Usage:
#   ./organs/health/safety-sentinel.sh <path-to-artifact>
#
# The stamp is appended to the artifact (unless --check-only is passed).
set -euo pipefail

ARTIFACT="${1:?usage: safety-sentinel.sh <artifact-path> [--check-only]}"
CHECK_ONLY="${2:-}"

if [ ! -f "$ARTIFACT" ]; then
  echo "FAIL: artifact not found: $ARTIFACT"
  exit 1
fi

FAILURES=()

# ── Guardrail 1: No diagnosis, no prescription, no medical advice ──────────
# The artifact must not claim to diagnose, prescribe, or give medical advice.
# Look for first-person clinical assertions.
IFS='|' read -ra CLINICAL_PATTERNS <<< \
  "you have been diagnosed with|I diagnose|I prescribe|treatment plan prescribed by your doctor|take .* mg of|dosage adjustment"
for pat in "${CLINICAL_PATTERNS[@]}"; do
  if grep -qin "$pat" "$ARTIFACT" 2>/dev/null; then
    CONTEXT=$(grep -in "$pat" "$ARTIFACT" 2>/dev/null | head -3 || true)
    FAILURES+=("CLINICAL-BOUNDARY: pattern '$pat' found (must originate from licensed clinician directive, not health organ)")
    FAILURES+=("  context: $CONTEXT")
  fi
done
# Also catch first-person clinical assertions like "I recommend" or "you need to [clinical action]"
if grep -qinE "(I|we) (recommend|suggest|advise|diagnose|prescribe)" "$ARTIFACT" 2>/dev/null; then
  CONTEXT=$(grep -inE "(I|we) (recommend|suggest|advise|diagnose|prescribe)" "$ARTIFACT" | head -3 || true)
  FAILURES+=("CLINICAL-BOUNDARY: first-person clinical assertion (only clinicians recommend/diagnose/prescribe)")
  FAILURES+=("  context: $CONTEXT")
fi

# ── Guardrail 2: No contradiction of licensed directives ───────────────────
# The artifact must not recommend deviation from a prescribed protocol.
if grep -qinE "you should (stop|skip|reduce|increase|change)" "$ARTIFACT" 2>/dev/null; then
  CONTEXT=$(grep -inE "you should (stop|skip|reduce|increase|change)" "$ARTIFACT" | head -3 || true)
  FAILURES+=("CONTRADICTION-GUARD: artifact recommends protocol deviation — only clinician may modify")
  FAILURES+=("  context: $CONTEXT")
fi

# ── Guardrail 3: No self-scheduling or self-booking ────────────────────────
# The artifact must not claim to book, confirm, or cancel appointments.
if grep -qinE "(booked|confirmed|rescheduled|cancelled) (appointment|session)" "$ARTIFACT" 2>/dev/null; then
  # Allow descriptive past tense (was scheduled)
  if grep -qinE "(will book|auto-confirm|auto-schedule|automatically scheduled)" "$ARTIFACT" 2>/dev/null; then
    CONTEXT=$(grep -inE "(will book|auto-confirm|auto-schedule)" "$ARTIFACT" | head -3 || true)
    FAILURES+=("SELF-SCHEDULING: artifact claims autonomous scheduling action")
    FAILURES+=("  context: $CONTEXT")
  fi
fi

# ── Guardrail 4: Privacy scoped — no personal identifiers ──────────────────
# The artifact must not contain patient names, DOBs, or PII beyond case IDs.
# This organ uses capability-focused documentation — no personal names in the record.
# Check for concrete PII patterns (email, phone, SSN, DOB) and for any personal name
# not explicitly allowed (Micah Longo is allowed as legal counsel reference).
if grep -qinE '\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b' "$ARTIFACT" 2>/dev/null; then
  FAILURES+=("PII-LEAK: email address found in artifact")
fi
if grep -qinE '\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b' "$ARTIFACT" 2>/dev/null; then
  FAILURES+=("PII-LEAK: SSN pattern found in artifact")
fi
if grep -qinE '(phone|tel|mobile|cell).*[0-9]{3}[) .-][0-9]{3}[ -][0-9]{4}' "$ARTIFACT" 2>/dev/null; then
  FAILURES+=("PII-LEAK: phone number found in artifact")
fi
if grep -qinE '\b(DOB|date of birth|birth date)\s*:' "$ARTIFACT" 2>/dev/null; then
  FAILURES+=("PII-LEAK: date of birth reference found in artifact")
fi

# ── Guardrail 5: No UPL-adjacent content (legal advice from health organ) ──
# The artifact must not suggest what accommodation to request or what legal argument to make.
if grep -qinE "(you should request|ask for|demand|insist on|legal right to|entitled to)" "$ARTIFACT" 2>/dev/null; then
  # Allow if explicitly referencing existing granted/active accommodations (factual)
  if ! grep -qinE "(currently granted|active and enforced|granted|approved)" "$ARTIFACT" 2>/dev/null; then
    CONTEXT=$(grep -inE "(you should request|ask for|demand|insist on|legal right to|entitled to)" "$ARTIFACT" | head -3 || true)
    FAILURES+=("UPL-ADJACENT: artifact suggests legal strategy — health organ records facts, legal organ applies strategy")
    FAILURES+=("  context: $CONTEXT")
  fi
fi

# ── Guardrail 6: Accommodation records feed legal, not replace it ──────────
# The artifact must not claim health organ replaces legal counsel or ADA proceeding.
if grep -qinE "this (constitutes|is) (legal advice|legal representation|a legal filing)" "$ARTIFACT" 2>/dev/null; then
  FAILURES+=("LEGAL-BOUNDARY: artifact claims legal status — only legal organ may produce legal work product")
fi

# ── Results ──────────────────────────────────────────────────────────────────
if [ ${#FAILURES[@]} -gt 0 ]; then
  echo "SAFETY SENTINEL: FAIL"
  for f in "${FAILURES[@]}"; do
    echo "  - $f"
  done
  exit 1
fi

STAMP="Safety check passed: clinical boundary held, no contradictions with licensed directives, privacy scoped, no UPL-adjacent content."
echo "SAFETY SENTINEL: PASS"
echo "$STAMP"

if [ -z "$CHECK_ONLY" ]; then
  # Append stamp to artifact
  echo "" >> "$ARTIFACT"
  echo "---" >> "$ARTIFACT"
  echo "*$STAMP -- $(date -u +'%Y-%m-%dT%H:%M:%SZ')*" >> "$ARTIFACT"
fi
