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
}

interface StatusData {
  portal: { name: string; budget?: { daily: number; track?: { spent: number } } };
  tasks: Task[];
  summary: { total: number; by_status: Record<string, number>; by_agent: Record<string, number> };
}

export default function Home() {
  const [data, setData] = useState<StatusData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/tasks.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((raw) => {
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
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div style={{ color: "red" }}>Error: {error}</div>;
  if (!data) return <div>Loading...</div>;

  const budget = data.portal.budget || { daily: 100, track: { spent: 0 } };
  const spent = budget.track?.spent ?? 0;
  const pct = Math.round((spent / budget.daily) * 100);

  const statusColors: Record<string, string> = {
    open: "#3b82f6",
    dispatched: "#f59e0b",
    in_progress: "#8b5cf6",
    done: "#22c55e",
    failed: "#ef4444",
  };

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0 0 0.25rem" }}>
        {data.portal.name || "limen"}
      </h1>
      <p style={{ color: "#666", margin: "0 0 1.5rem" }}>
        {data.summary.total} tasks | {spent}/{budget.daily} budget used
      </p>

      <div
        style={{
          height: 8,
          background: "#e5e7eb",
          borderRadius: 4,
          marginBottom: "1.5rem",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: pct > 80 ? "#ef4444" : "#22c55e",
            borderRadius: 4,
            transition: "width 0.3s",
          }}
        />
      </div>

      <div style={{ display: "flex", gap: "1rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        {Object.entries(data.summary.by_status).map(([s, c]) => (
          <div
            key={s}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: 8,
              background: statusColors[s] || "#e5e7eb",
              color: "#fff",
              fontWeight: 600,
              fontSize: "0.875rem",
            }}
          >
            {s}: {c}
          </div>
        ))}
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff", borderRadius: 8, overflow: "hidden" }}>
        <thead>
          <tr style={{ background: "#f9fafb", textAlign: "left" }}>
            <th style={{ padding: "0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", color: "#666" }}>ID</th>
            <th style={{ padding: "0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", color: "#666" }}>Title</th>
            <th style={{ padding: "0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", color: "#666" }}>Agent</th>
            <th style={{ padding: "0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", color: "#666" }}>Status</th>
            <th style={{ padding: "0.75rem", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", color: "#666" }}>Budget</th>
          </tr>
        </thead>
        <tbody>
          {data.tasks.map((t) => (
            <tr key={t.id} style={{ borderTop: "1px solid #e5e7eb" }}>
              <td style={{ padding: "0.75rem", fontWeight: 600, fontFamily: "monospace", fontSize: "0.875rem" }}>{t.id}</td>
              <td style={{ padding: "0.75rem", fontSize: "0.875rem", maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</td>
              <td style={{ padding: "0.75rem", fontSize: "0.875rem" }}>
                <span style={{ background: "#e5e7eb", padding: "0.125rem 0.5rem", borderRadius: 4, fontSize: "0.75rem" }}>
                  {t.target_agent}
                </span>
              </td>
              <td style={{ padding: "0.75rem" }}>
                <span
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: statusColors[t.status] || "#e5e7eb",
                    marginRight: 4,
                  }}
                />
                {t.status}
              </td>
              <td style={{ padding: "0.75rem", fontSize: "0.875rem" }}>{t.budget_cost}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
