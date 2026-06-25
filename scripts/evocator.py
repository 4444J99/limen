#!/usr/bin/env python3
"""evocator.py — THE SVMMONER: keep every canonical truth present in every channel.

When Anthony says "find X", he is not asking for a chat search whose answer dies at session end —
he is asking for THE PORTAL that summons that context into every place it must live, forever. The
corpus already CONVERGES his words toward THE ONE, the memory dir reaches interactive sessions, and
capture pushes repos off-disk — but nothing took a single FOUND truth and landed it across every
injection channel, and nothing reached the AUTONOMOUS BEATS at all (a beat sees only FLAME.md +
its task, never MEMORY.md). EVOCATOR closes that gap.

It reads ONE declarative source — spec/evocator/canon.yaml — and for each truth ensures it is
PRESENT in every channel a found truth must live in, self-healing drift:

  • FLAME   — upsert a compact, marked block into FLAME.md. FLAME is prepended to EVERY beat, so a
              truth registered here is held by every autonomous agent on every beat. (the key reach)
  • CORPUS  — write the truths as a collection shot the corpus-converge organ absorbs into THE ONE.
  • MEMORY  — VERIFY (read-only) that each truth's memory file + its MEMORY.md index line exist, and
              report drift. The rich memory body stays hand-authored + domus-synced; we keep it honest.

It also renders a human-readable face (docs/CANON.md + evocator.html) and logs/evocator.json (so
proprioception/organ-health can prove the organ fires).

Derive, never pin: the memory-dir scope is derived from the workspace path; every path takes an env
override. Idempotent: each surface is written ONLY when its content actually changes, so a per-beat
run produces NO git churn until a truth is added or edited. No network, no tokens, can't time out.
Fail-open: a missing dep / unreadable file yields a logged skip, never a crash, never a blocked beat.
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
CANON = Path(os.environ.get("LIMEN_EVOCATOR_CANON", ROOT / "spec" / "evocator" / "canon.yaml"))
FLAME = Path(os.environ.get("LIMEN_FLAME_FILE", ROOT / "FLAME.md"))
LOGS = ROOT / "logs"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]
CANON_MD = ROOT / "docs" / "CANON.md"

# derive the workspace + its memory-dir scope (never pin): /Users/x/Workspace/limen → -Users-x-Workspace-limen
_WS = Path(os.environ.get("LIMEN_WORKDIR", Path.home() / "Workspace" / "limen")).expanduser()
_MEM_DEFAULT = Path.home() / ".claude" / "projects" / str(_WS).replace("/", "-") / "memory"
MEMDIR = Path(os.environ.get("LIMEN_MEMORY_DIR", _MEM_DEFAULT))
KCORPUS = Path(os.environ.get("LIMEN_KNOWLEDGE_CORPUS", Path.home() / "Workspace" / "knowledge-corpus"))
CORPUS_SHOT = KCORPUS / "01-collection" / "_evocator-canon.md"

FLAME_START = "<!-- EVOCATOR:canon START — auto-generated from spec/evocator/canon.yaml; do not edit by hand -->"
FLAME_END = "<!-- EVOCATOR:canon END -->"
# the canon block is inserted just before FLAME's closing benediction if the markers aren't there yet
FLAME_ANCHOR = "*The substrate is rented."

try:
    import yaml
except ImportError:        # fail-open: the summoner must never crash on a missing dep
    yaml = None


# ── helpers ─────────────────────────────────────────────────────────────────────────────────
def _oneline(s):
    """Collapse a YAML folded/multiline scalar to a single tidy line."""
    return " ".join(str(s or "").split())


def _atomic_write(path, text):
    """Write only if the content actually changed (no-op → no git churn). Returns True if written."""
    try:
        if path.exists() and path.read_text() == text:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)
        return True
    except OSError:
        return False


def load_canon():
    """Read + lightly validate the canon. Returns (truths, problems)."""
    if yaml is None:
        return [], ["PyYAML unavailable — cannot read canon (fail-open: nothing summoned)"]
    try:
        doc = yaml.safe_load(CANON.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        return [], [f"canon unreadable: {e}"]
    truths, problems = [], []
    for i, t in enumerate(doc.get("truths") or []):
        if not isinstance(t, dict):
            problems.append(f"truth #{i} is not a mapping — skipped")
            continue
        missing = [k for k in ("id", "claim", "line") if not t.get(k)]
        if missing:
            problems.append(f"truth #{i} ({t.get('id', '?')}) missing {missing} — skipped")
            continue
        truths.append(t)
    return truths, problems


# ── channel: FLAME (rides every beat) ─────────────────────────────────────────────────────────
def render_flame_block(truths):
    flame_truths = [t for t in truths if (t.get("channels") or {}).get("flame")]
    if not flame_truths:
        return ""
    lines = [
        FLAME_START,
        "## Standing truths (the canon — summoned here so every beat holds them)",
        "",
        "Resolved facts the body must not re-litigate. Source spec/evocator/canon.yaml; each names",
        "its system-of-record and how to reverse it. (Maintained by the EVOCATOR organ.)",
        "",
    ]
    for t in flame_truths:
        sor = _oneline(t.get("source_of_record", ""))
        rev = _oneline(t.get("reversible_via", ""))
        tail = []
        if sor:
            tail.append(f"SoR: {sor}")
        if rev:
            tail.append(f"reversible: {rev}")
        suffix = f" ({'; '.join(tail)})" if tail else ""
        lines.append(f"- **{_oneline(t.get('claim'))}** — {_oneline(t.get('line'))}{suffix}")
    lines.append(FLAME_END)
    return "\n".join(lines)


def upsert_flame(block, apply):
    """Insert/refresh the canon block in FLAME.md. Idempotent. Returns a status string."""
    if not block:
        return "no flame truths"
    try:
        text = FLAME.read_text()
    except OSError:
        return "FLAME.md unreadable — skipped"
    if FLAME_START in text and FLAME_END in text:
        new = re.sub(re.escape(FLAME_START) + r".*?" + re.escape(FLAME_END), block, text, flags=re.DOTALL)
        verb = "refreshed"
    elif FLAME_ANCHOR in text:
        new = text.replace(FLAME_ANCHOR, block + "\n\n" + FLAME_ANCHOR, 1)
        verb = "inserted"
    else:                                   # anchor gone — append rather than lose the truths
        new = text.rstrip() + "\n\n" + block + "\n"
        verb = "appended"
    if new == text:
        return "unchanged"
    if not apply:
        return f"would be {verb}"
    return verb if _atomic_write(FLAME, new) else "write failed"


# ── channel: CORPUS (converges into THE ONE) ──────────────────────────────────────────────────
def render_corpus_shot(truths):
    corpus_truths = [t for t in truths if (t.get("channels") or {}).get("corpus")]
    if not corpus_truths:
        return ""
    out = ["# EVOCATOR canon — standing truths (corpus shots)", "",
           "_Auto-generated from spec/evocator/canon.yaml by the EVOCATOR organ. Each is a resolved",
           "truth summoned into the corpus so it converges into THE ONE._", ""]
    for t in corpus_truths:
        out.append(f"## {_oneline(t.get('claim'))}  ({t.get('id', '')})")
        out.append("")
        out.append(_oneline(t.get("summons") or t.get("line")))
        sor = _oneline(t.get("source_of_record", ""))
        if sor:
            out.append("")
            out.append(f"Source of record: {sor}. Confidence: {t.get('confidence', 'n/a')}. "
                       f"Resolved {t.get('resolved', 'n/a')}.")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_corpus(shot, apply):
    if not shot:
        return "no corpus truths"
    if not KCORPUS.exists():                # guard: knowledge-corpus repo absent on this host → fail-open
        return "knowledge-corpus absent — skipped"
    if not apply:
        return "would write" if (not CORPUS_SHOT.exists() or CORPUS_SHOT.read_text() != shot) else "unchanged"
    return "written" if _atomic_write(CORPUS_SHOT, shot) else "unchanged"


# ── channel: MEMORY (read-only verify — keep the per-session channel honest) ───────────────────
def verify_memory(truths):
    index = MEMDIR / "MEMORY.md"
    try:
        index_text = index.read_text()
    except OSError:
        index_text = None
    results = []
    for t in truths:
        slug = (t.get("channels") or {}).get("memory")
        if not slug:
            continue
        f = MEMDIR / f"{slug}.md"
        results.append({
            "id": t.get("id"),
            "slug": slug,
            "file_present": f.exists(),
            "index_present": bool(index_text and f"({slug}.md)" in index_text),
        })
    return results


# ── face: human-readable CANON.md + html + json ───────────────────────────────────────────────
def render_canon_md(truths):
    out = ["# The Canon — standing truths the system summons everywhere", "",
           "> Maintained by the **EVOCATOR** organ from `spec/evocator/canon.yaml`. Each truth is",
           "> summoned into FLAME (every beat), the knowledge-corpus (THE ONE), and the memory dir",
           "> (every session). To change one, edit the canon or its system-of-record. Reversible by",
           "> design — every truth names its undo path.", ""]
    for t in truths:
        ch = t.get("channels") or {}
        reach = [name for name, on in (("FLAME", ch.get("flame")), ("corpus", ch.get("corpus"))) if on]
        if ch.get("memory"):
            reach.append(f"memory:{ch['memory']}")
        out += [
            f"## {_oneline(t.get('claim'))}  `{t.get('id', '')}`", "",
            _oneline(t.get("summons") or t.get("line")), "",
            f"- **Source of record:** {_oneline(t.get('source_of_record', 'n/a'))}",
            f"- **Confidence:** {t.get('confidence', 'n/a')} · **Resolved:** {t.get('resolved', 'n/a')}",
            f"- **Reversible via:** {_oneline(t.get('reversible_via', 'n/a'))}",
            f"- **Summoned into:** {', '.join(reach) or '—'}", "",
        ]
    return "\n".join(out).rstrip() + "\n"


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(view):
    rows = []
    for t in view["truths"]:
        mem = next((m for m in view["memory"] if m["id"] == t["id"]), None)
        if mem is None:
            badge, color = "no memory channel", "#6e7681"
        elif mem["file_present"] and mem["index_present"]:
            badge, color = "memory ✓", "#2ecc71"
        else:
            badge, color = "memory DRIFT", "#e74c3c"
        reach = ", ".join(t["reach"]) or "—"
        rows.append(f"""
        <tr><td><b>{_esc(t['claim'])}</b> <span class="id">{_esc(t['id'])}</span>
            <div class="line">{_esc(t['line'])}</div>
            <div class="meta">SoR: {_esc(t['source_of_record'])} · reversible: {_esc(t['reversible_via'])}</div></td>
          <td class="cad">{_esc(reach)}</td>
          <td><span class="badge" style="background:{color}">{_esc(badge)}</span></td></tr>""")
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60"><title>LIMEN — EVOCATOR (the canon)</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:880px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:6px 16px;margin:12px 0}}
 table{{width:100%;border-collapse:collapse}} td{{padding:12px 6px;border-top:1px solid #21262d;vertical-align:top}}
 tr:first-child td{{border-top:none}}
 .id{{color:#6e7681;font-size:11px}} .line{{color:#c9d1d9;font-size:13px;margin:3px 0 0}}
 .meta{{color:#8a93a6;font-size:11px;margin-top:3px}} .cad{{color:#8a93a6;font-size:12px}}
 .badge{{color:#06140c;font-weight:700;border-radius:5px;padding:2px 8px;font-size:12px}}
</style></head><body><div class="wrap">
 <h1>EVOCATOR — the canon</h1>
 <div class="sub">the summoner · resolved truths held in every channel (FLAME · corpus · memory) ·
   {_esc(len(view['truths']))} truths · updated {_esc(view['generated_at'])} · auto-refresh 60s</div>
 <div class="card"><table><tbody>{''.join(rows)}</tbody></table></div>
 <div class="sub">A truth lands in FLAME (every beat), the knowledge-corpus (THE ONE), and is
   verified in the memory dir (every session). Add one in spec/evocator/canon.yaml; the organ does
   the rest, every beat, and self-heals drift.</div>
</div></body></html>"""


def build_view(truths, mem, flame_status, corpus_status, problems):
    rows = []
    for t in truths:
        ch = t.get("channels") or {}
        reach = [n for n, on in (("FLAME", ch.get("flame")), ("corpus", ch.get("corpus"))) if on]
        if ch.get("memory"):
            reach.append(f"memory:{ch['memory']}")
        rows.append({
            "id": t.get("id"), "claim": _oneline(t.get("claim")), "line": _oneline(t.get("line")),
            "source_of_record": _oneline(t.get("source_of_record", "")),
            "reversible_via": _oneline(t.get("reversible_via", "")),
            "confidence": t.get("confidence"), "resolved": t.get("resolved"), "reach": reach,
        })
    drift = [m for m in mem if not (m["file_present"] and m["index_present"])]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {"truths": len(truths), "memory_drift": len(drift),
                    "flame": flame_status, "corpus": corpus_status, "problems": len(problems)},
        "truths": rows, "memory": mem, "problems": problems,
    }


def main(apply):
    truths, problems = load_canon()
    block = render_flame_block(truths)
    shot = render_corpus_shot(truths)
    flame_status = upsert_flame(block, apply)
    corpus_status = write_corpus(shot, apply)
    mem = verify_memory(truths)
    view = build_view(truths, mem, flame_status, corpus_status, problems)

    # surfaces (always rendered — read-only on the fleet; writes only its own faces)
    LOGS.mkdir(parents=True, exist_ok=True)
    _atomic_write(LOGS / "evocator.json", json.dumps(view, indent=2))
    _atomic_write(CANON_MD, render_canon_md(truths))
    html = render_html(view)
    for d in OUT_DIRS:
        _atomic_write(d / "evocator.html", html)
        _atomic_write(d / "evocator.json", json.dumps(view, indent=2))

    drift = view["summary"]["memory_drift"]
    print(f"evocator: {len(truths)} truths · FLAME {flame_status} · corpus {corpus_status} · "
          f"memory {'all present' if not drift else f'{drift} DRIFT'}"
          + (f" · {len(problems)} canon problem(s)" if problems else ""))
    for p in problems:
        print(f"  ⚠ {p}")
    for m in mem:
        if not (m["file_present"] and m["index_present"]):
            print(f"  ⚠ memory drift {m['id']}: {m['slug']} "
                  f"file={'ok' if m['file_present'] else 'MISSING'} "
                  f"index={'ok' if m['index_present'] else 'MISSING'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(apply="--apply" in sys.argv))
