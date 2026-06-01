"use client";

import React, { useEffect, useState } from "react";

interface Task {
  id: string;
  title: string;
  repo: string;
  target_agent: string;
  priority: string;
  budget_cost: number;
  status: string;
  labels: string[];
  context?: string;
  created?: string;
  updated?: string;
  urls?: string[];
  dispatch_log?: any[];
}

interface PRCheck {
  total: number;
  failed: number;
  passed: number;
  pending: number;
}

interface PR {
  number: number;
  title: string;
  author: string;
  draft: boolean;
  head: string;
  base: string;
  html_url: string;
  checks: PRCheck | null;
  labels: string[];
}

interface RepoStatus {
  repo: string;
  prs: PR[];
  count: number;
}

interface PRStatusData {
  generated_at: string;
  repos: RepoStatus[];
  summary: {
    total_repos: number;
    total_open_prs: number;
    prs_with_failing_ci: number;
  };
}

interface StatusData {
  portal: { name: string; budget?: { daily: number; track?: { spent: number; per_agent?: Record<string, number> } } };
  tasks: Task[];
  summary: { total: number; by_status: Record<string, number>; by_agent: Record<string, number> };
}

const LIFECYCLE_PHASES = ["EXPLORE", "PLAN", "BUILD", "VERIFY", "LEARN", "REPEAT"] as const;
type LifecyclePhase = typeof LIFECYCLE_PHASES[number];

const statusColors: Record<string, string> = {
  open: "#3b82f6",
  dispatched: "#f59e0b",
  in_progress: "#8b5cf6",
  done: "#22c55e",
  failed: "#ef4444",
  superseded: "#94a3b8",
  failed_blocked: "#ef4444",
  needs_human: "#f43f5e",
};

const agentColors: Record<string, string> = {
  jules: "#6366f1",
  claude: "#f97316",
  gemini: "#06b6d4",
  any: "#94a3b8",
};

function shortRepo(repo: string) {
  return repo.split("/").pop() || repo;
}

// Map task status and PR state to Lifecycle Phase
function getPhase(task: Task, prs: PR[]): LifecyclePhase {
  const hasOpenPR = prs.length > 0;
  if (["failed", "superseded", "failed_blocked"].includes(task.status)) return "REPEAT";
  if (task.status === "done") return "LEARN";
  if (hasOpenPR && task.status === "in_progress") return "VERIFY";
  if (task.status === "in_progress") return "BUILD";
  if (task.status === "dispatched") return "PLAN";
  return "EXPLORE"; // open or needs_human
}

function getProgress(phase: LifecyclePhase): number {
  switch (phase) {
    case "EXPLORE": return 15;
    case "PLAN": return 30;
    case "BUILD": return 50;
    case "VERIFY": return 75;
    case "LEARN": return 90;
    case "REPEAT": return 100;
    default: return 0;
  }
}

export default function Home() {
  const [data, setData] = useState<StatusData | null>(null);
  const [prData, setPrData] = useState<PRStatusData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<LifecyclePhase>("EXPLORE");
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

  useEffect(() => {
    Promise.all([
      fetch("/tasks.json").then((r) => r.json()),
      fetch("/pr-status.json").then((r) => r.ok ? r.json() : null).catch(() => null),
    ])
      .then(([raw, prRaw]) => {
        const tasks = (raw.tasks || []).map((t: any) => ({
          ...t,
          target_agent: t.target_agent || "any",
        }));
        const by_status: Record<string, number> = {};
        const by_agent: Record<string, number> = {};
        for (const t of tasks) {
          by_status[t.status] = (by_status[t.status] || 0) + 1;
          by_agent[t.target_agent] = (by_agent[t.target_agent] || 0) + 1;
        }
        setData({
          portal: raw.portal || { name: "limen" },
          tasks,
          summary: { total: tasks.length, by_status, by_agent },
        });
        if (prRaw) setPrData(prRaw);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div style={{ color: "red", padding: 24 }}>Error: {error}</div>;
  if (!data) return <div style={{ padding: 24, color: "#666" }}>Loading...</div>;

  const budget = data.portal.budget || { daily: 100, track: { spent: 0 } };
  const spent = budget.track?.spent ?? 0;
  const pct = Math.round((spent / budget.daily) * 100);
  const perAgent = budget.track?.per_agent || {};

  const prsByRepo: Record<string, PR[]> = {};
  if (prData) {
    for (const r of prData.repos) {
      prsByRepo[r.repo] = r.prs;
    }
  }

  const getPRsForTask = (task: Task) => {
    const repoPRs = prsByRepo[task.repo] || [];
    const prUrls = task.urls?.filter(u => u.includes("/pull/")) || [];
    if (prUrls.length > 0) {
      return repoPRs.filter(pr => prUrls.includes(pr.html_url));
    }
    return repoPRs.filter(pr => pr.author === "4444J99");
  };

  const tasksWithPhase = data.tasks.map(t => {
    const prs = getPRsForTask(t);
    return { ...t, phase: getPhase(t, prs), relatedPRs: prs };
  });

  const filteredTasks = tasksWithPhase.filter(t => t.phase === tab);

  const toggleRow = (id: string) => {
    setExpandedRows(prev => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: "1rem", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>
          <a href="/" style={{ color: "inherit", textDecoration: "none" }}>{data.portal.name || "limen"}</a>
        </h1>
        <p style={{ color: "#666", margin: "0.25rem 0 0", fontSize: "0.875rem" }}>
          {data.summary.total} tasks &middot;{" "}
          <span style={{ color: "inherit" }}>{spent}/{budget.daily} budget</span>
        </p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.75rem", marginBottom: "1.5rem" }}>
        <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", border: "1px solid #e5e7eb" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#666", fontWeight: 600 }}>Budget</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{pct}%</div>
          <div style={{ height: 4, background: "#e5e7eb", borderRadius: 2, marginTop: 4 }}>
            <div style={{ width: \`\${pct}%\`, height: "100%", background: pct > 80 ? "#ef4444" : "#22c55e", borderRadius: 2 }} />
          </div>
          <div style={{ fontSize: "0.75rem", color: "#999", marginTop: 4 }}>
            {Object.entries(perAgent).map(([a, c]) => \`\${a}: \${c}\`).join(" | ")}
          </div>
        </div>

        <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", border: "1px solid #e5e7eb" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#666", fontWeight: 600 }}>Tasks by Status</div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
            {Object.entries(data.summary.by_status).map(([s, c]) => (
              <span key={s} style={{ background: statusColors[s] || "#e5e7eb", color: "#fff", padding: "0.125rem 0.5rem", borderRadius: 4, fontSize: "0.75rem", fontWeight: 600 }}>
                {s}: {c}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", borderBottom: "2px solid #e5e7eb", paddingBottom: 0, overflowX: "auto" }}>
        {LIFECYCLE_PHASES.map((t) => {
          const count = tasksWithPhase.filter(x => x.phase === t).length;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: "0.5rem 1rem",
                border: "none",
                borderBottom: tab === t ? "2px solid #111" : "2px solid transparent",
                background: "none",
                fontWeight: tab === t ? 700 : 400,
                fontSize: "0.875rem",
                cursor: "pointer",
                marginBottom: -2,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                whiteSpace: "nowrap"
              }}
            >
              {t} ({count})
            </button>
          );
        })}
      </div>

      <div style={{ background: "#fff", borderRadius: 8, overflow: "hidden", border: "1px solid #e5e7eb" }}>
        {filteredTasks.length === 0 ? (
          <p style={{ color: "#666", textAlign: "center", padding: "2rem" }}>No tasks in this phase.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f9fafb", textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                <th style={thStyle}>ID</th>
                <th style={thStyle}>Title & Progress</th>
                <th style={thStyle}>Repo</th>
                <th style={thStyle}>Agent</th>
                <th style={thStyle}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredTasks.map((t) => {
                const isExpanded = expandedRows[t.id];
                const prog = getProgress(t.phase);
                return (
                  <React.Fragment key={t.id}>
                    <tr 
                      onClick={() => toggleRow(t.id)} 
                      style={{ borderBottom: "1px solid #e5e7eb", cursor: "pointer", background: isExpanded ? "#f8fafc" : "transparent" }}
                    >
                      <td style={tdStyle}>
                        {t.urls?.[0] ? (
                          <a href={t.urls[0]} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()} style={{ fontFamily: "monospace", fontWeight: 600, color: "#2563eb", textDecoration: "none" }}>{t.id}</a>
                        ) : (
                          <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{t.id}</span>
                        )}
                      </td>
                      <td style={{ ...tdStyle, maxWidth: 400 }}>
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 4, fontWeight: 500 }}>
                          {t.title}
                        </div>
                        <div style={{ height: 4, background: "#e5e7eb", borderRadius: 2 }}>
                          <div style={{ width: \`\${prog}%\`, height: "100%", background: "#3b82f6", borderRadius: 2 }} />
                        </div>
                      </td>
                      <td style={{ ...tdStyle, fontSize: "0.75rem", color: "#666" }}>
                        <a href={\`https://github.com/\${t.repo}\`} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()} style={{ color: "inherit", textDecoration: "none" }}>{shortRepo(t.repo)}</a>
                      </td>
                      <td style={tdStyle}>
                        <span style={{ background: agentColors[t.target_agent] || "#e5e7eb", color: "#fff", padding: "0.125rem 0.5rem", borderRadius: 4, fontSize: "0.75rem" }}>
                          {t.target_agent}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: statusColors[t.status] || "#e5e7eb", marginRight: 4 }} />
                        {t.status}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e5e7eb" }}>
                        <td colSpan={5} style={{ padding: "1rem" }}>
                          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", fontSize: "0.875rem" }}>
                            
                            {/* Context & Labels */}
                            <div>
                              <strong>Context:</strong> {t.context || "No context provided."}
                              <div style={{ marginTop: 8, display: "flex", gap: 4 }}>
                                {t.labels.map(l => (
                                  <span key={l} style={{ background: "#e2e8f0", color: "#475569", padding: "2px 6px", borderRadius: 4, fontSize: "0.7rem", textTransform: "uppercase" }}>{l}</span>
                                ))}
                              </div>
                            </div>
                            
                            {/* Links */}
                            {t.urls && t.urls.length > 0 && (
                              <div>
                                <strong>Links:</strong>
                                <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
                                  {t.urls.map(u => (
                                    <li key={u}><a href={u} target="_blank" rel="noopener" style={{ color: "#2563eb", textDecoration: "none" }}>{u}</a></li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Related PRs */}
                            {t.relatedPRs.length > 0 && (
                              <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 6, padding: "0.75rem" }}>
                                <strong>Related Pull Requests:</strong>
                                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                                  {t.relatedPRs.map(p => (
                                    <div key={p.number} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: "0.8rem" }}>
                                      <a href={p.html_url} target="_blank" rel="noopener" style={{ color: "#2563eb", textDecoration: "none", fontWeight: 600 }}>#{p.number}</a>
                                      <span>{p.title}</span>
                                      {p.checks ? (
                                        <a href={\`https://github.com/\${p.repo}/pull/\${p.number}/checks\`} target="_blank" rel="noopener" style={{ color: p.checks.failed > 0 ? "#ef4444" : "#22c55e", textDecoration: "none", fontWeight: 600 }}>
                                          {p.checks.failed > 0 ? \`\${p.checks.failed} failed CI\` : \`\${p.checks.passed} passed CI\`}
                                        </a>
                                      ) : <span style={{ color: "#999" }}>no checks</span>}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Dispatch Log */}
                            {t.dispatch_log && t.dispatch_log.length > 0 && (
                              <div style={{ background: "#1e293b", color: "#f8fafc", padding: "1rem", borderRadius: 6, fontFamily: "monospace", fontSize: "0.75rem", maxHeight: 200, overflowY: "auto" }}>
                                {t.dispatch_log.map((log, i) => (
                                  <div key={i} style={{ marginBottom: 8 }}>
                                    <span style={{ color: "#94a3b8" }}>[{new Date(log.timestamp).toISOString().replace("T"," ").substring(0,19)}]</span>{" "}
                                    <span style={{ color: "#60a5fa" }}>[{log.agent}]</span>{" "}
                                    <span style={{ color: statusColors[log.status] || "#fff" }}>{log.status.toUpperCase()}</span>
                                    {log.output && <div style={{ marginTop: 2, paddingLeft: 12, color: "#cbd5e1" }}>{log.output}</div>}
                                  </div>
                                ))}
                              </div>
                            )}
                            
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <footer style={{ marginTop: "2rem", padding: "1rem 0", borderTop: "1px solid #e5e7eb", fontSize: "0.75rem", color: "#999", display: "flex", justifyContent: "space-between" }}>
        <a href="https://device-streaming-067d747a.web.app" target="_blank" rel="noopener" style={{ color: "inherit", textDecoration: "none" }}>device-streaming-067d747a.web.app</a>
        {prData && <span>PR data: {new Date(prData.generated_at).toLocaleString()}</span>}
      </footer>
    </main>
  );
}

const thStyle: React.CSSProperties = {
  padding: "0.75rem",
  fontWeight: 600,
  fontSize: "0.75rem",
  textTransform: "uppercase",
  color: "#666",
};

const tdStyle: React.CSSProperties = {
  padding: "0.75rem",
  fontSize: "0.875rem",
};
