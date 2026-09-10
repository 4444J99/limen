#!/usr/bin/env python3
"""Generate lever-triage.html from his-hand-levers.json.

Offline, single-file SPA. Reconciles the 87-open vs 93-triaged count:

- open == 87 (status == 'open' or ''), as stated in handoff
- triaged == 93 (open + needs_human = 87 + 6) — the set rendered in the UI

Categories are derived deterministically from lever IDs so the sidebar
progress reconciles to lever-summary.md. An optional enriched JSON can be
merged (pros/cons/paths) without breaking offline operation.

Usage:
  python3 scripts/generate_html.py
  python3 scripts/generate_html.py --in his-hand-levers.json --out lever-triage.html
  python3 scripts/generate_html.py --enriched his-hand-levers-enriched.json
"""

import argparse
import json
import pathlib
import re
import html as html_lib

DEFAULT_IN = "his-hand-levers.json"
DEFAULT_OUT = "lever-triage.html"

# Deterministic category map — keep in sync with lever-summary.md
_CATEGORY_RULES = [
    ("Security & Credentials", [
        "ARCA", "MODEL-TIER", "FLEET", "DOMUS", "TCC", "BACKUP-FDA",
        "FIREWALL", "DIALOGS", "AGENT-BASH", "LINT", "IANVA", "NAS-CRED",
        "MAIL-AUTOMATION", "OPENCODE-AUTH", "FABLE-GUARD", "TCC-",
    ]),
    ("Academic (ENC)", [
        "ENC1101", "ENC1102", "EDU-PERTERM", "IDENTITY-POPULATE",
    ]),
    ("Positioning & Social", [
        "POSITIONING", "LINKEDIN", "STUDIO-GOLIVE", "MONETA", "DECORUM",
        "SOCIAL", "VIC-SHARE", "DUSTIN-GH", "LAVREA",
    ]),
    ("Architecture & Systems", [
        "CONTAINER", "ESTATE-MOUNT", "BACKBLAZE", "PORTAL-PUBLISH",
        "CLOUD-", "CONDUCT-REGISTRY", "BRANCH-", "MEDIA-ARK", "AUDIO-",
        "OBSERVATORY", "UNIVERSE-RECOVERY", "CLOSEOUT-OBSERVE",
        "CLAUDE-SETTINGS", "CLAUDE-DEEPLINK", "CLAUDE-GATEKEEPER",
        "REMOTE-REAP", "URL-HIERARCHY", "BRANCH-REAP", "CARTRIDGE-REPOINT",
    ]),
]


def categorize(lever_id: str) -> str:
    for cat, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if kw in lever_id:
                return cat
    return "Uncategorized"


def load_levers(path: pathlib.Path, enriched_path: pathlib.Path | None):
    data = json.loads(path.read_text(encoding="utf-8"))
    levers_all = data.get("levers", [])
    generated_at = data.get("generated_at", "")

    # Merge enriched if present — only pros/cons/paths
    if enriched_path and enriched_path.exists():
        try:
            enriched = json.loads(enriched_path.read_text(encoding="utf-8"))
            enriched_map = {lv["id"]: lv for lv in enriched.get("levers", [])}
            for lv in levers_all:
                if lv["id"] in enriched_map:
                    for k in ("pros", "cons", "paths"):
                        if enriched_map[lv["id"]].get(k):
                            lv[k] = enriched_map[lv["id"]][k]
        except Exception as e:
            print(f"Warning: could not merge enriched {enriched_path}: {e}")

    # Triaged set: open + needs_human (93). Everything else is visible but not triaged.
    def is_triaged(lv):
        s = lv.get("status", "open").lower()
        return s in ("open", "", "needs_human")

    triaged = [lv for lv in levers_all if is_triaged(lv)]
    # Annotate category
    for lv in triaged:
        lv["category"] = categorize(lv["id"])

    counts = {}
    for lv in triaged:
        counts[lv["category"]] = counts.get(lv["category"], 0) + 1

    return data, levers_all, triaged, generated_at, counts


def build_html(triaged, generated_at: str) -> str:
    # Safe JSON embed — escape </script> to avoid breaking the script tag
    levers_json = json.dumps(triaged, ensure_ascii=False)
    levers_json = levers_json.replace("</", "<\\/")

    # Build category list for JS
    categories = sorted(set(lv["category"] for lv in triaged),
                        key=lambda c: ["Security & Credentials", "Academic (ENC)",
                                       "Positioning & Social", "Architecture & Systems",
                                       "Uncategorized"].index(c) if c in ["Security & Credentials", "Academic (ENC)",
                                                                            "Positioning & Social", "Architecture & Systems",
                                                                            "Uncategorized"] else 99)

    total = len(triaged)
    # Version key for localStorage — bust when source changes
    version = re.sub(r"[^0-9A-Za-z_-]+", "-", generated_at) if generated_at else "v1"

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Human Levers Triage Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0; padding: 0; display: flex; height: 100vh;
            background-color: #f3f4f6; color: #1f2937;
        }}
        #sidebar {{
            width: 370px; background-color: #ffffff; border-right: 1px solid #e5e7eb;
            overflow-y: auto; display: flex; flex-direction: column;
        }}
        .sidebar-header {{
            padding: 18px 20px; border-bottom: 1px solid #e5e7eb;
            background-color: #f9fafb; position: sticky; top: 0; z-index: 1;
        }}
        .sidebar-header h2 {{ margin: 0 0 8px 0; font-size: 18px; }}
        .progress {{ font-size: 13px; color: #4b5563; margin-bottom: 10px; }}
        .category-header {{
            padding: 10px 20px 6px 20px; font-size: 11px; font-weight: 700;
            letter-spacing: 0.06em; text-transform: uppercase; color: #6b7280;
            background: #f3f4f6; border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb;
            display: flex; justify-content: space-between;
        }}
        .lever-item {{
            padding: 12px 20px; border-bottom: 1px solid #e5e7eb;
            cursor: pointer; transition: background-color 0.15s;
        }}
        .lever-item:hover {{ background-color: #f9fafb; }}
        .lever-item.active {{ background-color: #eff6ff; border-left: 4px solid #3b82f6; }}
        .lever-item.completed {{ opacity: 0.72; }}
        .lever-item.completed .lever-id::after {{ content: " ✓"; color: #10b981; }}
        .lever-id {{ font-weight: 600; font-size: 13px; margin-bottom: 3px; word-break: break-word; }}
        .lever-preview {{ font-size: 11px; color: #6b7280; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .lever-meta {{ font-size: 11px; color: #9ca3af; margin-top: 2px; }}
        #main {{ flex: 1; padding: 36px; overflow-y: auto; }}
        .card {{
            background: white; border-radius: 8px; padding: 28px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08); max-width: 860px; margin: 0 auto;
        }}
        h1 {{ margin-top: 0; font-size: 22px; word-break: break-word; }}
        h3 {{ margin-top: 22px; font-size: 15px; color: #4b5563; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }}
        .badge {{
            display: inline-block; background: #f3f4f6; padding: 4px 8px; border-radius: 4px;
            font-size: 11px; font-weight: 600; color: #4b5563; margin-right: 6px; margin-bottom: 10px;
        }}
        .pro-con {{ display: flex; gap: 16px; margin-top: 14px; }}
        .pro-con > div {{ flex: 1; padding: 14px; border-radius: 6px; }}
        .pros {{ background-color: #ecfdf5; border: 1px solid #a7f3d0; }}
        .cons {{ background-color: #fef2f2; border: 1px solid #fecaca; }}
        .pros h4 {{ color: #059669; margin-top:0; font-size: 13px; }}
        .cons h4 {{ color: #dc2626; margin-top:0; font-size: 13px; }}
        select, textarea {{
            width: 100%; padding: 11px; border: 1px solid #d1d5db; border-radius: 6px;
            margin-top: 8px; font-family: inherit; font-size: 13px;
        }}
        textarea {{ height: 120px; resize: vertical; }}
        .btn {{
            background-color: #3b82f6; color: white; border: none; padding: 9px 16px;
            border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 13px; margin-top: 12px;
        }}
        .btn:hover {{ background-color: #2563eb; }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .export-btn {{ width: 100%; background-color: #10b981; }}
        .export-btn:hover {{ background-color: #059669; }}
        .secondary-btn {{ width: 100%; background-color: #6b7280; }}
        .secondary-btn:hover {{ background-color: #4b5563; }}
        .toolbar {{ display: flex; gap: 8px; margin-top: 10px; }}
        .toolbar .btn {{ flex: 1; margin-top: 0; }}
        .help {{ font-size: 12px; color: #6b7280; margin-top: 8px; }}
        .detail-meta {{ font-size: 13px; color: #4b5563; line-height: 1.5; }}
        .detail-meta strong {{ color: #1f2937; }}
    </style>
</head>
<body>
    <div id=\"sidebar\">
        <div class=\"sidebar-header\">
            <h2>Human Levers</h2>
            <div class=\"progress\" id=\"progress\">0 / {total} triaged</div>
            <div class=\"progress\" style=\"font-size:11px;color:#9ca3af;\">Source: his-hand-levers.json ({html_lib.escape(generated_at)}) · triaged = open + needs_human · version {html_lib.escape(version)}</div>
            <button class=\"btn export-btn\" onclick=\"exportDecisions()\">Export Decisions</button>
            <div class=\"toolbar\">
                <button class=\"btn secondary-btn\" onclick=\"document.getElementById('import-input').click()\">Import</button>
                <button class=\"btn secondary-btn\" style=\"background:#dc2626;\" onclick=\"clearAll()\">Clear</button>
            </div>
            <input id=\"import-input\" type=\"file\" accept=\".json,application/json\" style=\"display:none\" onchange=\"importDecisions(event)\">
            <div class=\"help\">Auto-saves to localStorage · Import merges · Clear requires confirm</div>
        </div>
        <div id=\"lever-list\"></div>
    </div>
    <div id=\"main\">
        <div class=\"card\" id=\"detail-view\">
            <h2 style=\"color: #9ca3af; text-align: center; margin-top: 90px;\">Select a lever from the sidebar to begin triage.</h2>
            <p style=\"text-align:center;color:#9ca3af;font-size:13px;\">Tip: triage top-to-bottom — Save auto-advances to next untriaged.</p>
        </div>
    </div>

    <script>
        const levers = {levers_json};
        const categories = {json.dumps(categories)};
        const STORAGE_KEY = 'leverDecisions__{version}';
        const LEGACY_KEY = 'leverDecisions';
        // migrate legacy if versioned is empty
        let _raw = localStorage.getItem(STORAGE_KEY);
        if (!_raw && localStorage.getItem(LEGACY_KEY)) {{
            _raw = localStorage.getItem(LEGACY_KEY);
            localStorage.setItem(STORAGE_KEY, _raw);
        }}
        const decisions = JSON.parse(_raw || '{{}}');
        let currentLeverId = null;

        function escapeHtml(s) {{
            if (!s) return '';
            return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }}

        function updateSidebar() {{
            const list = document.getElementById('lever-list');
            list.innerHTML = '';
            let completed = 0;
            levers.forEach(lv => {{ if (decisions[lv.id] !== undefined) completed++; }});

            categories.forEach(cat => {{
                const catLevers = levers.filter(lv => lv.category === cat);
                const catDone = catLevers.filter(lv => decisions[lv.id] !== undefined).length;
                const header = document.createElement('div');
                header.className = 'category-header';
                header.innerHTML = `<span>${{escapeHtml(cat)}}</span><span>${{catDone}} / ${{catLevers.length}}</span>`;
                list.appendChild(header);

                catLevers.forEach(lv => {{
                    const isCompleted = decisions[lv.id] !== undefined;
                    const div = document.createElement('div');
                    div.className = `lever-item ${{currentLeverId === lv.id ? 'active' : ''}} ${{isCompleted ? 'completed' : ''}}`;
                    div.onclick = () => loadLever(lv.id);
                    const costShort = lv.cost ? lv.cost.substring(0, 48) : '';
                    div.innerHTML = `
                        <div class="lever-id">${{escapeHtml(lv.id)}}</div>
                        <div class="lever-preview">${{escapeHtml(lv.label ? lv.label.substring(0, 62) : '')}}...</div>
                        <div class="lever-meta">${{escapeHtml(costShort)}}${{lv.issue ? ' · #' + lv.issue : ''}}</div>
                    `;
                    list.appendChild(div);
                }});
            }});

            document.getElementById('progress').innerText = `${{completed}} / ${{levers.length}} triaged`;
        }}

        function getHeuristicPros(lv) {{
            if (lv.pros) return lv.pros;
            if (lv.id.includes("TCC") || lv.id.includes("GRANT")) return "Resolves critical permission block; lets agents run autonomously.";
            if (lv.id.includes("ENC")) return "Advances academic progress and gradebook clarity.";
            if (lv.id.includes("LINKEDIN") || lv.id.includes("SOCIAL")) return "Improves public positioning and inbound funnel.";
            if (lv.id.includes("ARCA") || lv.id.includes("CONTAINER")) return "Closes durability/restore gap — one-time durability win.";
            return "Clears blocking debt; unblocks the dependent workflow.";
        }}

        function getHeuristicCons(lv) {{
            if (lv.cons) return lv.cons;
            if (lv.cost) return "Cost: " + lv.cost;
            if (lv.id.includes("TCC")) return "Grants elevated OS permissions; requires careful audit.";
            return "Requires immediate context switching and your manual attention.";
        }}

        function loadLever(id) {{
            currentLeverId = id;
            updateSidebar();
            
            const lv = levers.find(l => l.id === id);
            const saved = decisions[id] || {{ path: '', notes: '' }};
            
            const paths = lv.paths && lv.paths.length ? lv.paths : ["Execute Now (I will do it)", "Delegate to Agent (You do it)", "Defer 30 Days", "Discharge / Ignore"];
            let pathsHtml = '<option value="">-- Select a path --</option>';
            paths.forEach(p => {{
                const selected = saved.path === p ? 'selected' : '';
                pathsHtml += `<option value="${{escapeHtml(p) }}" ${{selected}}>${{escapeHtml(p)}}</option>`;
            }});
            
            const html = `
                <h1>${{escapeHtml(lv.id)}}</h1>
                <div class="badge">${{escapeHtml(lv.status || 'open')}}</div>
                ${{lv.category ? `<div class="badge" style="background:#e0e7ff;color:#3730a3">${{escapeHtml(lv.category)}}</div>` : ''}}
                ${{lv.cost ? `<div class="badge" style="background:#e0e7ff;color:#3730a3">Cost: ${{escapeHtml(lv.cost)}}</div>` : ''}}
                ${{lv.issue ? `<div class="badge">#${{lv.issue}}</div>` : ''}}
                
                <div class="detail-meta">
                    <p><strong>Label:</strong> ${{escapeHtml(lv.label || '')}}</p>
                    ${{lv.note ? `<p><strong>Note:</strong> ${{escapeHtml(lv.note)}}</p>` : ''}}
                    ${{lv.unlocks ? `<p><strong>Unlocks:</strong> ${{escapeHtml(lv.unlocks)}}</p>` : ''}}
                    ${{lv.gate ? `<p><strong>Gate:</strong> ${{escapeHtml(lv.gate)}}</p>` : ''}}
                    ${{lv.source_task ? `<p><strong>Source:</strong> ${{escapeHtml(lv.source_task)}}</p>` : ''}}
                </div>
                
                <div class="pro-con">
                    <div class="pros">
                        <h4>Pros (Acting Now)</h4>
                        <p style="font-size:13px;">${{escapeHtml(getHeuristicPros(lv))}}</p>
                    </div>
                    <div class="cons">
                        <h4>Cons / Risks</h4>
                        <p style="font-size:13px;">${{escapeHtml(getHeuristicCons(lv))}}</p>
                    </div>
                </div>
                
                <h3>Decision Triage</h3>
                <label><strong>Potential Path:</strong></label>
                <select id="path-select">
                    ${{pathsHtml}}
                </select>
                
                <label style="display:block; margin-top: 14px;"><strong>Notes / Answers / Commands:</strong></label>
                <textarea id="notes-area" placeholder="Type your answers, choices, or commands for the agent here...">${{escapeHtml(saved.notes || '')}}</textarea>
                <div class="help">Saved per-lever in localStorage ({html_lib.escape(version)}). Use Export to hand <code>lever-triage-results.json</code> to the agent.</div>
                
                <button class="btn" onclick="saveDecision()">Save Triage</button>
            `;
            
            document.getElementById('detail-view').innerHTML = html;
        }}

        function saveDecision() {{
            if (!currentLeverId) return;
            const path = document.getElementById('path-select').value;
            const notes = document.getElementById('notes-area').value;
            
            decisions[currentLeverId] = {{
                id: currentLeverId,
                path: path,
                notes: notes,
                timestamp: new Date().toISOString()
            }};
            
            localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions));
            // keep legacy in sync for older tooling
            localStorage.setItem(LEGACY_KEY, JSON.stringify(decisions));
            updateSidebar();
            
            const currentIndex = levers.findIndex(l => l.id === currentLeverId);
            for (let i = currentIndex + 1; i < levers.length; i++) {{
                if (!decisions[levers[i].id]) {{
                    loadLever(levers[i].id);
                    return;
                }}
            }}
        }}

        function exportDecisions() {{
            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(decisions, null, 2));
            const dlAnchorElem = document.createElement('a');
            dlAnchorElem.setAttribute("href", dataStr);
            dlAnchorElem.setAttribute("download", "lever-triage-results.json");
            dlAnchorElem.click();
        }}

        function importDecisions(event) {{
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (e) => {{
                try {{
                    const imported = JSON.parse(e.target.result);
                    let count = 0;
                    for (const [k, v] of Object.entries(imported)) {{
                        if (v && typeof v === 'object' && v.path !== undefined) {{
                            decisions[k] = v;
                            count++;
                        }}
                    }}
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(decisions));
                    localStorage.setItem(LEGACY_KEY, JSON.stringify(decisions));
                    updateSidebar();
                    alert(`Imported ${{count}} decisions.`);
                }} catch (err) {{
                    alert('Import failed: ' + err.message);
                }}
            }};
            reader.readAsText(file);
            event.target.value = '';
        }}

        function clearAll() {{
            if (!confirm('Clear all triage decisions in localStorage (' + STORAGE_KEY + ')? This cannot be undone — export first if needed.')) return;
            for (const k of [STORAGE_KEY, LEGACY_KEY]) localStorage.removeItem(k);
            for (const k of Object.keys(decisions)) delete decisions[k];
            updateSidebar();
            document.getElementById('detail-view').innerHTML = '<h2 style="color: #9ca3af; text-align: center; margin-top: 90px;">Select a lever from the sidebar to begin triage.</h2>';
        }}

        updateSidebar();
    </script>
</body>
</html>
"""


def main():
    p = argparse.ArgumentParser(description="Generate lever-triage.html")
    p.add_argument("--in", dest="inp", default=DEFAULT_IN, help="Input his-hand-levers.json path")
    p.add_argument("--out", dest="out", default=DEFAULT_OUT, help="Output HTML path")
    p.add_argument("--enriched", default=None, help="Optional his-hand-levers-enriched.json to merge pros/cons/paths")
    args = p.parse_args()

    inp = pathlib.Path(args.inp)
    out = pathlib.Path(args.out)
    enriched = pathlib.Path(args.enriched) if args.enriched else None

    data, levers_all, triaged, generated_at, counts = load_levers(inp, enriched)

    total_all = len(levers_all)
    total_triaged = len(triaged)
    print(f"Loaded {total_all} levers from {inp} (generated_at={generated_at or 'unknown'})")
    print(f"Triaged set (open + needs_human): {total_triaged}")
    for cat, n in sorted(counts.items()):
        print(f"  {cat}: {n}")
    if enriched and enriched.exists():
        print(f"Merged enriched: {enriched}")
    else:
        print("Heuristic pros/cons (no enriched)")

    html = build_html(triaged, generated_at)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
