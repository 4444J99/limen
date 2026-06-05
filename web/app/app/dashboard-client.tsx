"use client";

import React, { useMemo, useState } from "react";
import SurfaceNav from "./surface-nav";

export interface Task {
  id: string;
  title: string;
  repo: string;
  target_agent: string;
  priority: string;
  budget_cost: number;
  status: string;
  labels?: string[];
  context?: string;
  created?: string;
  updated?: string;
  urls?: string[];
  dispatch_log?: DispatchEvent[];
}

export interface DispatchEvent {
  timestamp: string;
  agent: string;
  session_id?: string;
  status: string;
  output?: string;
  task_id?: string;
  task_title?: string;
  repo?: string;
}

export interface PRCheck {
  total: number;
  failed: number;
  passed: number;
  pending: number;
}

export interface PR {
  number: number;
  title: string;
  author: string;
  draft: boolean;
  head: string;
  base: string;
  html_url: string;
  checks: PRCheck | null;
  labels: string[];
  created_at?: string;
  updated_at?: string;
}

export interface RepoStatus {
  repo: string;
  prs: PR[];
  count: number;
}

export interface PRStatusData {
  generated_at: string;
  repos: RepoStatus[];
  summary: {
    total_repos: number;
    total_open_prs: number;
    prs_with_failing_ci: number;
  };
}

export interface DashboardData {
  version: string;
  portal: {
    name: string;
    description: string;
    budget?: {
      daily: number;
      unit: string;
      per_agent?: Record<string, number>;
      track?: { date: string; spent: number; per_agent?: Record<string, number> };
    };
  };
  tasks: Task[];
  summary: {
    generated_at: string;
    total: number;
    by_status: Record<string, number>;
    by_agent: Record<string, number>;
    by_priority: Record<string, number>;
    by_repo: Record<string, number>;
    active_count: number;
    stale_count: number;
    stale_task_ids: string[];
    today: string;
    today_events: number;
    today_jules_dispatches: number;
    throughput?: ThroughputSummary;
    recent_events: DispatchEvent[];
  };
  storage?: {
    mode: string;
    repo?: string;
    branch?: string;
    path?: string;
    configured?: boolean;
  };
}

export interface ThroughputSummary {
  first_created: string;
  current_date: string;
  age_days: number;
  daily_capacity: number;
  expected_capacity_runs: number;
  task_burndown_target_per_day: number;
  recorded_events: number;
  recorded_starts: number;
  recorded_finishes: number;
  done: number;
  not_done: number;
  unrecorded_capacity_runs: number;
  by_event_status: Record<string, number>;
  by_event_agent: Record<string, number>;
  by_event_date: Record<string, number>;
}

type Phase = "EXPLORE" | "PLAN" | "BUILD" | "VERIFY" | "LEARN" | "REPEAT";
type LifecycleGate = "recover" | "verify" | "assign" | "archive" | "archived";
type FilterKey = "all" | "needs-attention" | "jules" | "active" | "done" | LifecycleGate;
type ApiAction = "release" | "dispatch";
type ApiPreviewItem = {
  id?: string;
  title?: string;
  repo?: string;
  agent?: string;
  status?: string;
  budget_cost?: number;
  command?: string[];
  latest?: string | null;
};
type ApiState = {
  loading: ApiAction | null;
  result: string;
  error: string;
  preview: ApiPreviewItem[];
  action: ApiAction | null;
};

const phases: Phase[] = ["EXPLORE", "PLAN", "BUILD", "VERIFY", "LEARN", "REPEAT"];
const lifecycleGates: LifecycleGate[] = ["recover", "verify", "assign", "archive", "archived"];
const statusColor: Record<string, string> = {
  open: "blue",
  dispatched: "amber",
  in_progress: "violet",
  done: "green",
  failed: "red",
  failed_blocked: "red",
  needs_human: "red",
  superseded: "slate",
};

function shortRepo(repo: string) {
  return repo ? repo.split("/").pop() || repo : "limen";
}

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

function getPhase(task: Task, relatedPRs: PR[]): Phase {
  if (["failed", "failed_blocked", "needs_human", "superseded"].includes(task.status)) return "REPEAT";
  if (task.status === "done") return "LEARN";
  if (relatedPRs.length > 0 || task.status === "in_progress") return "VERIFY";
  if (task.status === "dispatched") return "BUILD";
  return "EXPLORE";
}

function getLifecycleGate(task: Task, stale: boolean): LifecycleGate {
  const urls = task.urls || [];
  if (task.status === "archived") return "archived";
  if (task.status === "done") return "archive";
  if (stale || ["failed", "failed_blocked", "needs_human"].includes(task.status)) return "recover";
  if (urls.some((url) => url.includes("/pull/")) || ["dispatched", "in_progress"].includes(task.status)) return "verify";
  return "assign";
}

function getLifecycleGateLabel(gate: LifecycleGate) {
  return {
    recover: "release stale claim or reassign with failure note",
    verify: "verify PR/runtime evidence, then close or return",
    assign: "assign to agent with budget and acceptance gate",
    archive: "archive evidence and suppress from active steering",
    archived: "suppressed from active steering",
  }[gate];
}

function getProgress(phase: Phase) {
  return { EXPLORE: 12, PLAN: 28, BUILD: 52, VERIFY: 74, LEARN: 92, REPEAT: 100 }[phase];
}

function latestEvent(task: Task) {
  return [...(task.dispatch_log || [])].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))[0];
}

export default function DashboardClient({ data, prData, apiUrl, initialToken = "" }: { data: DashboardData; prData: PRStatusData | null; apiUrl: string; initialToken?: string }) {
  const [phase, setPhase] = useState<Phase | "ALL">("ALL");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(data.tasks[0]?.id || "");
  const [apiToken, setApiToken] = useState(initialToken);
  const [apiState, setApiState] = useState<ApiState>({ loading: null, result: "", error: "", preview: [], action: null });

  const prsByRepo = useMemo(() => {
    const byRepo: Record<string, PR[]> = {};
    for (const repo of prData?.repos || []) byRepo[repo.repo] = repo.prs || [];
    return byRepo;
  }, [prData]);

  const rows = useMemo(() => {
    return data.tasks.map((task) => {
      const repoPRs = prsByRepo[task.repo] || [];
      const prUrls = task.urls?.filter((url) => url.includes("/pull/")) || [];
      const relatedPRs = prUrls.length
        ? repoPRs.filter((pr) => prUrls.some((url) => url.includes(`/pull/${pr.number}`)))
        : repoPRs.filter((pr) => pr.author === "4444J99");
      const taskPhase = getPhase(task, relatedPRs);
      return {
        ...task,
        phase: taskPhase,
        lifecycleGate: getLifecycleGate(task, data.summary.stale_task_ids.includes(task.id)),
        progress: getProgress(taskPhase),
        relatedPRs,
        latestEvent: latestEvent(task),
        stale: data.summary.stale_task_ids.includes(task.id),
      };
    });
  }, [data.tasks, data.summary.stale_task_ids, prsByRepo]);

  const filteredRows = rows.filter((task) => {
    const matchesPhase = phase === "ALL" || task.phase === phase;
    const haystack = `${task.id} ${task.title} ${task.repo} ${task.status} ${task.target_agent} ${(task.labels || []).join(" ")}`.toLowerCase();
    const matchesQuery = !query || haystack.includes(query.toLowerCase());
    const matchesFilter =
      filter === "all" ||
      (filter === "needs-attention" && (task.stale || ["failed", "failed_blocked", "needs_human"].includes(task.status))) ||
      (filter === "jules" && task.target_agent === "jules") ||
      (filter === "active" && ["dispatched", "in_progress"].includes(task.status)) ||
      (filter === "done" && task.status === "done") ||
      (lifecycleGates.includes(filter as LifecycleGate) && task.lifecycleGate === filter);
    return matchesPhase && matchesQuery && matchesFilter;
  });

  const selected = rows.find((task) => task.id === selectedId) || filteredRows[0] || rows[0];
  const budget = data.portal.budget || { daily: 100, unit: "runs", per_agent: { jules: 100 }, track: { date: "", spent: 0, per_agent: {} } };
  const julesDaily = budget.per_agent?.jules || 100;
  const julesToday = data.summary.today_jules_dispatches;
  const julesPct = Math.min(100, Math.round((julesToday / julesDaily) * 100));
  const done = data.summary.by_status.done || 0;
  const active = data.summary.active_count;
  const failed = (data.summary.by_status.failed || 0) + (data.summary.by_status.failed_blocked || 0);
  const throughput = data.summary.throughput;
  const lifecycleCounts = Object.fromEntries(lifecycleGates.map((gate) => [gate, rows.filter((task) => task.lifecycleGate === gate).length])) as Record<LifecycleGate, number>;
  const apiReady = Boolean(apiUrl);
  const storageLabel = data.storage?.mode === "github" && data.storage.repo
    ? `${data.storage.repo}:${data.storage.path || "tasks.yaml"}`
    : data.storage?.mode || "static snapshot";

  async function callApi(action: ApiAction) {
    if (!apiReady || apiState.loading) return;
    setApiState({ loading: action, result: "", error: "", preview: [], action });
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
    const endpoint =
      action === "release"
        ? `${apiUrl}/api/release-stale?hours=24&dry_run=true`
        : `${apiUrl}/api/dispatch`;
    const init: RequestInit =
      action === "release"
        ? { method: "POST", headers }
        : {
            method: "POST",
            headers,
            body: JSON.stringify({ agent: "jules", limit: 10, live: false, session_id: "dashboard" }),
          };

    try {
      const response = await fetch(endpoint, init);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || response.statusText);
      const result =
        action === "release"
          ? `${payload.count || 0} stale tasks ready to reopen`
          : `${payload.count || 0} Jules dispatch candidates`;
      const preview = (payload.candidates || payload.tasks || []) as ApiPreviewItem[];
      setApiState({ loading: null, result, error: "", preview, action });
    } catch (error) {
      setApiState({ loading: null, result: "", error: error instanceof Error ? error.message : "API request failed", preview: [], action });
    }
  }

  return (
    <main className="shell">
      <SurfaceNav active="internal" />
      <header className="topbar">
        <div>
          <p className="caption">Limen</p>
          <h1>{data.portal.name || "Universal Task Intake"}</h1>
        </div>
        <div className="topbarMeta">
          <span>Generated {formatDate(data.summary.generated_at)}</span>
          <a href="https://device-streaming-067d747a.web.app" target="_blank" rel="noreferrer">
            Production
          </a>
        </div>
      </header>

      <section className="metrics" aria-label="Pipeline metrics">
        <Metric title="Jules today" value={`${julesToday}/${julesDaily}`} tone={julesToday === 0 ? "red" : "blue"} detail={`${julesPct}% of daily async capacity used`} />
        <Metric title="Run plan" value={throughput ? `${throughput.task_burndown_target_per_day}/day` : "n/a"} tone="blue" detail={throughput ? `${throughput.first_created} to ${throughput.current_date}: ${throughput.age_days} days` : "Creation date unavailable"} />
        <Metric title="Recorded starts" value={throughput ? `${throughput.recorded_starts}` : "0"} tone={throughput?.recorded_starts ? "amber" : "red"} detail={throughput ? `${throughput.recorded_events} events, ${throughput.unrecorded_capacity_runs} starts not recorded` : "No run ledger"} />
        <Metric title="Queue" value={`${data.summary.total}`} tone="blue" detail={`${active} active, ${data.summary.stale_count} stale`} />
        <Metric title="Completed" value={`${throughput?.done ?? done}`} tone="green" detail={`${throughput?.not_done ?? data.summary.total - done} not done`} />
        <Metric title="PR health" value={`${prData?.summary.total_open_prs || 0}`} tone={prData?.summary.prs_with_failing_ci ? "amber" : "green"} detail={`${prData?.summary.prs_with_failing_ci || 0} with failing CI`} />
        <Metric title="Failures" value={`${failed}`} tone={failed ? "red" : "green"} detail="Failed or blocked task states" />
      </section>

      <section className="lifecycleBand" aria-label="Task lifecycle gates">
        {lifecycleGates.map((gate) => (
          <button key={gate} className={filter === gate ? "selected" : ""} onClick={() => setFilter(gate)}>
            <span>{gate}</span>
            <strong>{lifecycleCounts[gate]}</strong>
          </button>
        ))}
      </section>

      <section className="controlBand">
        <div className="phaseRail" aria-label="Lifecycle phases">
          <button className={phase === "ALL" ? "selected" : ""} onClick={() => setPhase("ALL")}>ALL</button>
          {phases.map((item) => (
            <button key={item} className={phase === item ? "selected" : ""} onClick={() => setPhase(item)}>
              {item}<span>{rows.filter((task) => task.phase === item).length}</span>
            </button>
          ))}
        </div>
        <div className="filters">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search task, repo, label" />
          <select value={filter} onChange={(event) => setFilter(event.target.value as FilterKey)}>
            <option value="all">All tasks</option>
            <option value="needs-attention">Needs attention</option>
            <option value="jules">Jules queue</option>
            <option value="active">Active</option>
            <option value="done">Done</option>
            {lifecycleGates.map((gate) => <option key={gate} value={gate}>{gate}</option>)}
          </select>
        </div>
      </section>

      <section className="opsPanel" aria-label="Dispatch controls">
        <div>
          <span className={`connection ${apiReady ? "online" : "offline"}`}>{apiReady ? "API connected" : "API not connected"}</span>
          <strong>Jules capacity recovery</strong>
          <p>{data.summary.stale_count} stale active tasks are blocking new Jules dispatches. Source: {storageLabel}.</p>
        </div>
        <div className="opsControls">
          <input
            value={apiToken}
            onChange={(event) => setApiToken(event.target.value)}
            placeholder="API token"
            type="password"
            disabled={!apiReady}
          />
          <button onClick={() => callApi("release")} disabled={!apiReady || Boolean(apiState.loading)}>
            {apiState.loading === "release" ? "Checking" : "Preview release"}
          </button>
          <button onClick={() => callApi("dispatch")} disabled={!apiReady || Boolean(apiState.loading)}>
            {apiState.loading === "dispatch" ? "Checking" : "Preview dispatch"}
          </button>
        </div>
        {(apiState.result || apiState.error) && (
          <p className={apiState.error ? "opsError" : "opsResult"}>{apiState.error || apiState.result}</p>
        )}
        {apiState.preview.length > 0 && (
          <div className="opsPreview" aria-label="Preview candidates">
            {apiState.preview.slice(0, 10).map((item) => (
              <article key={item.id}>
                <span className="mono">{item.id}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{shortRepo(item.repo || "")} · {apiState.action === "release" ? item.status || "stale" : `${item.budget_cost || 1} run`}</p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="workspace">
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Task</th>
                <th>Repo</th>
                <th>Agent</th>
                <th>Status</th>
                <th>Gate</th>
                <th>Progress</th>
                <th>Latest</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((task) => (
                <tr key={task.id} className={selected?.id === task.id ? "activeRow" : ""} onClick={() => setSelectedId(task.id)}>
                  <td className="mono">{task.id}</td>
                  <td>
                    <div className="taskTitle">{task.title}</div>
                    <div className="labels">{(task.labels || []).slice(0, 4).map((label) => <span key={label}>{label}</span>)}</div>
                  </td>
                  <td><a href={task.repo ? `https://github.com/${task.repo}` : "#"} target="_blank" rel="noreferrer">{shortRepo(task.repo)}</a></td>
                  <td><span className="agent">{task.target_agent || "any"}</span></td>
                  <td><span className={`status ${statusColor[task.status] || "slate"}`}>{task.status}</span></td>
                  <td><span className="gatePill">{task.lifecycleGate}</span></td>
                  <td>
                    <div className="progress"><span style={{ width: `${task.progress}%` }} /></div>
                  </td>
                  <td>{formatDate(task.latestEvent?.timestamp || task.updated || task.created)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <aside className="detailPane" aria-label="Task details">
          {selected ? (
            <>
              <div className="detailHeader">
                <span className="mono">{selected.id}</span>
                <span className={`status ${statusColor[selected.status] || "slate"}`}>{selected.status}</span>
              </div>
              <h2>{selected.title}</h2>
              <p>{selected.context || "No task context recorded."}</p>
              <dl className="detailGrid">
                <div><dt>Agent</dt><dd>{selected.target_agent}</dd></div>
                <div><dt>Priority</dt><dd>{selected.priority}</dd></div>
                <div><dt>Budget</dt><dd>{selected.budget_cost || 1} run</dd></div>
                <div><dt>Phase</dt><dd>{selected.phase}</dd></div>
                <div><dt>Gate</dt><dd>{selected.lifecycleGate}</dd></div>
              </dl>
              <p className="surfaceCopy">{getLifecycleGateLabel(selected.lifecycleGate)}</p>
              <section>
                <h3>Links</h3>
                <div className="linkList">
                  {(selected.urls || []).map((url) => <a href={url} key={url} target="_blank" rel="noreferrer">{url}</a>)}
                  {selected.relatedPRs.map((pr) => <a href={pr.html_url} key={pr.html_url} target="_blank" rel="noreferrer">PR #{pr.number}: {pr.title}</a>)}
                </div>
              </section>
              <section>
                <h3>Dispatch Log</h3>
                <div className="eventLog">
                  {(selected.dispatch_log || []).slice().reverse().map((event, index) => (
                    <div key={`${event.timestamp}-${index}`}>
                      <span>{formatDate(event.timestamp)}</span>
                      <strong>{event.agent}</strong>
                      <em>{event.status}</em>
                      {event.output && <p>{event.output}</p>}
                    </div>
                  ))}
                </div>
              </section>
            </>
          ) : (
            <p>No task selected.</p>
          )}
        </aside>
      </section>
    </main>
  );
}

function Metric({ title, value, detail, tone }: { title: string; value: string; detail: string; tone: string }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{title}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}
