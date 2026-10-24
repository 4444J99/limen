"""Render full captured prompt sequences privately; public annotations contain no raw bodies."""

import hashlib
import html
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
PRIVATE = REPO / ".limen-private/prompt-sequence-study"
snapshot = json.loads((PRIVATE / "native-archive-snapshot.json").read_text())
review = json.loads((BASE / "native-sequence-review.json").read_text())
bindings = json.loads((PRIVATE / "annotation-bindings.json").read_text())
assert len(snapshot["sessions"]) == len(review["sequences"]) == len(bindings)
for session, binding in zip(snapshot["sessions"], bindings):
    assert session["id"] == binding["session_id"], "review session binding changed"
    assert session["source_sha256"] == binding["source_sha256"], "review source binding changed"
    assert [p["line"] for p in session["prompts"]] == binding["prompt_lines"], "review positions changed"
    assert hashlib.sha256(Path(session["path"]).read_bytes()).hexdigest() == session["source_sha256"], (
        "native source changed"
    )

escape = html.escape
headers = []
body = []
for i, (session, notes) in enumerate(zip(snapshot["sessions"], review["sequences"])):
    assert len(session["prompts"]) == notes["captured_prompts"]
    mark = "body-complete" if notes["all_prompt_bodies_marked_complete"] else "incomplete body"
    headers.append(
        "<th>"
        + escape(notes["sequence"] + " | " + mark)
        + "<p>"
        + escape(str(session["cwd"]))
        + "</p><small>"
        + escape(session["id"])
        + "</small></th>"
    )
for position in range(max(len(s["prompts"]) for s in snapshot["sessions"])):
    cells = []
    for session, notes in zip(snapshot["sessions"], review["sequences"]):
        if position >= len(session["prompts"]):
            cells.append("<td class='empty'>End of captured sequence</td>")
            continue
        prompt = session["prompts"][position]
        label = (
            "FIRST RETAINED PROMPT — opener candidate"
            if position == 0
            else notes["followup_candidates"][position - 1]["candidate"]
        )
        completeness = (
            "Complete retained body"
            if prompt["retained_complete"] is True
            else "INCOMPLETE RETAINED BODY"
            if prompt["retained_complete"] is False
            else "Body completeness unknown"
        )
        cell = "<td><strong>" + escape(label) + "</strong><p class='status'>" + completeness
        cell += " | native line " + str(prompt["line"]) + "</p>"
        cell += "<details open><summary>Original prompt (" + str(len(prompt["text"])) + " characters)</summary>"
        cell += "<pre>" + escape(prompt["text"]) + "</pre></details>"
        if prompt["media"]:
            cell += "<p>Media blocks retained as descriptors only: " + escape(str(prompt["media"])) + "</p>"
        cell += "<details><summary>Recorded replies (" + str(len(prompt["finals"])) + ") and actions</summary>"
        cell += (
            "<p>Historical assistant claims; not current verification. Tool invocations: "
            + str(prompt["tool_calls"])
            + "</p>"
        )
        for reply in prompt["finals"]:
            cell += "<pre>" + escape(reply["text"]) + "</pre>"
        cell += "</details></td>"
        cells.append(cell)
    body.append("<tr><th scope='row'>" + str(position + 1) + "</th>" + "".join(cells) + "</tr>")
findings = "".join(
    "<li>" + escape(f["claim"]) + " <strong>" + escape(", ".join(f["evidence"])) + "</strong></li>"
    for f in review["findings"]
)
page = (
    """<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Native prompt sequences | side-by-side review</title>
<style>
:root{color-scheme:light dark;font:16px/1.5 system-ui;background:#111720;color:#edf2f7}
body{margin:0;padding:28px}h1{font-size:32px;letter-spacing:-.7px;margin:0}
.lead{max-width:1000px;color:#bfcddd}.banner{padding:16px;border:1px solid #72839c;border-radius:10px;background:#202b3b}
.board{overflow:auto;max-height:76vh;margin:24px 0;border:1px solid #54647c;border-radius:10px}
table{border-collapse:separate;border-spacing:0;table-layout:fixed;width:max-content}
th,td{vertical-align:top;border-right:1px solid #394963;border-bottom:1px solid #394963;padding:14px;width:350px;min-width:350px}
thead th{position:sticky;top:0;background:#25334a;z-index:2;text-align:left}
th:first-child{width:34px;min-width:34px;position:sticky;left:0;background:#25334a;z-index:3}
p{margin:8px 0}th p,small,.status{font-size:12px;overflow-wrap:anywhere;color:#bfcddd}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.55 ui-monospace,monospace;max-height:360px;overflow:auto;background:#182333;padding:12px;border-radius:6px}
strong{color:#8ee4c2}summary{cursor:pointer;font-size:13px}.empty{color:#8695a9}li{margin:10px 0}
a{color:#9cc7ff}
</style><main><h1>One session per column. Every captured prompt in order.</h1>
<p class="lead">A native Codex archive tranche for studying equivalent intentions after the opener.
Read across to compare sessions; read down to preserve each session's context. Scroll horizontally for all eight columns.</p>
<div class="banner"><strong>Evidence boundary</strong><p>8 captured sequences, 43 candidate operator prompts,
35 post-opener prompts. Only 3 sequences mark every retained prompt body complete.
“Body-complete” does not prove that an entire logical session, its forks, attachments, or prior resumed history is present.
No command substitution has yet been experimentally validated.</p>
<p>The scan read 43 of 180 uncompressed archive files, bounded to 64 MiB and 8 MiB per file.
Compressed archive units and other providers are outside this tranche. Harness context and expanded skill bodies are listed separately in the private snapshot.
Payloads remain private; this page makes no network requests.</p></div>
<h2>Findings to test</h2><ul>"""
    + findings
    + "</ul><div class='board'><table><thead><tr><th>#</th>"
    + "".join(headers)
    + "</tr></thead><tbody>"
    + "".join(body)
    + "</tbody></table></div><p>Candidate syntax is a review annotation, not installed behavior. The first retained prompt stays as content. Its status as the original logical-session opener still requires lineage reconciliation.</p></main></html>"
)
PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
destination = PRIVATE / "native-sequences.html"
destination.write_text(page)
destination.chmod(0o600)
print(
    json.dumps(
        {
            "artifact": str(destination),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "sequence_columns": len(headers),
            "prompt_rows": len(body),
            "full_prompt_cells": sum(len(s["prompts"]) for s in snapshot["sessions"]),
        }
    )
)
