import json

with open("his-hand-levers.json", "r") as f:
    data = json.load(f)

levers = [lv for lv in data.get("levers", []) if lv.get("status", "open").lower() in ("open", "", "needs_human")]
levers_json = json.dumps(levers)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Human Levers Triage Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            height: 100vh;
            background-color: #f3f4f6;
            color: #1f2937;
        }}
        #sidebar {{
            width: 350px;
            background-color: #ffffff;
            border-right: 1px solid #e5e7eb;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }}
        .sidebar-header {{
            padding: 20px;
            border-bottom: 1px solid #e5e7eb;
            background-color: #f9fafb;
            position: sticky;
            top: 0;
        }}
        .lever-item {{
            padding: 15px 20px;
            border-bottom: 1px solid #e5e7eb;
            cursor: pointer;
            transition: background-color 0.2s;
        }}
        .lever-item:hover {{
            background-color: #f9fafb;
        }}
        .lever-item.active {{
            background-color: #eff6ff;
            border-left: 4px solid #3b82f6;
        }}
        .lever-item.completed {{
            opacity: 0.7;
        }}
        .lever-item.completed .lever-id::after {{
            content: " ✓";
            color: #10b981;
        }}
        .lever-id {{
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 4px;
        }}
        .lever-preview {{
            font-size: 12px;
            color: #6b7280;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        #main {{
            flex: 1;
            padding: 40px;
            overflow-y: auto;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            max-width: 800px;
            margin: 0 auto;
        }}
        h1 {{ margin-top: 0; font-size: 24px; }}
        h3 {{ margin-top: 24px; font-size: 16px; color: #4b5563; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }}
        .badge {{
            display: inline-block;
            background: #f3f4f6;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            color: #4b5563;
            margin-right: 8px;
            margin-bottom: 16px;
        }}
        .pro-con {{
            display: flex;
            gap: 20px;
            margin-top: 16px;
        }}
        .pro-con > div {{
            flex: 1;
            padding: 16px;
            border-radius: 6px;
        }}
        .pros {{ background-color: #ecfdf5; border: 1px solid #a7f3d0; }}
        .cons {{ background-color: #fef2f2; border: 1px solid #fecaca; }}
        .pros h4 {{ color: #059669; margin-top:0; }}
        .cons h4 {{ color: #dc2626; margin-top:0; }}
        
        select, textarea {{
            width: 100%;
            padding: 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            margin-top: 8px;
            font-family: inherit;
        }}
        textarea {{
            height: 120px;
            resize: vertical;
        }}
        .btn {{
            background-color: #3b82f6;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            margin-top: 16px;
        }}
        .btn:hover {{ background-color: #2563eb; }}
        .export-btn {{
            width: 100%;
            background-color: #10b981;
            margin-top: 16px;
        }}
        .export-btn:hover {{ background-color: #059669; }}
    </style>
</head>
<body>
    <div id="sidebar">
        <div class="sidebar-header">
            <h2>Human Levers</h2>
            <div id="progress">0 / {len(levers)} triaged</div>
            <button class="btn export-btn" onclick="exportDecisions()">Export Decisions</button>
        </div>
        <div id="lever-list"></div>
    </div>
    <div id="main">
        <div class="card" id="detail-view">
            <h2 style="color: #9ca3af; text-align: center; margin-top: 100px;">Select a lever from the sidebar to begin triage.</h2>
        </div>
    </div>

    <script>
        const levers = {levers_json};
        const decisions = JSON.parse(localStorage.getItem('leverDecisions') || '{{}}');
        let currentLeverId = null;

        function updateSidebar() {{
            const list = document.getElementById('lever-list');
            list.innerHTML = '';
            let completed = 0;
            
            levers.forEach(lv => {{
                const isCompleted = decisions[lv.id] !== undefined;
                if (isCompleted) completed++;
                
                const div = document.createElement('div');
                div.className = `lever-item ${{currentLeverId === lv.id ? 'active' : ''}} ${{isCompleted ? 'completed' : ''}}`;
                div.onclick = () => loadLever(lv.id);
                
                div.innerHTML = `
                    <div class="lever-id">${{lv.id}}</div>
                    <div class="lever-preview">${{lv.label ? lv.label.substring(0, 60) : ''}}...</div>
                `;
                list.appendChild(div);
            }});
            
            document.getElementById('progress').innerText = `${{completed}} / ${{levers.length}} triaged`;
        }}

        function getHeuristicPros(lv) {{
            if (lv.id.includes("TCC") || lv.id.includes("GRANT")) return "Resolves critical permission block; allows agents to run autonomously.";
            if (lv.id.includes("ENC")) return "Advances academic progress and gradebook clarity.";
            if (lv.id.includes("LINKEDIN") || lv.id.includes("SOCIAL")) return "Improves public positioning and inbound funnel.";
            return "Clears blocking debt; allows the dependent workflow to proceed autonomously.";
        }}

        function getHeuristicCons(lv) {{
            if (lv.cost) return "Cost: " + lv.cost;
            if (lv.id.includes("TCC")) return "Grants elevated permissions to the system; requires careful audit.";
            return "Requires immediate context switching and your manual attention.";
        }}

        function loadLever(id) {{
            currentLeverId = id;
            updateSidebar();
            
            const lv = levers.find(l => l.id === id);
            const saved = decisions[id] || {{ path: '', notes: '' }};
            
            const paths = ["Execute Now (I will do it)", "Delegate to Agent (You do it)", "Defer 30 Days", "Discharge / Ignore"];
            let pathsHtml = '<option value="">-- Select a path --</option>';
            paths.forEach(p => {{
                const selected = saved.path === p ? 'selected' : '';
                pathsHtml += `<option value="${{p}}" ${{selected}}>${{p}}</option>`;
            }});
            
            const html = `
                <h1>${{lv.id}}</h1>
                <div class="badge">${{lv.status || 'Open'}}</div>
                ${{lv.cost ? `<div class="badge" style="background:#e0e7ff;color:#3730a3">Cost: ${{lv.cost}}</div>` : ''}}
                
                <p><strong>Label:</strong> ${{lv.label || ''}}</p>
                <p><strong>Note:</strong> ${{lv.note || ''}}</p>
                
                <div class="pro-con">
                    <div class="pros">
                        <h4>Pros (Acting Now)</h4>
                        <p>${{getHeuristicPros(lv)}}</p>
                    </div>
                    <div class="cons">
                        <h4>Cons / Risks</h4>
                        <p>${{getHeuristicCons(lv)}}</p>
                    </div>
                </div>
                
                <h3>Decision Triage</h3>
                <label><strong>Potential Path:</strong></label>
                <select id="path-select">
                    ${{pathsHtml}}
                </select>
                
                <label style="display:block; margin-top: 16px;"><strong>Notes / Answers / Commands:</strong></label>
                <textarea id="notes-area" placeholder="Type your answers, choices, or commands for the agent here...">${{saved.notes || ''}}</textarea>
                
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
            
            localStorage.setItem('leverDecisions', JSON.stringify(decisions));
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

        updateSidebar();
    </script>
</body>
</html>
"""
with open("lever-triage.html", "w") as f:
    f.write(html)
print("lever-triage.html generated successfully!")
