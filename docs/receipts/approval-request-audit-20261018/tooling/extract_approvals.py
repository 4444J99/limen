"""Extract every visible approval-request event from Claude transcripts in a time window.

Visible traces: AskUserQuestion, ExitPlanMode, user-rejected tool prompts, auto-mode classifier denials.
Usage: python3 -I extract_approvals.py <out.jsonl>
"""
import collections
import glob
import json
import os
import sys

CUT = "2026-10-15T17:16"  # 72h before 2026-10-18T17:16Z
CUT_EPOCH = 1792000000
ROOT = "/Users/4jp/Workspace/limen/.agent-runtime/claude/projects"


def flat(content, cap):
    if isinstance(content, str):
        s = content
    elif isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
            else:
                parts.append(json.dumps(b)[:400])
        s = "\n".join(parts)
    else:
        s = json.dumps(content)
    return s[:cap]


def main(out_path):
    events = []
    for f in sorted(glob.glob(f"{ROOT}/*/*.jsonl")):
        if os.path.getmtime(f) < CUT_EPOCH:
            continue
        project = os.path.basename(os.path.dirname(f))
        session = os.path.basename(f)[:-6]
        human = ""
        asst = ""
        mode = "?"
        uses = {}
        for line in open(f, errors="ignore"):
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            ts = o.get("timestamp") or ""
            if t == "permission-mode":
                mode = o.get("permissionMode", mode)
                continue
            m = o.get("message")
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            if t == "user":
                if isinstance(c, str):
                    if not o.get("isMeta"):
                        human = c[-1500:]
                    continue
                if not isinstance(c, list):
                    continue
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and not o.get("isSidechain") and not o.get("isMeta"):
                        human = b.get("text", "")[-1500:]
                    if b.get("type") != "tool_result":
                        continue
                    use = uses.get(b.get("tool_use_id"))
                    if not use:
                        continue
                    res = flat(b.get("content"), 1500)
                    kind = None
                    if use["name"] in ("AskUserQuestion", "ExitPlanMode"):
                        kind = use["name"]
                    elif b.get("is_error") and res.startswith("Permission for this action was denied"):
                        kind = "classifier_denial"
                    elif b.get("is_error") and "doesn't want to proceed" in res:
                        kind = "user_rejected_prompt"
                    if kind and use["ts"] >= CUT:
                        events.append({
                            "kind": kind, "project": project, "session": session, "ts": use["ts"],
                            "mode": use["mode"], "tool": use["name"], "input": use["input"],
                            "human_prompt": use["human"], "assistant_text": use["asst"], "result": res,
                            "sidechain": bool(o.get("isSidechain")),
                        })
            elif t == "assistant":
                if not isinstance(c, list):
                    continue
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and b.get("text", "").strip():
                        asst = b["text"][-1500:]
                    elif b.get("type") == "tool_use":
                        uses[b["id"]] = {
                            "name": b["name"], "ts": ts, "mode": mode, "human": human, "asst": asst,
                            "input": json.dumps(b.get("input"))[:1800],
                        }
    events.sort(key=lambda e: e["ts"])
    for i, e in enumerate(events):
        e["id"] = f"E{i:03d}"
    with open(out_path, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    by_kind = collections.Counter(e["kind"] for e in events)
    by_day = collections.Counter((e["ts"][:10], e["kind"]) for e in events)
    by_proj = collections.Counter(e["project"].replace("-Users-4jp-Workspace-limen--claude-worktrees-", "wt:") for e in events)
    by_mode = collections.Counter((e["kind"], e["mode"]) for e in events)
    print(len(events), "events since", CUT)
    print("by kind", dict(by_kind))
    print("by day/kind", sorted(by_day.items()))
    print("by mode", sorted(by_mode.items()))
    print("top projects", by_proj.most_common(12))


main(sys.argv[1])
