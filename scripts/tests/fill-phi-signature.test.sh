#!/usr/bin/env bash
# fill-phi-signature.test.sh — the signature artifact auto-fills the sig line, or falls back to a blank.
#
# Branch-2 of the identity organ: identity.signature.image (applicable:true, required:false) lets a
# form embed the operator's homed signature instead of a hand-sign blank — retiring the last human
# step of the phi.pdf fill. This guards the resolver's three states (embedded / absent / missing_file)
# and that the image becomes an inline base64 data URI — WITHOUT invoking Chrome, so it runs in CI
# where no browser exists. The image bytes never leave the transient render (never chat/log).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
fill="$here/../fill-phi-jewishboard.py"
[ -f "$fill" ] || { echo "FAIL: cannot find fill-phi-jewishboard.py at $fill" >&2; exit 1; }

python3 - "$fill" <<'PY'
import base64, importlib.util, os, sys, tempfile

spec = importlib.util.spec_from_file_location("fillphi", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

fails = []
def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

# absent: no signature in the store -> hand-sign fallback
uri, st = m.signature_data_uri({})
check(uri == "" and st == "absent", "absent when no signature.image_path is homed")

# missing_file: path homed but file gone -> surfaced, not silently embedded
uri, st = m.signature_data_uri({"signature": {"image_path": "/definitely/not/here.png"}})
check(uri == "" and st == "missing_file", "missing_file when the homed path does not resolve")

# embedded: a real image becomes an inline base64 data URI
work = tempfile.mkdtemp()
png = os.path.join(work, "sig.png")
onexone = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII=")
open(png, "wb").write(onexone)
uri, st = m.signature_data_uri({"signature": {"image_path": png}})
check(st == "embedded" and uri.startswith("data:image/png;base64,"),
      "embedded as a data URI when the image resolves")

# build_fields propagates the resolved artifact into the field set
D = m.build_fields({"signature": {"image_path": png}, "legal_name": {"first": "A", "last": "B"}})
check(D.get("sig_status") == "embedded" and D.get("sig_img", "").startswith("data:image/png"),
      "build_fields carries the embedded signature into the field set")

# absent path: build_fields yields no image (the form renders a hand-sign blank)
D2 = m.build_fields({"legal_name": {"first": "A", "last": "B"}})
check(D2.get("sig_status") == "absent" and not D2.get("sig_img"),
      "build_fields yields no image when the signature is not homed (hand-sign fallback)")

sys.exit(1 if fails else 0)
PY

# Live-contract guard: the registry must still home the signature class WITH the filler as consumer.
real_reg="$here/../../institutio/governance/personal-facts.yaml"
python3 - "$real_reg" <<'PY'
import sys, yaml
sig = (yaml.safe_load(open(sys.argv[1])) or {}).get("facts", {}).get("identity.signature.image", {})
assert sig.get("applicable") is True, "identity.signature.image must be applicable:true (wired)"
assert "fill-phi-jewishboard.py" in (sig.get("consumers") or []), "filler dropped as a signature consumer"
PY
echo "ok   live personal-facts.yaml homes identity.signature.image with the filler as consumer"
echo "fill-phi-signature.test.sh: passed"
