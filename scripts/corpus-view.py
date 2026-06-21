#!/usr/bin/env python3
"""corpus-view.py — make the knowledge base VISIBLE (the answer to "what happened to my corpus?").

The corpus was invisible to the running system — a buried file you had to navigate the filesystem to
see. This renders it where you already look: a self-contained web/app/out/corpus.html (meta-refresh,
pure string templating — NO Next.js, NO network, can't time out) plus logs/corpus-view.json, mirrored
to web/app/public/ for the phone face. It shows THE ONE's one-sentence, the 13 faces with their last
convergence, the live convergence activity (what the corpus-converge organ distilled + the gaps it
surfaced), and how much new material has been absorbed.

Anti-waste + never-"NO": every section fails OPEN — a missing/torn feed yields an empty section, never
a crash. Read-only on the corpus; writes only its own output files.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]


def _corpus_root():
    return Path(os.environ.get("LIMEN_CORPUS_ROOT", Path.home() / "Workspace" / "knowledge-corpus"))


_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_REDDATE_RE = re.compile(r"\*\*Reduction date:\*\*\s*(.+)")
_CONVERGED_RE = re.compile(r"_Converged\s+(\d{4}-\d{2}-\d{2})\b.*?absorbed\s+(\d+)\s+new", re.DOTALL)
_ONE_SENTENCE_RE = re.compile(r"^>\s*\*\*(.+?)\*\*\s*$", re.DOTALL | re.MULTILINE)


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _jsonl(path, n=40):
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def _one_sentence(the_one_text):
    """The compressed seed — the first bolded blockquote in 00-THE-ONE."""
    m = _ONE_SENTENCE_RE.search(the_one_text)
    if not m:
        return ""
    # the blockquote spans several lines, each prefixed with '> ' — strip those continuations.
    cleaned = re.sub(r"\n\s*>\s*", " ", m.group(1))
    return re.sub(r"\s+", " ", cleaned).strip()


def build_view():
    corpus = _corpus_root()
    reduced = corpus / "reduced"
    faces = []
    if reduced.is_dir():
        for p in sorted(reduced.glob("*.md")):
            try:
                text = p.read_text()
                st = p.stat()
            except OSError:
                continue
            h1 = _H1_RE.search(text)
            conv = _CONVERGED_RE.search(text)
            faces.append({
                "name": p.stem,
                "title": h1.group(1).strip() if h1 else p.stem,
                "kb": round(st.st_size / 1024, 1),
                "updated": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "auto_converged": conv.group(1) if conv else None,
                "absorbed": int(conv.group(2)) if conv else None,
                "reduction_date": (_REDDATE_RE.search(text).group(1).strip()
                                   if _REDDATE_RE.search(text) else None),
            })

    one_path = corpus / "00-THE-ONE.md"
    one_text = ""
    one_kb = one_updated = None
    if one_path.is_file():
        try:
            one_text = one_path.read_text()
            st = one_path.stat()
            one_kb = round(st.st_size / 1024, 1)
            one_updated = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            pass

    log = _jsonl(LOGS / "corpus-converge-log.jsonl")
    state = _load_json(LOGS / "corpus-converge-state.json", {})
    activity = list(reversed(log[-12:]))
    gaps_total = sum(int(r.get("gaps", 0) or 0) for r in log)
    last_run = log[-1].get("ts") if log else None

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "one_sentence": _one_sentence(one_text),
        "the_one": {"kb": one_kb, "updated": one_updated},
        "faces": faces,
        "face_count": len(faces),
        "absorbed_total": len(state.get("absorbed", [])),
        "gaps_total": gaps_total,
        "last_run": last_run,
        "activity": activity,
    }


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(v):
    face_rows = []
    for f in v["faces"]:
        when = (f"<span class='auto'>↻ {_esc(f['auto_converged'])}</span>" if f.get("auto_converged")
                else f"<span class='hand'>{_esc(f.get('reduction_date') or '—')}</span>")
        absorbed = f" · +{f['absorbed']} absorbed" if f.get("absorbed") else ""
        face_rows.append(f"""
        <tr><td><b>{_esc(f['title'])}</b><div class="sub2">{_esc(f['name'])}</div></td>
          <td class="num">{f['kb']}K</td>
          <td>{when}{absorbed}</td></tr>""")

    act = ""
    if v["activity"]:
        items = "".join(
            f"<li><b>{_esc(r.get('face',''))}</b> +{_esc(r.get('new_shots',0))} shots → "
            f"score {_esc(r.get('score','—'))} "
            f"{'<span class=ok>written</span>' if r.get('wrote') else '<span class=dim>preview</span>'}"
            f"{(' · ' + str(r.get('gaps')) + ' gaps') if r.get('gaps') else ''}</li>"
            for r in v["activity"])
        act = f'<div class="card"><div class="k">CONVERGENCE ACTIVITY</div><ul>{items}</ul></div>'
    else:
        act = ('<div class="card"><div class="k">CONVERGENCE ACTIVITY</div>'
               '<div class="dim" style="margin-top:6px">organ idle — set LIMEN_CORPUS_CONVERGE=1 '
               '(and LIMEN_CORPUS_CONVERGE_LIVE=1 for real synthesis) to begin distilling.</div></div>')

    one = v["the_one"]
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60"><title>LIMEN — the corpus</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:880px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .one{{border-color:#7c6cff;background:#15122b}} .one .seed{{font-size:15px;color:#d8d2ff;font-style:italic}}
 .k{{color:#8a93a6;font-size:12px;text-transform:uppercase;letter-spacing:.5px}}
 table{{width:100%;border-collapse:collapse}} td{{padding:8px 6px;border-top:1px solid #21262d;vertical-align:top}}
 .sub2{{color:#8a93a6;font-size:12px}} .num{{color:#8a93a6;width:50px;text-align:right}}
 .auto{{color:#2ecc71;font-weight:700}} .hand{{color:#8a93a6}} .ok{{color:#2ecc71;font-weight:700}}
 .dim{{color:#8a93a6}} ul{{margin:6px 0;padding-left:18px}} li{{margin:3px 0}}
 .row{{display:flex;gap:24px;flex-wrap:wrap}} .big{{font-size:26px;font-weight:700}}
</style></head><body><div class="wrap">
 <h1>LIMEN — the knowledge base</h1>
 <div class="sub">updated {_esc(v['generated_at'])} · auto-refresh 60s · DIVERGE → CONVERGE → ONE</div>
 <div class="card one"><div class="k">THE ONE — the compressed seed</div>
   <div class="seed" style="margin-top:8px">{_esc(v['one_sentence']) or '—'}</div>
   <div class="sub" style="margin-top:10px">00-THE-ONE.md · {one.get('kb') or '—'}K · updated {_esc(one.get('updated') or '—')}</div>
 </div>
 <div class="card row">
   <div><div class="k">faces</div><div class="big">{v['face_count']}</div></div>
   <div><div class="k">shots absorbed</div><div class="big">{v['absorbed_total']}</div></div>
   <div><div class="k">gaps surfaced</div><div class="big">{v['gaps_total']}</div></div>
   <div><div class="k">last run</div><div class="big" style="font-size:15px">{_esc(v['last_run'] or '—')}</div></div>
 </div>
 <div class="card"><div class="k">THE 13 FACES</div>
   <table><tbody>{''.join(face_rows) or '<tr><td class=dim>no faces found</td></tr>'}</tbody></table></div>
 {act}
</div></body></html>"""


def main():
    view = build_view()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "corpus-view.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "corpus.html").write_text(html)
            (d / "corpus-view.json").write_text(json.dumps(view, indent=2))
            wrote.append(str(d / "corpus.html"))
        except OSError:
            continue
    print(f"corpus-view: {view['face_count']} faces, {view['absorbed_total']} absorbed, "
          f"{view['gaps_total']} gaps, last run {view['last_run'] or 'never'} "
          f"-> {', '.join(wrote) or 'logs/corpus-view.json only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
