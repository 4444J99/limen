#!/usr/bin/env python3
"""Fill The Jewish Board 'Client's Request for His/Her Own PHI' form from the identity organ.

A CONSUMER of the core-identity store: it reads scripts/identity.py, maps atoms onto the
form, and renders a clean PDF via Chrome headless. The source form is a flat scan (no AcroForm
fields), so we recreate the layout rather than overlay text.

  fill-phi-jewishboard.py OUT.pdf                 # fill from the store; blanks stay blank
  fill-phi-jewishboard.py OUT.pdf --draft         # highlight still-missing atoms in yellow

Any field the store lacks renders as an underlined blank to hand-write. Once the store is
populated (identity.py verify -> exit 0), the PDF is complete with no blanks.
"""
import json
import sys
import subprocess
import os
import html
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# The personal-fact classes this form reads. fact-wall.py asserts every entry is a homed row in
# institutio/governance/personal-facts.yaml — so an un-homed atom is a RED build, never a chat ask.
CONSUMES = [
    "identity.legal_name.first",
    "identity.legal_name.middle",
    "identity.legal_name.last",
    "identity.dob",
    "identity.addresses.0.street",
    "identity.addresses.0.city",
    "identity.addresses.0.state",
    "identity.addresses.0.zip",
    "identity.phones.0.number",
    "identity.emails",
]

def load_identity():
    """Read the identity store via the organ (form-filler is allowed the full record)."""
    out = subprocess.run([sys.executable, os.path.join(HERE, "identity.py"), "json", "--unsafe-ssn"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    return json.loads(out.stdout)

def build_fields(idn):
    name = idn.get("legal_name", {})
    addr = (idn.get("addresses") or [{}])[0]
    phone = (idn.get("phones") or [{}])[0].get("number", "")
    return {
        "first":  name.get("first", ""),
        "middle": (name.get("middle", "")[:1] if name.get("middle") else ""),
        "last":   name.get("last", ""),
        "dob":    idn.get("dob", ""),
        "phone":  phone,
        "street": " ".join(x for x in [addr.get("street", ""), addr.get("unit", "")] if x),
        "city":   addr.get("city", ""),
        "state":  addr.get("state", ""),
        "zip":    addr.get("zip", ""),
        # sensible reversible defaults:
        "records_other": "My complete health / mental-health record (entire chart), all dates of service.",
        "delivery_email": (idn.get("emails") or [""])[0] + " (PDF by secure email)",
        "sig_date": datetime.date.today().strftime("%m/%d/%Y"),
    }

def render(D, out, draft=False):
    def v(key, blank_len=32, need=False):
        val = D.get(key, "")
        if val:
            return f'<span class="val">{html.escape(str(val))}</span>'
        cls = "blank need" if (need and draft) else "blank"
        return f'<span class="{cls}">{"&nbsp;"*blank_len}</span>'
    def box(c):
        return '<span class="cbx checked">&#9746;</span>' if c else '<span class="cbx">&#9744;</span>'
    other = D.get("records_other", ""); email = D.get("delivery_email", "")
    hf, ht = D.get("health_from", ""), D.get("health_through", "")
    HTML = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: Letter; margin: 0.75in 0.9in; }}
* {{ box-sizing: border-box; }}
body {{ font-family:'Helvetica Neue',Arial,sans-serif; font-size:11.3pt; color:#111; line-height:1.75; }}
.brand {{ font-weight:700; font-size:15pt; }}
.brand .sub {{ display:block; font-weight:600; font-size:6.8pt; letter-spacing:.3px; margin-top:1px; }}
h1 {{ font-size:12pt; text-align:center; margin:20px 0 16px; }}
.sec {{ font-weight:700; margin:11px 0 5px; }}
.val {{ font-weight:600; border-bottom:1px solid #111; padding:0 6px; white-space:pre; }}
.blank {{ border-bottom:1px solid #111; padding:0 4px; }}
.need {{ background:#fff3b0; }}
.cbx {{ font-size:13pt; vertical-align:-1px; }}
.row {{ margin:2px 0; }}
.intbox {{ border:1px solid #111; padding:9px 12px; margin-top:20px; }}
.intbox .sec {{ margin-top:0; }}
.rev {{ text-align:right; font-style:italic; font-size:8.5pt; color:#333; margin-top:20px; }}
</style></head><body>
<div class="brand">The Jewish Board<span class="sub">HEALTH AND HUMAN SERVICES FOR ALL NEW YORKERS</span></div>
<h1>Jewish Board Client&rsquo;s Request for His/Her Own Protected Health Information</h1>
<div class="sec">Client Information (Please Print):</div>
<div class="row">First Name: {v('first')} &nbsp; Middle Initial: {v('middle',6)} &nbsp; Last Name: {v('last')}</div>
<div class="row">Date of Birth (MM/DD/YYYY): {v('dob',16,need=True)} &nbsp; Phone: {v('phone',22,need=True)}</div>
<div class="row">Street Address: {v('street',30,need=True)} City: {v('city',14,need=True)} State: {v('state',6,need=True)} Zip: {v('zip',8,need=True)}</div>
<div class="sec">What records are you requesting? (Check appropriate boxes below):</div>
<div class="row">{box(bool(hf or ht))} Health Record from: {v('health_from',10)} through {v('health_through',10)}</div>
<div class="row">{box(bool(other))} Other: Please specify: {('<span class="val">'+html.escape(other)+'</span>') if other else v('_o',60)}</div>
<div class="sec">How would you like your records delivered?</div>
<div class="row">Paper</div>
<div class="row" style="margin-left:28px">{box(D.get('home_delivery'))} Home Delivery (include address): {v('home_addr',34)}</div>
<div class="row" style="margin-left:28px">{box(D.get('in_person'))} In-Person Pickup</div>
<div class="row">Electronic (Email, CD) please specify: {('<span class="val">'+html.escape(email)+'</span>') if email else v('_e',40)}</div>
<div class="row" style="margin-top:22px">Signature of client and/or personal representative {v('_sig',30)} Date: {v('sig_date',12)}</div>
<div class="intbox">
<div class="sec">Internal Use Only:</div>
<div class="row">Client Medical Record #: {v('_mrn',24)}</div>
<div class="row">JB Program Name: {v('_prog',30)}</div>
<div class="row">Name of JB staff that processed the client&rsquo;s request</div>
<div class="row">(print): {v('_staff',30)} Date: {v('_sdate',14)}</div>
</div>
<div class="rev">Rev. 8.6.18 JKS</div>
</body></html>"""
    hp = out.replace(".pdf", ".html")
    open(hp, "w").write(HTML)
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", "file://" + os.path.abspath(hp)],
                   check=True, capture_output=True)
    os.remove(hp)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--draft", action="store_true", help="highlight missing atoms in yellow")
    a = ap.parse_args()
    D = build_fields(load_identity())
    render(D, a.out, draft=a.draft)
    missing = [k for k in ("dob", "phone", "street", "city", "state", "zip") if not D.get(k)]
    print("wrote", a.out)
    if missing:
        print("still-blank (populate the identity store to auto-fill):", ", ".join(missing))

if __name__ == "__main__":
    main()
