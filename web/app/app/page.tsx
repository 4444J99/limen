"use client";

import { useEffect, useState } from "react";

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
  urls?: string[];
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

const statusColors: Record<string, string> = {
  open: "#3b82f6",
  dispatched: "#f59e0b",
  in_progress: "#8b5cf6",
  done: "#22c55e",
  failed: "#ef4444",
  superseded: "#94a3b8",
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

export default function Home() {
  const [data, setData] = useState<StatusData | null>(null);
  const [prData, setPrData] = useState<PRStatusData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"tasks" | "prs">("tasks");

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

  const activeTasks = data.tasks.filter((t) => !["done", "superseded"].includes(t.status));
  const myPRs = prData?.repos.flatMap((r) =>
    r.prs.filter((p) => p.author === "4444J99").map((p) => ({ ...p, repo: r.repo }))
  ) || [];
  const failingPRs = myPRs.filter((p) => p.checks?.failed && p.checks.failed > 0);

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: "1rem", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>
          {data.portal.name || "limen"}
        </h1>
        <p style={{ color: "#666", margin: "0.25rem 0 0", fontSize: "0.875rem" }}>
          {data.summary.total} tasks &middot; {spent}/{budget.daily} budget &middot;{" "}
          {myPRs.length} open PRs{failingPRs.length > 0 && (
            <span style={{ color: "#ef4444" }}> &middot; {failingPRs.length} failing CI</span>
          )}
        </p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.75rem", marginBottom: "1.5rem" }}>
        <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", border: "1px solid #e5e7eb" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#666", fontWeight: 600 }}>Budget</div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{pct}%</div>
          <div style={{ height: 4, background: "#e5e7eb", borderRadius: 2, marginTop: 4 }}>
            <div style={{ width: `${pct}%`, height: "100%", background: pct > 80 ? "#ef4444" : "#22c55e", borderRadius: 2 }} />
          </div>
          <div style={{ fontSize: "0.75rem", color: "#999", marginTop: 4 }}>
            {Object.entries(perAgent).map(([a, c]) => `${a}: ${c}`).join(" | ")}
          </div>
        </div>

        <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", border: "1px solid #e5e7eb" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#666", fontWeight: 600 }}>Tasks</div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
            {Object.entries(data.summary.by_status).map(([s, c]) => (
              <span key={s} style={{ background: statusColors[s] || "#e5e7eb", color: "#fff", padding: "0.125rem 0.5rem", borderRadius: 4, fontSize: "0.75rem", fontWeight: 600 }}>
                {s}: {c}
              </span>
            ))}
          </div>
        </div>

        <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", border: "1px solid #e5e7eb" }}>
          <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#666", fontWeight: 600 }}>Agents</div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
            {Object.entries(data.summary.by_agent).map(([a, c]) => (
              <span key={a} style={{ background: agentColors[a] || "#e5e7eb", color: "#fff", padding: "0.125rem 0.5rem", borderRadius: 4, fontSize: "0.75rem", fontWeight: 600 }}>
                {a}: {c}
              </span>
            ))}
          </div>
        </div>

        {prData && (
          <div style={{ background: "#fff", borderRadius: 8, padding: "1rem", border: "1px solid #e5e7eb" }}>
            <div style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#666", fontWeight: 600 }}>PRs</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{prData.summary.total_open_prs}</div>
            <div style={{ fontSize: "0.75rem", color: "#999" }}>
              across {prData.summary.total_repos} repos
              {prData.summary.prs_with_failing_ci > 0 && (
                <span style={{ color: "#ef4444" }}> &middot; {prData.summary.prs_with_failing_ci} failing</span>
              )}
            </div>
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", borderBottom: "2px solid #e5e7eb", paddingBottom: 0 }}>
        {(["tasks", "prs"] as const).map((t) => (
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
            }}
          >
            {t === "tasks" ? `Tasks (${data.tasks.length})` : `Pull Requests (${myPRs.length})`}
          </button>
        ))}
      </div>

      {tab === "tasks" && (
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", borderRadius: 8, overflow: "hidden", border: "1px solid #e5e7eb" }}>
          <thead>
            <tr style={{ background: "#f9fafb", textAlign: "left" }}>
              <th style={thStyle}>ID</th>
              <th style={thStyle}>Title</th>
              <th style={thStyle}>Repo</th>
              <th style={thStyle}>Agent</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {data.tasks.map((t) => (
              <tr key={t.id} style={{ borderTop: "1px solid #e5e7eb" }}>
                <td style={tdStyle}>
                  <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{t.id}</span>
                </td>
                <td style={{ ...tdStyle, maxWidth: 350, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.urls?.[0] ? (
                    <a href={t.urls[0]} target="_blank" rel="noopener" style={{ color: "#2563eb", textDecoration: "none" }}>{t.title}</a>
                  ) : t.title}
                </td>
                <td style={{ ...tdStyle, fontSize: "0.75rem", color: "#666" }}>{shortRepo(t.repo)}</td>
                <td style={tdStyle}>
                  <span style={{ background: agentColors[t.target_agent] || "#e5e7eb", color: "#fff", padding: "0.125rem 0.5rem", borderRadius: 4, fontSize: "0.75rem" }}>
                    {t.target_agent}
                  </span>
                </td>
                <td style={tdStyle}>
                  <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: statusColors[t.status] || "#e5e7eb", marginRight: 4 }} />
                  {t.status}
                </td>
                <td style={{ ...tdStyle, textAlign: "center" }}>{t.budget_cost}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "prs" && (
        <div>
          {myPRs.length === 0 ? (
            <p style={{ color: "#666", textAlign: "center", padding: "2rem" }}>No open PRs found</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", borderRadius: 8, overflow: "hidden", border: "1px solid #e5e7eb" }}>
              <thead>
                <tr style={{ background: "#f9fafb", textAlign: "left" }}>
                  <th style={thStyle}>PR</th>
                  <th style={thStyle}>Repo</th>
                  <th style={thStyle}>Branch</th>
                  <th style={thStyle}>CI</th>
                </tr>
              </thead>
              <tbody>
                {myPRs.map((p) => (
                  <tr key={`${p.repo}-${p.number}`} style={{ borderTop: "1px solid #e5e7eb" }}>
                    <td style={tdStyle}>
                      <a href={p.html_url} target="_blank" rel="noopener" style={{ color: "#2563eb", textDecoration: "none", fontWeight: 600 }}>
                        #{p.number}
                      </a>{" "}
                      <span style={{ fontSize: "0.875rem" }}>{p.title}</span>
                      {p.draft && <span style={{ background: "#f59e0b", color: "#fff", padding: "0.0625rem 0.375rem", borderRadius: 3, fontSize: "0.625rem", marginLeft: 4 }}>DRAFT</span>}
                    </td>
                    <td style={{ ...tdStyle, fontSize: "0.75rem", color: "#666" }}>{shortRepo(p.repo)}</td>
                    <td style={{ ...tdStyle, fontFamily: "monospace", fontSize: "0.75rem" }}>{p.head}</td>
                    <td style={tdStyle}>
                      {p.checks ? (
                        <span style={{
                          color: p.checks.failed > 0 ? "#ef4444" : "#22c55e",
                          fontWeight: 600,
                          fontSize: "0.75rem",
                        }}>
                          {p.checks.failed > 0 ? `${p.checks.failed} failed` : `${p.checks.passed} passed`}
                          {p.checks.pending > 0 && ` (${p.checks.pending} pending)`}
                        </span>
                      ) : (
                        <span style={{ color: "#999", fontSize: "0.75rem" }}>no checks</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <footer style={{ marginTop: "2rem", padding: "1rem 0", borderTop: "1px solid #e5e7eb", fontSize: "0.75rem", color: "#999", display: "flex", justifyContent: "space-between" }}>
        <span>device-streaming-067d747a.web.app</span>
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
