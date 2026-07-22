#!/usr/bin/env bash
# Constellation program done-predicate. Exit 0 ⟺ the program is done:
# valid register, every protocol PROVEN-shaped, the CONST- DAG fully seeded,
# every dossier-stage project carrying both dossier halves, and no PII on any
# touched public surface. Idempotent — a re-run performs no writes.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

C=organs/consulting/constellation

echo "── registry ──"
python3 "$C/validate-constellation.py" --quiet

echo "── protocols (all 9) ──"
fail=0
for slug in maddie jessica rob charles scott ari dustin david john-m; do
  "$C/check.py" proto "$slug" || fail=1
done

echo "── board DAG ──"
"$C/seed-tasks.py" --check || fail=1

echo "── dossiers (every project at stage>=dossier) ──"
python3 - "$C/registry.yaml" <<'EOF' || fail=1
import subprocess, sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
ranked = ["idea", "dossier", "building", "mvp", "live", "funnelized"]
bad = 0
for person in doc.get("people") or []:
    for row in person.get("projects") or []:
        if ranked.index(row.get("stage", "idea")) >= 1 and row.get("dossier"):
            rc = subprocess.run(
                ["organs/consulting/constellation/check.py", "dossier", person["slug"], row["name"]]
            ).returncode
            bad += 1 if rc else 0
sys.exit(1 if bad else 0)
EOF

echo "── public-surface sweep (touched public repos) ──"
python3 - "$C/registry.yaml" <<'EOF' || fail=1
import subprocess, sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
bad = 0
for person in doc.get("people") or []:
    for row in person.get("projects") or []:
        repo = row.get("repo")
        if repo and row.get("public_face_state") not in (None, "none", "pending-split"):
            rc = subprocess.run(
                [sys.executable, "scripts/publish-sweep.py", "--repo", repo]
            ).returncode
            bad += 1 if rc else 0
sys.exit(1 if bad else 0)
EOF

if [ "$fail" -ne 0 ]; then
  echo "CONSTELLATION: NOT DONE"
  exit 1
fi
echo "CONSTELLATION: DONE — register valid, protocols proven, DAG seeded, dossiers landed, surfaces clean"
