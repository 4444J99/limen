#!/usr/bin/env python3
"""Read-only native prompt study; outputs private review caches, never source mutations."""

import argparse
import collections
import hashlib
import json
import os
import re
import time
from pathlib import Path


def body(record):
    value = record.get("message", {}).get("content", "")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for part in value:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                parts.append(part.get("text", ""))
            elif part.get("type") in ("image", "document"):
                parts.append("[attachment: " + part["type"] + "; binary not reproduced]")
        return "\n".join(parts)
    return ""


def normalized(text):
    # Only an entire native wrapper may be normalized. Markup quoted inside an
    # ordinary request must not erase its surrounding constraints.
    tags = list(re.finditer(r"<(command-name|command-message|command-args)>(.*?)</\1>", text, re.DOTALL))
    remainder = re.sub(r"<(command-name|command-message|command-args)>.*?</\1>", "", text, flags=re.DOTALL)
    names = [m[2].strip() for m in tags if m[1] == "command-name"]
    args = [m[2].strip() for m in tags if m[1] == "command-args"]
    if (
        not remainder.strip()
        and len(names) == 1
        and len(args) <= 1
        and re.fullmatch(r"/[a-zA-Z][a-zA-Z0-9_:-]*", names[0])
    ):
        return names[0] + (" " + args[0] if args and args[0] else "")
    return text.strip()


def candidate(text, index):
    if index == 0:
        return "OPENER", "", "Keep the initial scope in full."
    t = text.lower().strip()
    if re.match(r"^/[a-zA-Z][a-zA-Z0-9_:-]*(?:\s|$)", t):
        return "EXISTING", text.split()[0], "Existing command; arguments retained, behavior not validated here."
    if t.startswith("!") or "<bash-input>" in t:
        return "SHELL", "", "Keep exact shell payload and its authority."
    if len(text) > 600 or "<pasted_content" in t:
        cmd = "/fix <payload>" if re.match(r"^(address|solve|heal|debug|fix|repair)\b", t) else ""
        return (
            "PAYLOAD",
            cmd,
            "Long or pasted material: no keyword classification of the quoted body. Preserve payload and authority.",
        )
    if re.match(r"^merge and apply", t):
        return "COMPOUND", "/ship + /apply", "Two authorized effects; retain the selected target and order."
    if re.match(r"^apply it", t):
        return "APPLY", "/apply", "Apply the selected change; merging is a separate effect."
    if re.search(r"safe to archive|are we done|anything (left|hanging)|what (is left|remains)", t):
        return "CLOSURE_CHECK", "/verify closure", "Question about closure; does not itself archive or delete anything."
    tests = [
        (
            "CORRECTION",
            "/correct",
            r"^(again |no\b|no--|wrong\b|once again|i (never|already|said|asked|told)|you (didn.t|did not|keep|never)|this isn.t a closeout)|closeout means|leaving shit|why (did|are|do) you",
        ),
        ("CLOSE", "/closeout", r"safe to archive|are we done|anything (left|hanging)|what remains|close.?out"),
        (
            "STATUS",
            "/status",
            r"status|percentage|what.s (going on|merged)|what has been|are all.*merged|why.*(long|nothing|slow)|progress",
        ),
        (
            "VERIFY",
            "/verify",
            r"you reviewed|verif|check|all.*(findings|patched|repaired|healed|addressed)|anything strange",
        ),
        ("EXPLAIN", "/tldr", r"what is |tldr|eli5|explain|what do i need to do|how do i proceed"),
        (
            "NEXT",
            "/next",
            r"any settings.*worth|what.?s next|where do we go|ideal form|alpha to omega|root to leaf|salve to heal",
        ),
        ("SHIP", "/ship", r"^merge\b|^ship\b|merge (it|them|the stack)"),
        ("CODIFY", "/codify", r"codif|make.*hook|ever happening again"),
        ("REPAIR", "/fix", r"^(address|solve|heal|debug|fix|repair)\b"),
        ("REPORT", "/report", r"full report|report of all work"),
        (
            "CONTINUE",
            "/continue",
            r"^(continue|cont|proceed|go|keep going|yes|full go|do it|you do it|execute|implement the following plan|get it there|option [0-9])\b",
        ),
        ("RESOURCE", "/delegate", r"spawn|teammate|subagent|haiku|sonnet|token usage"),
    ]
    matches = [(a, b) for a, b, pattern in tests if re.search(pattern, t)]
    if len(matches) > 1:
        return (
            "COMPOUND",
            " + ".join(dict.fromkeys(b for a, b in matches)),
            "Multiple matches: preserve clauses; human semantic review required.",
        )
    if matches:
        a, b = matches[0]
        return a, b, "Provisional lexical suggestion; target, qualifiers and payload must remain."
    return "CONTENT", "", "New content or unresolved intent; retain full text."


def extract(path, root, deadline, byte_limit=None):
    start = path.stat()
    boundary = start.st_size if byte_limit is None else byte_limit
    if not isinstance(boundary, int) or boundary < 0 or boundary > start.st_size:
        raise ValueError("Recorded source boundary is unavailable")
    response_seen = False
    source_hash = hashlib.sha256()
    prompts = []
    excluded = collections.Counter()
    errors = []
    uuids = set()
    assistant_tail = []
    line_no = 0
    with path.open("rb") as stream:
        while stream.tell() < boundary:
            if time.monotonic() > deadline:
                raise TimeoutError("180-second source-read deadline reached")
            raw = stream.readline(boundary - stream.tell())
            source_hash.update(raw)
            line_no += 1
            if not raw:
                break
            try:
                r = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                errors.append(line_no)
                continue
            if not isinstance(r, dict):
                continue
            kind = r.get("type")
            if kind == "assistant" and prompts and not r.get("isSidechain"):
                response_seen = True
                text = body(r)
                if text.strip():
                    assistant_tail.append(text)
                for part in r.get("message", {}).get("content", []):
                    if isinstance(part, dict) and part.get("type") == "tool_use":
                        prompts[-1]["tools"][part.get("name", "unknown")] += 1
                continue
            if kind != "user":
                continue
            if r.get("isSidechain") or r.get("isMeta") or r.get("sourceToolAssistantUUID"):
                excluded["derived_or_sidechain"] += 1
                continue
            if r.get("isCompactSummary"):
                excluded["compaction_summary"] += 1
                continue
            text = body(r)
            stripped = text.strip()
            if stripped == "The app was quit while you were working. Please continue from where you left off.":
                excluded["app_resume_notice"] += 1
                continue
            if not stripped:
                excluded["no_text_or_attachment"] += 1
                continue
            if re.match(
                r"^(<task-notification>|<system-reminder>|<local-command-(stdout|stderr|caveat)>|<bash-(stdout|stderr)>|This session is being continued|This is a continuation|\[Request interrupted by user)",
                stripped,
            ):
                excluded["harness_or_continuation"] += 1
                continue
            if re.match(
                r"^(Message from (another|session)|You have received a message from|<teammate-message|<agent_notification)",
                stripped,
            ):
                excluded["relay"] += 1
                continue
            uid = r.get("uuid") or f"line:{line_no}"
            if uid in uuids:
                excluded["duplicate_uuid_in_file"] += 1
                continue
            uuids.add(uid)
            clean = normalized(stripped)
            if (
                prompts
                and not response_seen
                and not prompts[-1].get("echo_records")
                and prompts[-1]["text"] == clean
                and bool(prompts[-1]["raw_text"]) != (clean != stripped)
                and clean.startswith("/")
            ):
                prompts[-1].setdefault("echo_records", []).append(
                    {"uuid": uid, "line": line_no, "timestamp": r.get("timestamp"), "raw_text": stripped}
                )
                excluded["paired_command_echo"] += 1
                continue
            if prompts:
                prompts[-1]["response"] = {
                    "first": assistant_tail[0] if assistant_tail else "",
                    "last": assistant_tail[-1] if assistant_tail else "",
                    "text_records": len(assistant_tail),
                }
            assistant_tail = []
            response_seen = False
            clean = normalized(stripped)
            intent, command, note = candidate(clean, len(prompts))
            prompts.append(
                {
                    "n": len(prompts) + 1,
                    "line": line_no,
                    "uuid": uid,
                    "parent_uuid": r.get("parentUuid"),
                    "timestamp": r.get("timestamp"),
                    "text": clean,
                    "raw_text": stripped if clean != stripped else None,
                    "intent": intent,
                    "command": command,
                    "note": note,
                    "tools": collections.Counter(),
                }
            )
    if prompts:
        prompts[-1]["response"] = {
            "first": assistant_tail[0] if assistant_tail else "",
            "last": assistant_tail[-1] if assistant_tail else "",
            "text_records": len(assistant_tail),
        }
    # Manual contextual coding for the complete, public-safe Ghostty example.
    if path.name.startswith("62527e84"):
        reviewed = {
            2: ("VERIFY", "/verify grounding"),
            3: ("NEXT", "/next config"),
            4: ("CONTINUE", "/continue"),
            5: ("SHIP", "/ship"),
            6: ("APPLY", "/apply"),
            7: ("CLARIFY", "/explain tab behavior"),
            8: ("CHOICE", "/choose switch"),
            9: ("COMPOUND", "/ship + /apply"),
            10: ("EXPLAIN", "/explain super"),
            11: ("CLOSURE_CHECK", "/verify closure"),
        }
        for item in prompts:
            if item["n"] in reviewed:
                item["intent"], item["command"] = reviewed[item["n"]]
                item["note"] = (
                    "Contextually reviewed against the preceding proposal and the following response; preserve target and arguments."
                )
    end = path.stat()
    return {
        "id": path.name.split(".jsonl")[0],
        "source": str(path.relative_to(root)),
        "bytes_read_boundary": boundary,
        "source_sha256": source_hash.hexdigest(),
        "mtime_ns": start.st_mtime_ns,
        "stable": start.st_size == end.st_size and start.st_mtime_ns == end.st_mtime_ns,
        "parse_error_lines": errors,
        "excluded": dict(excluded),
        "prompts": prompts,
        "coverage": "All retained operator records in this file at the captured byte boundary; original start and terminal completion are not established.",
        "last_response_closeout_claim": bool(prompts and "CLOSEOUT COMPLETE" in prompts[-1]["response"]["last"]),
    }


def render(data, output):
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Prompt sequence study</title>
<style>
:root{color-scheme:light;--ink:#162c3c;--muted:#596b73;--line:#dbe2e3;--accent:#076b6d}*{box-sizing:border-box}body{margin:0;background:#f3f5f2;color:var(--ink);font:15px/1.5 system-ui}header{padding:28px 32px;background:#12323d;color:white}h1{font-size:29px;margin:0 0 8px}header p{max-width:1100px;margin:6px 0;color:#cbdedc}main{padding:20px 24px}.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:center;background:white;padding:14px;border:1px solid var(--line);border-radius:10px;position:sticky;top:0;z-index:3}input,select,button{font:inherit;padding:8px;border:1px solid #b8c7c9;border-radius:6px}input{min-width:300px}button{background:var(--accent);color:white;cursor:pointer}.stats{margin:14px 0;color:var(--muted)}.board{display:flex;gap:16px;overflow-x:auto;align-items:flex-start;padding-bottom:24px}.session{flex:0 0 380px;background:white;border:1px solid var(--line);border-radius:10px;padding:16px}.session h2{font-size:17px;margin:0}.meta{font-size:12px;color:var(--muted);overflow-wrap:anywhere}.turn{border-top:1px solid var(--line);margin-top:15px;padding-top:14px}.tag{font-size:12px;letter-spacing:.04em;font-weight:700;color:var(--accent)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 system-ui;margin:9px 0}.command{font:600 15px ui-monospace;color:#834126}.note{font-size:12px;color:var(--muted)}summary{cursor:pointer;font-size:12px;color:var(--accent)}details pre{font-size:12px;background:#f5f6f4;padding:10px}.warning{color:#983c27}a{color:var(--accent)}.guide{max-width:1100px;margin:16px 0}code{font-family:ui-monospace;font-size:13px}
</style><header><h1>One source file per column. Retained prompts in order.</h1><p>Compare the opener, follow-up wording, suggested command, and the assistant's response. Suggestions are provisional. A response is evidence of what was said and attempted—not independent proof of completion.</p><p>PRIVATE LOCAL REVIEW • source snapshots remain untouched • no network requests • no command execution</p></header><main><div class="controls"><input id="search" placeholder="Search session ID, source, or prompt text"><select id="sort"><option value="date">Recent first</option><option value="length">Longest first</option><option value="id">Session ID</option></select><label><input type="checkbox" id="multi" checked style="min-width:0"> Multiple prompts</label><label><input type="checkbox" id="focus" style="min-width:0"> Six sessions cited by Claude</label><button id="reset">Reset</button></div><p class="guide"><b>How to read:</b> scroll horizontally between sessions; scroll down within the page to follow each session. Filtering selects whole sessions and never removes intermediate prompts. Opener stays uncompressed. Open “Observed response” to check whether the same wording produced the same behavior.</p><div class="stats" id="stats"></div><div class="board" id="board"></div></main><script>
const DATA=__DATA__;
const query=s=>document.querySelector(s);
function el(tag,cls,text){const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=text;return x}
function draw(){const q=query('#search').value.toLowerCase();let rows=DATA.sessions.filter(s=>s.prompts.length&&(!query('#multi').checked||s.prompts.length>1)&&(!query('#focus').checked||DATA.focus.some(id=>s.id.startsWith(id)))&&(!q||(s.id+' '+s.source+' '+s.prompts.map(p=>p.text).join(' ')).toLowerCase().includes(q)));rows.sort((a,b)=>query('#sort').value==='length'?b.prompts.length-a.prompts.length:query('#sort').value==='id'?a.id.localeCompare(b.id):String(b.prompts[0].timestamp).localeCompare(String(a.prompts[0].timestamp)));query('#stats').textContent=rows.length+' shown / '+DATA.summary.sessions_with_prompts+' files with prompts · '+DATA.summary.retained_prompts+' retained records · '+DATA.summary.post_opener+' post-opener records · '+DATA.summary.files+' source files · '+DATA.summary.unstable_files+' changed during reading. Shared UUIDs across files are flagged, not silently counted as independent evidence.';query('#board').replaceChildren();for(const s of rows){const col=el('section','session');col.append(el('h2','',s.id.slice(0,8)+' · '+s.prompts.length+' prompts'),el('p','meta',s.source),el('p','meta',s.coverage));if(!s.stable||s.parse_error_lines.length)col.append(el('p','warning','Source changed or parse errors: inspect coverage.json'));if(s.shared_uuid_count)col.append(el('p','warning',s.shared_uuid_count+' prompt UUIDs also occur in another file. Possible resumed/copied history.'));for(const p of s.prompts){const t=el('article','turn');t.append(el('div','tag','P'+p.n+' · '+p.intent+' · line '+p.line),el('pre','',p.text));if(p.command)t.append(el('div','command',p.command));t.append(el('p','note',p.note));const d=el('details');d.append(el('summary','', 'Observed response · '+Object.values(p.tools).reduce((a,b)=>a+b,0)+' tool calls'));d.append(el('p','meta',JSON.stringify(p.tools)),el('pre','',p.response.first||'[No assistant text retained]'));if(p.response.last!==p.response.first)d.append(el('pre','',p.response.last));t.append(d);if(p.raw_text){const raw=el('details');raw.append(el('summary','','Original command wrapper'),el('pre','',p.raw_text));t.append(raw)}col.append(t)}query('#board').append(col)}}['search','sort','multi','focus'].forEach(id=>query('#'+id).addEventListener('input',draw));query('#reset').onclick=()=>{query('#search').value='';query('#multi').checked=true;query('#focus').checked=false;draw()};draw();
</script></html>""".replace("__DATA__", payload)
    (output / "index.html").write_text(page)


def summarize(sessions):
    uuid_counts = collections.Counter(p["uuid"] for s in sessions for p in s["prompts"])
    for session in sessions:
        session["shared_uuid_count"] = sum(uuid_counts[p["uuid"]] > 1 for p in session["prompts"])
    return {
        "files": len(sessions),
        "source_bytes": sum(s["bytes_read_boundary"] for s in sessions),
        "sessions_with_prompts": sum(bool(s["prompts"]) for s in sessions),
        "multi_prompt_sessions": sum(len(s["prompts"]) > 1 for s in sessions),
        "retained_prompts": sum(len(s["prompts"]) for s in sessions),
        "post_opener": sum(max(0, len(s["prompts"]) - 1) for s in sessions),
        "unique_prompt_uuids": len(uuid_counts),
        "shared_uuid_occurrences": sum(n - 1 for n in uuid_counts.values()),
        "unstable_files": sum(not s["stable"] for s in sessions),
        "parse_error_lines": sum(len(s["parse_error_lines"]) for s in sessions),
        "candidate_counts": dict(collections.Counter(p["intent"] for s in sessions for p in s["prompts"][1:])),
    }


def coverage_for(data):
    return {
        "summary": data["summary"],
        "sessions": [{k: v for k, v in s.items() if k != "prompts"} for s in data["sessions"]],
    }


def check_cache(output, source_root):
    data = json.loads((output / "sequences.json").read_text())
    if not data["sessions"]:
        raise ValueError("No source sessions captured")
    page = (output / "index.html").read_text()
    embedded = re.search(r"const DATA=(.*?);\nconst query=", page, re.DOTALL)
    if not embedded or json.loads(embedded[1]) != data:
        raise ValueError("HTML data differs from the sequence cache")
    if json.loads((output / "coverage.json").read_text()) != coverage_for(data):
        raise ValueError("Coverage differs from the sequence cache")
    deadline = time.monotonic() + 180
    root = source_root.resolve()
    for session in data["sessions"]:
        path = (root / session["source"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Source path escapes the declared root")
        replay = extract(path, root, deadline, byte_limit=session["bytes_read_boundary"])
        # Current mtime/stability can change after capture; content at the recorded
        # boundary must still have exactly the recorded fingerprint and extraction.
        for key in replay:
            if key not in {"mtime_ns", "stable"} and replay[key] != session.get(key):
                raise ValueError(f"Source replay differs: {session['id']} ({key})")
    summary = summarize(data["sessions"])
    recorded = {k: v for k, v in data["summary"].items() if k != "elapsed_seconds"}
    if summary != recorded or json.loads((output / "coverage.json").read_text()) != coverage_for(data):
        raise ValueError("Counts or shared-UUID annotations do not reconcile")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / "Workspace/limen/.agent-runtime/claude")))
        / "projects",
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        try:
            summary = check_cache(args.output, args.source_root)
        except (OSError, ValueError, KeyError, TypeError, TimeoutError) as error:
            ap.error(str(error))
        print(
            f"PASS: source-prefix replay, fingerprints, full HTML data, coverage and counts ({summary['files']} files)"
        )
        return
    started = time.monotonic()
    deadline = started + 180
    if not args.source_root.is_dir():
        ap.error("Source root does not exist or is not a directory")
    paths = sorted(set(args.source_root.glob("*/*.jsonl")) | set(args.source_root.glob("*/*.jsonl.orphaned")))
    if not paths:
        ap.error("No eligible source files found")
    sessions = [extract(p, args.source_root, deadline) for p in paths]
    summary = summarize(sessions)
    summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
    data = {
        "schema": "prompt-sequence-study.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "Claude top-level native JSONL files; no other provider; not an exhaustive account-history census",
        "focus": ["6ffc6427", "1607c1d2", "c04eb60f", "cd4ddafd", "62527e84", "8d9c1055"],
        "summary": summary,
        "sessions": sessions,
    }
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    (args.output / "sequences.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    coverage = coverage_for(data)
    (args.output / "coverage.json").write_text(json.dumps(coverage, indent=2))
    render(data, args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
