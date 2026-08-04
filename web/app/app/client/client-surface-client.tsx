"use client";

import { useState } from "react";
import RuntimeStatusPanel from "../runtime-status-panel";
import SurfaceNav from "../surface-nav";
import type { ClientStatusData, ReadinessData, SurfaceManifestData } from "../lib/data";

type LoadState = {
  loading: boolean;
  error: string;
  statusData: ClientStatusData | null;
  manifest: SurfaceManifestData | null;
  readiness: ReadinessData | null;
};

type ClientTask = NonNullable<ClientStatusData["summary"]["active_tasks"]>[number];

function formatDate(value?: string) {
  if (!value) return "Never";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(time));
}

function repoName(repo: string) {
  return repo ? repo.split("/").pop() || repo : "limen";
}

export default function ClientSurfaceClient({ apiUrl }: { apiUrl: string }) {
  const [token, setToken] = useState("");
  const [state, setState] = useState<LoadState>({ loading: false, error: "", statusData: null, manifest: null, readiness: null });
  const [searchQuery, setSearchQuery] = useState("");
  const [phaseFilter, setPhaseFilter] = useState("all");
  const [selectedTask, setSelectedTask] = useState<ClientTask | null>(null);

  async function load() {
    if (!apiUrl || state.loading) return;
    setState({ loading: true, error: "", statusData: null, manifest: null, readiness: null });
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    try {
      const [statusRes, manifestRes] = await Promise.all([
        fetch(`${apiUrl}/api/client-status`, { headers }),
        fetch(`${apiUrl}/api/surface-manifest`, { headers }),
      ]);
      const statusPayload = await statusRes.json();
      const manifestPayload = await manifestRes.json();
      if (!statusRes.ok) throw new Error(statusPayload.detail || statusRes.statusText);
      if (!manifestRes.ok) throw new Error(manifestPayload.detail || manifestRes.statusText);
      setState({ loading: false, error: "", statusData: statusPayload, manifest: manifestPayload, readiness: null });
    } catch (error) {
      setState({ loading: false, error: error instanceof Error ? error.message : "Client load failed", statusData: null, manifest: null, readiness: null });
    }
  }

  const summary = state.statusData?.summary;
  const completion = summary ? Math.round(summary.completion_rate * 100) : 0;
  const allActiveTasks = summary?.active_tasks || [];

  const filteredTasks = allActiveTasks.filter((task) => {
    const matchesSearch =
      task.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      task.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      task.repo.toLowerCase().includes(searchQuery.toLowerCase()) ||
      task.target_agent.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesPhase = phaseFilter === "all" || (task.phase || task.status) === phaseFilter;
    return matchesSearch && matchesPhase;
  });

  return (
    <main className="audienceShell">
      <SurfaceNav active="client" persona="client" />
      <header className="audienceHeader clientHeader">
        <p className="caption">Client Surface</p>
        <h1>{summary?.portal.name || "Universal Task Intake"}</h1>
        <p>Cross-agent delivery status loads after sanctioned client authorization.</p>
      </header>

      {!summary ? (
        <section className="surfacePanel authPanel">
          <div className="panelTitle">
            <span>Access</span>
            <strong>{apiUrl ? "Client token required" : "Runtime unavailable"}</strong>
          </div>
          <div className="assignPanel">
            <label>
              <span>Token</span>
              <input value={token} onChange={(event) => setToken(event.target.value)} type="password" disabled={!apiUrl} />
            </label>
            <button onClick={load} disabled={!apiUrl || state.loading}>
              {state.loading ? "Loading" : "Load client"}
            </button>
            {!apiUrl && <p>Build with NEXT_PUBLIC_API_URL to enable the client surface.</p>}
            {state.error && <p className="opsError">{state.error}</p>}
          </div>
        </section>
      ) : (
        <>
          <section className="audienceMetrics" aria-label="Client delivery metrics">
            <div><span>Task board</span><strong>{summary.total}</strong><p>{summary.active} active tasks</p></div>
            <div><span>Completion</span><strong>{completion}%</strong><p>{summary.completed} closed items</p></div>
            <div><span>Stale</span><strong>{summary.stale_count}</strong><p>Claims awaiting recovery</p></div>
            <div><span>Updated</span><strong>{formatDate(summary.generated_at)}</strong><p>{state.manifest?.persona || "client"} manifest</p></div>
          </section>

          <section className="audienceGrid">
            <div className="surfacePanel wide">
              <div className="panelTitle">
                <span>Delivery focus</span>
                <strong>{summary.stale_count} stale claims require release before capacity recovers</strong>
              </div>

              <div style={{ display: "flex", gap: "0.75rem", margin: "1rem 0", flexWrap: "wrap" }}>
                <input
                  type="text"
                  placeholder="Filter tasks by ID, title, agent, repo..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{ flex: 1, padding: "0.4rem 0.75rem", borderRadius: "6px", border: "1px solid #d1d5db" }}
                />
                <select
                  value={phaseFilter}
                  onChange={(e) => setPhaseFilter(e.target.value)}
                  style={{ padding: "0.4rem 0.75rem", borderRadius: "6px", border: "1px solid #d1d5db" }}
                >
                  <option value="all">All Phases</option>
                  <option value="assign">Assign</option>
                  <option value="verify">Verify</option>
                  <option value="recover">Recover</option>
                  <option value="archive">Archive</option>
                </select>
              </div>

              <div className="clientTaskList">
                {filteredTasks.length === 0 ? (
                  <p style={{ color: "#6b7280", padding: "1rem" }}>No active tasks match current filter.</p>
                ) : (
                  filteredTasks.map((task) => (
                    <article
                      key={task.id}
                      onClick={() => setSelectedTask(task)}
                      style={{ cursor: "pointer" }}
                      title="Click to view task details"
                    >
                      <span>{task.id}</span>
                      <div>
                        <strong>{task.title}</strong>
                        <p>{repoName(task.repo)} · {task.target_agent} · {task.phase || task.status}</p>
                        {task.next_gate && <em>{task.next_gate}</em>}
                      </div>
                    </article>
                  ))
                )}
              </div>
            </div>

            <div className="surfacePanel">
              <div className="panelTitle">
                <span>Lifecycle</span>
                <strong>Current delivery gates</strong>
              </div>
              <ul className="rankList">
                {Object.entries(summary.lifecycle).map(([phase, count]) => (
                  <li key={phase}><span>{phase}</span><strong>{count}</strong></li>
                ))}
              </ul>
            </div>

            <div className="surfacePanel">
              <div className="panelTitle">
                <span>Repos</span>
                <strong>Current workload distribution</strong>
              </div>
              <ul className="rankList">
                {summary.top_repos.slice(0, 6).map((repo) => (
                  <li key={repo.repo}><span>{repoName(repo.repo)}</span><strong>{repo.count}</strong></li>
                ))}
              </ul>
            </div>

            <div className="surfacePanel">
              <RuntimeStatusPanel apiUrl={apiUrl} endpoint="/api/client-status" title="Client runtime refresh" tokenRequired initialToken={token} />
            </div>
          </section>
        </>
      )}

      {selectedTask && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            justifyContent: "flex-end",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#ffffff",
              width: "100%",
              maxWidth: "480px",
              height: "100%",
              padding: "2rem",
              boxShadow: "-4px 0 16px rgba(0,0,0,0.15)",
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
                <h3 style={{ margin: 0 }}>Task Details</h3>
                <button
                  onClick={() => setSelectedTask(null)}
                  style={{ background: "none", border: "none", fontSize: "1.5rem", cursor: "pointer" }}
                >
                  ✕
                </button>
              </div>

              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>TASK ID</span>
                <p style={{ margin: "0.2rem 0 0 0", fontFamily: "monospace", fontSize: "1.1rem", fontWeight: "bold" }}>{selectedTask.id}</p>
              </div>

              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>TITLE</span>
                <p style={{ margin: "0.2rem 0 0 0", fontSize: "1rem", fontWeight: 600 }}>{selectedTask.title}</p>
              </div>

              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>REPOSITORY</span>
                <p style={{ margin: "0.2rem 0 0 0" }}>{selectedTask.repo}</p>
              </div>

              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>TARGET AGENT</span>
                <p style={{ margin: "0.2rem 0 0 0", textTransform: "uppercase", fontWeight: "bold" }}>{selectedTask.target_agent}</p>
              </div>

              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>PRIORITY</span>
                <p style={{ margin: "0.2rem 0 0 0" }}>{selectedTask.priority}</p>
              </div>

              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>PHASE / STATUS</span>
                <p style={{ margin: "0.2rem 0 0 0" }}>{selectedTask.phase || selectedTask.status}</p>
              </div>

              <div style={{ marginBottom: "1.25rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>STALE STATUS</span>
                <p style={{ margin: "0.2rem 0 0 0", color: selectedTask.stale ? "#dc2626" : "#16a34a", fontWeight: "bold" }}>
                  {selectedTask.stale ? "Stale Claim (Awaiting Recovery)" : "Active & Healthy"}
                </p>
              </div>

              {selectedTask.next_gate && (
                <div style={{ marginBottom: "1.25rem" }}>
                  <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 600 }}>NEXT GATE</span>
                  <p style={{ margin: "0.2rem 0 0 0", background: "#f3f4f6", padding: "0.5rem", borderRadius: "4px", fontFamily: "monospace", fontSize: "0.85rem" }}>
                    {selectedTask.next_gate}
                  </p>
                </div>
              )}
            </div>

            <button
              onClick={() => setSelectedTask(null)}
              style={{
                width: "100%",
                padding: "0.75rem",
                borderRadius: "6px",
                border: "1px solid #d1d5db",
                background: "#f9fafb",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Close Drawer
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
