"use client";

import { useEffect, useState } from "react";
import DashboardClient, { type DashboardData, type IssueStatusData, type PRStatusData, type RepoHealthData, type Task } from "./dashboard-client";
import SurfaceNav from "./surface-nav";

type LoadState = {
  loading: boolean;
  error: string;
  data: DashboardData | null;
};

async function readOptionalJson(path: string) {
  const response = await fetch(path).catch(() => null);
  return response && response.ok ? response.json() : null;
}

export default function AuthenticatedDashboard({ apiUrl }: { apiUrl: string }) {
  const [token, setToken] = useState("");
  const [state, setState] = useState<LoadState>({ loading: false, error: "", data: null });
  const [prData, setPrData] = useState<PRStatusData | null>(null);
  const [issueData, setIssueData] = useState<IssueStatusData | null>(null);
  const [repoHealthData, setRepoHealthData] = useState<RepoHealthData | null>(null);
  const [doneTasks, setDoneTasks] = useState<Task[] | null>(null);
  const [doneLoading, setDoneLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    const pull = async () => {
      try {
        const [dashboardRes, pr, issues, repoHealth] = await Promise.all([
          fetch("/dashboard.json"),
          readOptionalJson("/pr-status.json"),
          readOptionalJson("/issue-status.json"),
          readOptionalJson("/repo-health.json"),
        ]);
        if (!dashboardRes.ok) return;
        const dashboard = await dashboardRes.json();
        if (!alive) return;
        setPrData(pr);
        setIssueData(issues);
        setRepoHealthData(repoHealth);
        setState({
          loading: false,
          error: "",
          data: {
            version: "static",
            portal: dashboard.portal || { name: "Limen", description: "" },
            tasks: dashboard.tasks || [],
            summary: dashboard.summary,
            storage: dashboard.storage,
          },
        });
      } catch {
        // fall back to the runtime gate below
      }
    };
    pull();
    const id = setInterval(pull, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  async function loadDoneTasks() {
    if (doneLoading || doneTasks !== null) return;
    setDoneLoading(true);
    try {
      const res = await fetch("/done-tasks.json");
      if (res.ok) {
        const payload = await res.json();
        setDoneTasks(payload.tasks || []);
      }
    } catch {
      // ignore
    } finally {
      setDoneLoading(false);
    }
  }

  async function load() {
    if (!apiUrl || state.loading) return;
    setState({ loading: true, error: "", data: null });
    try {
      const headers: Record<string, string> = token ? { Authorization: "Bearer " + token } : {};
      const optionalFetch = (path: string) => fetch(`${apiUrl}${path}`, { headers }).catch(() => null);
      const [statusResponse, tasksResponse, prResponse, issueResponse, repoHealthResponse] = await Promise.all([
        fetch(`${apiUrl}/api/status`, { headers }),
        fetch(`${apiUrl}/api/tasks`, { headers }),
        optionalFetch("/api/pr-status"),
        optionalFetch("/api/issue-status"),
        optionalFetch("/api/repo-health"),
      ]);
      const payload = await statusResponse.json();
      if (!statusResponse.ok) throw new Error(payload.detail || statusResponse.statusText);
      const tasksPayload = await tasksResponse.json();
      if (!tasksResponse.ok) throw new Error(tasksPayload.detail || tasksResponse.statusText);
      setPrData(prResponse && prResponse.ok ? await prResponse.json() : null);
      setIssueData(issueResponse && issueResponse.ok ? await issueResponse.json() : null);
      setRepoHealthData(repoHealthResponse && repoHealthResponse.ok ? await repoHealthResponse.json() : null);
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
    return (
      <DashboardClient
        data={state.data}
        prData={prData}
        issueData={issueData}
        repoHealthData={repoHealthData}
        apiUrl={apiUrl}
        initialToken={token}
        doneTasks={doneTasks}
        doneLoading={doneLoading}
        onLoadDoneTasks={loadDoneTasks}
      />
    );
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
