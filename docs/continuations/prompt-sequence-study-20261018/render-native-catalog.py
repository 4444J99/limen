"""Build a private catalog; transcript text is only inserted with textContent."""

import json
import html
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
PRIVATE = REPO / ".limen-private/prompt-sequence-study"
stream = json.loads((PRIVATE / "native-stream-v3-0000.json").read_text())
manual = json.loads((PRIVATE / "native-archive-snapshot.json").read_text())
notes = json.loads((BASE / "native-sequence-review.json").read_text())
bindings = {s["path"]: (s, n) for s, n in zip(manual["sessions"], notes["sequences"])}
excluded = {
    "01a14e66-dd33-79d2-8b81-fccbda7c8c2d",
    "01a14eab-8da4-71d1-bdf0-9aacde1c07a7",
    "01a14e44-df56-74d3-aad4-c4356be5694a",
}
sessions = []
for session in stream["sessions"]:
    if session["id"] in excluded:
        continue
    if session["path"] in bindings:
        source, review = bindings[session["path"]]
        assert source["source_sha256"] == session["decompressed_sha256"]
        assert [p["line"] for p in source["prompts"]] == [p["line"] for p in session["prompts"]]
        session["alias"] = review["sequence"]
        session["annotations"] = [p["candidate"] for p in review["followup_candidates"]]
    sessions.append(session)
cross = json.loads((PRIVATE / "cross-provider-bindings.json").read_text())
for entry in cross:
    if entry["alias"] == "C1":
        session = json.loads((PRIVATE / "claude-ghostty-native.json").read_text())
        assert session["source_sha256"] == entry["source_sha256"]
        session["alias"] = entry["alias"]
        session["annotations"] = entry["labels"]
        sessions.append(session)
    else:
        session = next(s for s in sessions if s["path"] == entry["path"])
        assert session["decompressed_sha256"] == entry["decompressed_sha256"]
        session["alias"] = entry["alias"]
        session["annotations"] = entry["labels"]
payload = (
    json.dumps({"sessions": sessions}, ensure_ascii=True)
    .replace("<", "\\u003c")
    .replace(">", "\\u003e")
    .replace("&", "\\u0026")
)
script = (BASE / "native-catalog.js").read_text()
proof = json.loads((PRIVATE / "native-readback-bindings-v1.json").read_text())
managed = next(entry for entry in proof["threads"] if entry["alias"] == "U3")
positions = sorted(int(entry["case"].split(".")[1]) for entry in proof["recovery_records"])
assert positions == [5, 6, 7, 8, 9, 10]
source_notes = [{"id": managed["id"], "alias": "U3", "positions": positions,
                 "label": "Managed recovery input; excluded from operator-intent evidence; original retained verbatim."}]
overlay = (BASE / "catalog-source-notes.js").read_text().replace(
    "__SOURCE_NOTES__", json.dumps(source_notes).replace("<", "\\u003c")
    .replace(">", "\\u003e").replace("&", "\\u0026"))
script = script.replace("const picker =", overlay + "const picker =", 1)
lineage_public = json.loads((BASE / "native-prefix-census-v1.json").read_text())
lineage_private = json.loads((PRIVATE / "native-prefix-census-bindings-v1.json").read_text())
lineage_bindings = {entry["alias"]: entry for entry in lineage_private["rows"]}
assert set(lineage_bindings) == {entry["source_alias"] for entry in lineage_public["rows"]}
lineage_rows = [
    {"alias": entry["source_alias"], "parent_alias": entry["declared_parent_alias"],
     "parent_id": lineage_bindings[entry["source_alias"]]["metadata"].get("forked_from_id"),
     "local_line": entry["first_local_candidate_source_line"],
     "reader_positions": entry["reader_user_positions_in_same_turn"],
     "attribution": entry["attribution"], "body_match": entry["prompt_body_matches"]}
    for entry in lineage_public["rows"]
]
lineage_payload = json.dumps({"rows": lineage_rows}, indent=2).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
lineage_script = (BASE / "catalog-lineage.js").read_text().replace("__LINEAGE_DATA__", lineage_payload)
script = script.replace("const picker =", lineage_script + "const picker =", 1)
page = (
    """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>Native session prompt catalog</title>
<style>
:root{font:16px/1.5 system-ui;background:#111720;color:#edf2f7;color-scheme:dark}
body{margin:0;padding:24px}h1{font-size:30px;margin:0}p{max-width:1000px}
.controls{display:flex;gap:16px;align-items:center;flex-wrap:wrap;padding:16px;background:#202c3e;border-radius:10px}
input,select,button{font:inherit;padding:8px;border-radius:5px}select{width:min(850px,90vw)}
#board{display:flex;gap:14px;overflow:auto;align-items:flex-start;max-height:75vh;padding:16px 0}
article{flex:0 0 390px;border:1px solid #536681;border-radius:8px;background:#182333}
header{padding:14px;background:#25344b}header p,small{font-size:12px;overflow-wrap:anywhere}
h2{font-size:19px;margin:0}ol{padding:0 16px 0 38px}li{padding:16px 0;border-bottom:1px solid #435572}
strong{color:#8ee4c2}pre{font:13px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto}
.meta{font-size:12px;color:#bac9dd}summary{cursor:pointer}.warning{border-left:4px solid #edc46f;padding:12px;background:#202c3e}
#lineage{overflow:auto;max-height:340px}#lineage table{border-collapse:collapse;min-width:760px;font-size:12px}#lineage th,#lineage td{padding:8px;text-align:left;border-bottom:1px solid #435572}#lineage-panel{margin:14px 0;padding:12px;background:#202c3e;border-radius:8px}
</style><h1>Native prompts, one file sequence per column</h1>
<p>Choose whole sequences to compare. Every captured prompt stays in order; filtering selects sessions, never individual turns. Select all matching sequences to place the entire captured set next to one another.</p>
<p class="warning">All 509 direct-session candidate files were visited. 383 yielded multi-prompt captures; 100 had fewer than two candidate prompts; 26 exceeded explicit per-file or per-record bounds. The raw snapshot contains 3,496 prompt rows. This view excludes this study and its two related study sessions to avoid circular evidence. Retention, attachments, forks, resumed history and original openers still require reconciliation. The catalog also includes one independently read Claude source file with 11 prompts. Most follow-ups remain uncoded; 78 follow-ups across 20 file sequences have contextual annotations. This includes a frozen nine-sequence, 27-follow-up source holdout assessed by one coder; four authority-sensitive requests remain unresolved as bare controls. This is not blind independent validation. Native turn IDs now bind replies; shared turns and unbound adjacency remain visible. Derived frames are retained separately. No installed commands or complete-corpus equivalence is claimed.</p>
<div class="controls"><label>Find a session <input id="search" placeholder="Directory, session ID or opener"></label>
<select multiple size="6" id="picker" aria-label="Native file sequences"></select>
<button id="compare">Compare selected</button><button id="all">Compare all matching</button></div>
<details id="lineage-panel"><summary>Native view lineage and parent context</summary><div id="lineage"></div></details>
<p id="selection" aria-live="polite"></p><main id="board" aria-label="Side-by-side native sequences"></main>
<script type="application/json" id="dataset">"""
    + payload
    + "</script><script>"
    + script
    + "</script></html>"
)
vocabulary = json.loads((BASE / "vocabulary-v2.json").read_text())
glossary = "<details><summary>18 candidate operations and their contracts</summary><ul>"
for command in vocabulary["commands"]:
    glossary += "<li><strong>" + html.escape(command["name"]) + "</strong> — " + html.escape(command["operation"])
    glossary += (
        "<p>"
        + html.escape(command["target_and_payload"])
        + "</p><p class='meta'>"
        + html.escape(command["authority_and_constraints"])
        + "</p></li>"
    )
glossary += "</ul><p>These contracts are provisional and are not installed commands.</p></details>"
page = page.replace('<div class="controls">', glossary + '<div class="controls">')
current = json.loads((BASE / "vocabulary-v5.json").read_text())
current_glossary = '<details id="current-vocabulary"><summary>21 proposed operator commands (V5)</summary><dl>\n'
for command in current["commands"]:
    current_glossary += (
        "<dt><code>" + html.escape(command["name"]) + "</code> — "
        + html.escape(command["operation"]) + "</dt><dd>"
        + html.escape(command["target_and_payload"]) + '<p class="meta">'
        + html.escape(command["authority_and_constraints"]) + "</p><p>"
        + html.escape(command["completion_evidence"]) + "</p></dd>\n"
    )
current_glossary += (
    "</dl><p>Provisional research contracts; no installed commands or independent substitution validation. "
    "Six managed recovery inputs are retained and excluded from operator-intent evidence.</p></details>\n"
    '<p class="meta">The 18-operation glossary below is the frozen V2 evaluation baseline, '
    "superseded for current proposal review.</p>\n"
)
page = page.replace("<p>Choose whole sequences", current_glossary + "<p>Choose whole sequences", 1)
destination = PRIVATE / "native-catalog.html"
destination.write_text(page)
destination.chmod(0o600)
print(
    json.dumps(
        {
            "artifact": str(destination),
            "captured_file_columns": len(sessions),
            "prompt_rows": sum(len(s["prompts"]) for s in sessions),
            "excluded_study_file_sequences": len(stream["sessions"]) - (len(sessions) - 1),
        }
    )
)
