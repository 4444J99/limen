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
  const activeTasks = summary?.active_tasks.slice(0, 10) || [];

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
              <div className="clientTaskList">
                {activeTasks.map((task) => (
                  <article key={task.id}>
                    <span>{task.id}</span>
                    <div>
                      <strong>{task.title}</strong>
                      <p>{repoName(task.repo)} · {task.target_agent} · {task.phase || task.status}</p>
                      {task.next_gate && <em>{task.next_gate}</em>}
                    </div>
                  </article>
                ))}
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
    </main>
  );
}
