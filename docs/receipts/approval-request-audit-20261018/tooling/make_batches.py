"""Split approval-events.jsonl into per-batch readable dossiers (same-session events stay together)."""
import json
import os
import sys
import textwrap

src, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
events = [json.loads(line) for line in open(src)]
by_session = {}
for e in events:
    by_session.setdefault(e["session"], []).append(e)

MAX_EVENTS, MAX_CHARS = 6, 26000


def render(e):
    def block(label, text):
        wrapped = "\n".join(textwrap.fill(p, 180) for p in (text or "").splitlines() if p.strip()) or "(empty)"
        return f"{label}:\n{wrapped}\n"

    head = (f"=== {e['id']} | kind={e['kind']} | {e['ts']} | permission-mode={e['mode']} | "
            f"sidechain={e['sidechain']} | project={e['project']} | session={e['session']} ===\n")
    return (head + block("LAST HUMAN MESSAGE BEFORE THIS", e["human_prompt"])
            + block("ASSISTANT'S PRECEDING TEXT", e["assistant_text"])
            + block(f"TOOL = {e['tool']}; INPUT", e["input"])
            + block("RESULT / USER RESPONSE", e["result"]) + "\n")


batches, cur, cur_chars = [], [], 0
for session, evs in sorted(by_session.items(), key=lambda kv: kv[1][0]["ts"]):
    for e in evs:
        text = render(e)
        if cur and (len(cur) >= MAX_EVENTS or cur_chars + len(text) > MAX_CHARS):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append({**e, "_text": text})
        cur_chars += len(text)
if cur:
    batches.append(cur)

manifest = []
for i, b in enumerate(batches):
    path = os.path.abspath(os.path.join(outdir, f"B{i:02d}.txt"))
    with open(path, "w") as fh:
        fh.write(f"BATCH B{i:02d} — events: {', '.join(e['id'] for e in b)}\n\n")
        for e in b:
            fh.write(e["_text"])
    manifest.append({"batch": f"B{i:02d}", "path": path, "ids": [e["id"] for e in b]})
json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w"), indent=1)
print(len(batches), "batches;", sum(len(b) for b in batches), "events")
print("sizes (chars):", [os.path.getsize(m["path"]) for m in manifest])
