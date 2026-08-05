"use client";

import { useEffect, useState } from "react";
import DashboardClient, { type DashboardData, type PRStatusData, type Task } from "./dashboard-client";
import SurfaceNav from "./surface-nav";

type LoadState = {
  loading: boolean;
  error: string;
  data: DashboardData | null;
};

export default function AuthenticatedDashboard({ apiUrl }: { apiUrl: string }) {
  const [token, setToken] = useState("");
  const [state, setState] = useState<LoadState>({ loading: false, error: "", data: null });
  const [prData, setPrData] = useState<PRStatusData | null>(null);
  const [doneTasks, setDoneTasks] = useState<Task[] | null>(null);
  const [doneLoading, setDoneLoading] = useState(false);

  // STATIC-FIRST (detach-safe): render the baked dashboard.json directly — no runtime
  // needed. The daemon's web voice regenerates it each cycle, so it stays near-real-time.
  // dashboard.json is slim (active tasks only); done-tasks.json is lazy-fetched on demand.
  useEffect(() => {
    let alive = true;
    const pull = async () => {
      try {
        const res = await fetch("/dashboard.json");
        if (!res.ok) return;
        const d = await res.json();
        const prRes = await fetch("/pr-status.json").catch(() => null);
        const pr = prRes && prRes.ok ? await prRes.json() : null;
        if (!alive) return;
        if (pr) setPrData(pr);
        setState({ loading: false, error: "", data: {
          version: "static", portal: d.portal || { name: "Limen", description: "" },
          tasks: d.tasks || [], summary: d.summary, storage: d.storage } });
      } catch { /* fall back to the runtime gate below */ }
    };
    pull();
    const id = setInterval(pull, 60000);  // live: re-pull every 60s (ETag/304 friendly)
    return () => { alive = false; clearInterval(id); };
  }, []);

  // Lazy-fetch done tasks only when requested (avoids loading them on every page load).
  async function loadDoneTasks() {
    if (doneLoading || doneTasks !== null) return;
    setDoneLoading(true);
    try {
      const res = await fetch("/done-tasks.json");
      if (res.ok) {
        const d = await res.json();
        setDoneTasks(d.tasks || []);
      }
    } catch { /* ignore */ } finally {
      setDoneLoading(false);
    }
  }

  async function load() {
    if (!apiUrl || state.loading) return;
    setState({ loading: true, error: "", data: null });
    try {
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const [statusResponse, tasksResponse] = await Promise.all([
        fetch(`${apiUrl}/api/status`, { headers }),
        fetch(`${apiUrl}/api/tasks`, { headers }),
      ]);
      const payload = await statusResponse.json();
      if (!statusResponse.ok) throw new Error(payload.detail || statusResponse.statusText);
      const tasksPayload = await tasksResponse.json();
      if (!tasksResponse.ok) throw new Error(tasksPayload.detail || tasksResponse.statusText);
      setState({
        loading: false,
        error: "",
        data: {
          version: "runtime",
          portal: payload.portal || { name: "Limen", description: "" },
          tasks: tasksPayload.tasks || [],
          summary: payload.summary,
          storage: payload.storage,
        },
      });
    } catch (error) {
      setState({ loading: false, error: error instanceof Error ? error.message : "Internal load failed", data: null });
    }
  }

  if (state.data) {
    return <DashboardClient
      data={state.data}
      prData={prData}
      apiUrl={apiUrl}
      initialToken={token}
      doneTasks={doneTasks}
      doneLoading={doneLoading}
      onLoadDoneTasks={loadDoneTasks}
    />;
  }

  return (
    <main className="audienceShell authShell">
      <SurfaceNav active="internal" />
      <header className="audienceHeader qaHeader">
        <p className="caption">Internal Surface</p>
        <h1>Owner access</h1>
        <p>Internal operations load from the runtime after owner authorization.</p>
      </header>
      <section className="surfacePanel authPanel">
        <div className="panelTitle">
          <span>Runtime</span>
          <strong>{apiUrl ? "Owner token required" : "Runtime unavailable"}</strong>
        </div>
        <div className="assignPanel">
          <label>
            <span>Token</span>
            <input value={token} onChange={(event) => setToken(event.target.value)} type="password" disabled={!apiUrl} />
          </label>
          <button onClick={load} disabled={!apiUrl || state.loading}>
            {state.loading ? "Loading" : "Load internal"}
          </button>
          {!apiUrl && <p>Build with NEXT_PUBLIC_API_URL to enable the internal surface.</p>}
          {state.error && <p className="opsError">{state.error}</p>}
        </div>
      </section>
    </main>
  );
}
