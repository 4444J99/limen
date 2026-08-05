"use client";

import React, { useEffect, useMemo, useState } from "react";
import FleetLivePanel from "./fleet-live-panel";
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
    per_vendor?: VendorUsage[];
    daily_total?: { spent: number; cap: number; date: string | null };
    ticks?: HeartbeatTick[];
    throughput?: ThroughputSummary;
    integrity?: {
      counts: Record<string, number>;
      chronic?: { id: string; agent: string; reopens: number; repo: string }[];
    };
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

export interface VendorUsage {
  agent: string;
  kind: "cloud" | "local";
  cap: number;
  spent: number;
  remaining: number;
  pct: number;
  open: number;
  today_dispatches: number;
}

export interface HeartbeatTick {
  ts: string;
  total: number;
  open: number;
  dispatched: number;
  done: number;
  failed: number;
  daily_spent: number;
  daily_cap: number;
}

type Phase = "EXPLORE" | "PLAN" | "BUILD" | "VERIFY" | "HEAL" | "LEARN" | "RELAY";
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

const phases: Phase[] = ["EXPLORE", "PLAN", "BUILD", "VERIFY", "HEAL", "LEARN", "RELAY"];
const lifecycleGates: LifecycleGate[] = ["recover", "verify", "assign", "archive", "archived"];
const statusColor: Record<string, string> = {
  open: "blue",
  dispatched: "amber",
  in_progress: "violet",
  done: "green",
  failed: "red",
  failed_blocked: "red",
  needs_human: "red",
  cancelled: "slate",
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
  if (["failed", "failed_blocked", "needs_human"].includes(task.status)) return "HEAL";
  if (task.status === "superseded" || task.status === "cancelled") return "RELAY";
  if (task.status === "done" || task.status === "archived") return "LEARN";
  if (relatedPRs.length > 0 || task.status === "in_progress") return "VERIFY";
  if (task.status === "dispatched") return "BUILD";
  return "EXPLORE";
}

function getLifecycleGate(task: Task, stale: boolean): LifecycleGate {
  const urls = task.urls || [];
  if (["archived", "cancelled"].includes(task.status)) return "archived";
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
  return { EXPLORE: 10, PLAN: 24, BUILD: 44, VERIFY: 64, HEAL: 78, LEARN: 92, RELAY: 100 }[phase];
}

function latestEvent(task: Task) {
  return [...(task.dispatch_log || [])].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))[0];
}

export default function DashboardClient({ data, prData, apiUrl, initialToken = "", doneTasks = null, doneLoading = false, onLoadDoneTasks }: { data: DashboardData; prData: PRStatusData | null; apiUrl: string; initialToken?: string; doneTasks?: Task[] | null; doneLoading?: boolean; onLoadDoneTasks?: () => void }) {
  const [phase, setPhase] = useState<Phase | "ALL">("ALL");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(data.tasks[0]?.id || "");
  const [apiToken, setApiToken] = useState(initialToken);
  const [apiState, setApiState] = useState<ApiState>({ loading: null, result: "", error: "", preview: [], action: null });
  const [rollup, setRollup] = useState(true);
  const [openRepos, setOpenRepos] = useState<Record<string, boolean>>({});
  const [hideChurn, setHideChurn] = useState(true);

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

  // Machine churn (cancelled / noop / per-session "Session walk" reconcile rows) is
  // telemetry, not work — demoted out of the default view (toggle to show).
  const isChurn = (task: (typeof rows)[number]) =>
    task.status === "cancelled" ||
    (task.labels || []).includes("noop") ||
    (task.labels || []).includes("session-walk") ||
    task.title.startsWith("Session walk:");
  const churnTotal = rows.filter(isChurn).length;

  // When filter="done" is selected, trigger lazy-loading done-tasks.json the first time.
  useEffect(() => {
    if (filter === "done" && doneTasks === null && !doneLoading) {
      onLoadDoneTasks?.();
    }
  }, [filter, doneTasks, doneLoading, onLoadDoneTasks]);

  // Augment rows with lazy-loaded done tasks when the done filter is active.
  const doneRows = useMemo(() => {
    if (!doneTasks) return [];
    return doneTasks.map((task) => {
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
  }, [doneTasks, prsByRepo, data.summary.stale_task_ids]);

  const filteredRows = [...rows, ...(filter === "done" ? doneRows : [])].filter((task) => {
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
    return matchesPhase && matchesQuery && matchesFilter && (!hideChurn || !isChurn(task));
  });

  // Roll up the (filtered) tasks by repo so the view is a handful of collapsible
  // groups with per-status counts — not an endless flat scroll of every dispatch.
  const repoGroups = (() => {
    const map = new Map<string, typeof filteredRows>();
    for (const task of filteredRows) {
      const key = task.repo || "(no repo)";
      const list = map.get(key);
      if (list) list.push(task);
      else map.set(key, [task]);
    }
    return Array.from(map.entries())
      .map(([repo, tasks]) => {
        const counts: Record<string, number> = {};
        for (const t of tasks) counts[t.status] = (counts[t.status] || 0) + 1;
        return { repo, tasks, counts };
      })
      .sort((a, b) => b.tasks.length - a.tasks.length);
  })();

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

  const renderRow = (task: (typeof rows)[number]) => (
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
  );

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
        <Metric title="Dispatches recorded" value={throughput ? `${throughput.recorded_starts}` : "0"} tone={throughput?.recorded_starts ? "blue" : "red"} detail={throughput ? `${throughput.recorded_events} log events · ${throughput.unrecorded_capacity_runs} capacity slots unused since launch` : "No run ledger"} />
        <Metric title="Queue" value={`${data.summary.total}`} tone="blue" detail={`${active} active, ${data.summary.stale_count} stale`} />
        <Metric title="Completed" value={`${throughput?.done ?? done}`} tone="green" detail={`${throughput?.not_done ?? data.summary.total - done} not done`} />
        <Metric title="PR health" value={`${prData?.summary.total_open_prs || 0}`} tone={prData?.summary.prs_with_failing_ci ? "amber" : "green"} detail={`${prData?.summary.prs_with_failing_ci || 0} with failing CI`} />
        <Metric title="Failures" value={`${failed}`} tone={failed ? "red" : "green"} detail="Failed or blocked task states" />
      </section>

      <VendorCapacity vendors={data.summary.per_vendor || []} dailyTotal={data.summary.daily_total} />

      <IntegrityPanel integrity={data.summary.integrity} />

      <FleetLivePanel />

      <HeartbeatTimeline ticks={data.summary.ticks || []} />

      <SurfacesGrid byRepo={data.summary.by_repo} />

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
          <button type="button" className={rollup ? "selected" : ""} onClick={() => setRollup((v) => !v)}>{rollup ? "Rolled up" : "Flat list"}</button>
          <button type="button" className={hideChurn ? "selected" : ""} onClick={() => setHideChurn((v) => !v)} title="cancelled / noop / session-walk reconcile rows">{hideChurn ? `Churn hidden (${churnTotal})` : "Churn shown"}</button>
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
              {filter === "done" && doneLoading && (
                <tr><td colSpan={8} style={{ textAlign: "center", color: "#94a3b8", padding: "1rem" }}>Loading done tasks…</td></tr>
              )}
              {rollup
                ? repoGroups.map((group) => (
                    <React.Fragment key={group.repo}>
                      <tr className="groupRow" onClick={() => setOpenRepos((open) => ({ ...open, [group.repo]: !open[group.repo] }))}>
                        <td colSpan={8} style={{ cursor: "pointer", background: "#0f172a" }}>
                          <span style={{ display: "inline-block", width: 14 }}>{openRepos[group.repo] ? "▾" : "▸"}</span>
                          <strong>{shortRepo(group.repo)}</strong>
                          <span style={{ marginLeft: 8, color: "#94a3b8" }}>{group.tasks.length} tasks</span>
                          {Object.entries(group.counts).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
                            <span key={s} className={`status ${statusColor[s] || "slate"}`} style={{ marginLeft: 6 }}>{s} {n}</span>
                          ))}
                        </td>
                      </tr>
                      {openRepos[group.repo] && group.tasks.map((task) => renderRow(task))}
                    </React.Fragment>
                  ))
                : filteredRows.map((task) => renderRow(task))}
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

function VendorCapacity({ vendors, dailyTotal }: { vendors: VendorUsage[]; dailyTotal?: { spent: number; cap: number; date: string | null } }) {
  if (!vendors.length) return null;
  const barColor = (pct: number) => (pct >= 90 ? "#e5484d" : pct >= 60 ? "#f5a623" : "#3b82f6");
  return (
    <section aria-label="Vendor capacity" style={{ margin: "1rem 0", padding: "1rem 1.25rem", border: "1px solid #2a2f3a", borderRadius: 10, background: "#0f1320" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.85rem" }}>
        <h2 style={{ margin: 0, fontSize: "0.85rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "#cbd5e1" }}>Vendor capacity &amp; refresh</h2>
        {dailyTotal ? (
          <span style={{ fontSize: "0.78rem", color: "#94a3b8" }}>
            daily {dailyTotal.spent}/{dailyTotal.cap} · resets on UTC date-roll{dailyTotal.date ? ` (now ${dailyTotal.date})` : ""}
          </span>
        ) : null}
      </div>
      <div style={{ display: "grid", gap: "0.55rem" }}>
        {vendors.map((v) => (
          <div key={v.agent} style={{ display: "grid", gridTemplateColumns: "8rem 1fr 12rem", alignItems: "center", gap: "0.85rem" }}>
            <span style={{ fontWeight: 600, color: "#e2e8f0" }}>
              {v.agent}
              <span style={{ marginLeft: 6, fontSize: "0.62rem", color: v.kind === "cloud" ? "#a78bfa" : "#34d399" }}>{v.kind}</span>
            </span>
            <div style={{ position: "relative", height: 14, background: "#1f2937", borderRadius: 7, overflow: "hidden" }} title={`${v.spent}/${v.cap} used today`}>
              <div style={{ width: `${Math.max(2, Math.min(100, v.pct))}%`, height: "100%", background: barColor(v.pct) }} />
            </div>
            <span style={{ fontSize: "0.76rem", color: "#94a3b8", textAlign: "right" }}>
              {v.spent}/{v.cap} · {v.remaining} left · {v.open} queued · {v.today_dispatches} today
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

interface Surface { name: string; repo: string; kind: string; live?: string; status?: string; desc?: string }

function IntegrityPanel({ integrity }: { integrity?: DashboardData["summary"]["integrity"] }) {
  if (!integrity) return null;
  const c = integrity.counts || {};
  const healthy: [string, string][] = [["PR_OPEN", "#34d399"], ["JULES_ASYNC", "#22d3ee"], ["DISPATCHED_RUNNING", "#3b82f6"]];
  const bad: [string, string][] = [["PR_MERGED", "#f5a623"], ["PR_CLOSED", "#f5a623"], ["PR_MISSING", "#e5484d"], ["DISPATCHED_NO_PR", "#e5484d"]];
  const actionable = bad.reduce((s, [k]) => s + (c[k] || 0), 0);
  const chronic = c["CHRONIC"] || 0;
  return (
    <section aria-label="Dispatch integrity" style={{ margin: "1rem 0", padding: "1rem 1.25rem", border: "1px solid #2a2f3a", borderRadius: 10, background: "#0f1320" }}>
      <h2 style={{ margin: "0 0 0.7rem", fontSize: "0.85rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "#cbd5e1" }}>Dispatch integrity · babysit every send</h2>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", alignItems: "baseline" }}>
        {healthy.map(([k, col]) => (
          <span key={k} style={{ color: col, fontSize: "0.82rem" }}>{k.toLowerCase()}: <strong>{c[k] || 0}</strong></span>
        ))}
        {actionable === 0 ? (
          <span style={{ color: "#34d399", fontSize: "0.82rem" }}>✓ no silent failures</span>
        ) : (
          bad.filter(([k]) => c[k]).map(([k, col]) => (
            <span key={k} style={{ color: col, fontSize: "0.82rem" }}>⚠ {k.toLowerCase()}: <strong>{c[k]}</strong></span>
          ))
        )}
      </div>
      {chronic ? (
        <div style={{ marginTop: "0.7rem", fontSize: "0.78rem", color: "#a78bfa" }}>
          ⚑ chronic: <strong>{chronic}</strong> <span style={{ color: "#94a3b8" }}>(reopened ≥3× · never a PR · failing all lanes → escalate, not re-loop)</span>
        </div>
      ) : null}
    </section>
  );
}

function SurfacesGrid({ byRepo }: { byRepo: Record<string, number> }) {
  const [surfaces, setSurfaces] = useState<Surface[]>([]);
  useEffect(() => {
    let alive = true;
    fetch("/surfaces.json")
      .then((r) => (r.ok ? r.json() : { surfaces: [] }))
      .then((d) => { if (alive) setSurfaces(d.surfaces || []); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  if (!surfaces.length) return null;
  return (
    <section aria-label="Surfaces" style={{ margin: "1rem 0", padding: "1rem 1.25rem", border: "1px solid #2a2f3a", borderRadius: 10, background: "#0f1320" }}>
      <h2 style={{ margin: "0 0 0.85rem", fontSize: "0.85rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "#cbd5e1" }}>Surfaces — backend &amp; frontend</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(15rem, 1fr))", gap: "0.75rem" }}>
        {surfaces.map((s) => {
          const tasks = byRepo?.[s.repo] || 0;
          const href = s.live || `https://github.com/${s.repo}`;
          return (
            <a key={s.repo} href={href} target="_blank" rel="noreferrer" style={{ display: "block", padding: "0.75rem 0.9rem", border: "1px solid #2a2f3a", borderRadius: 8, background: "#141a2b", textDecoration: "none", color: "#e2e8f0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <strong style={{ fontSize: "0.85rem" }}>{s.name}</strong>
                <span style={{ fontSize: "0.6rem", color: s.status === "lost" ? "#e5484d" : s.kind === "frontend" ? "#60a5fa" : "#34d399" }}>{s.status === "lost" ? "lost" : s.kind}</span>
              </div>
              <p style={{ margin: "0.3rem 0 0", fontSize: "0.72rem", color: "#94a3b8" }}>{s.desc}</p>
              <p style={{ margin: "0.4rem 0 0", fontSize: "0.68rem", color: "#64748b" }}>{s.repo} · {tasks} task{tasks === 1 ? "" : "s"}{s.live ? " · live" : ""}</p>
            </a>
          );
        })}
      </div>
    </section>
  );
}

function HeartbeatTimeline({ ticks }: { ticks: HeartbeatTick[] }) {
  if (!ticks.length) return null;
  const last = ticks[ticks.length - 1];
  const max = Math.max(1, ...ticks.map((t) => t.dispatched + t.done));
  return (
    <section aria-label="Heartbeat" style={{ margin: "1rem 0", padding: "1rem 1.25rem", border: "1px solid #2a2f3a", borderRadius: 10, background: "#0f1320" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.85rem" }}>
        <h2 style={{ margin: 0, fontSize: "0.85rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "#cbd5e1" }}>Heartbeat — autonomic loop</h2>
        <span style={{ fontSize: "0.78rem", color: "#94a3b8" }}>{ticks.length} ticks · last {formatDate(last.ts)} · spent {last.daily_spent}/{last.daily_cap}</span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 48 }}>
        {ticks.map((t, i) => {
          const h = Math.max(3, Math.round(((t.dispatched + t.done) / max) * 46));
          return <div key={i} title={`${t.ts} — ${t.total} tasks, ${t.open} open, ${t.dispatched} dispatched`} style={{ width: 6, height: h, background: t.failed ? "#e5484d" : "#3b82f6", borderRadius: 2 }} />;
        })}
      </div>
      <p style={{ margin: "0.5rem 0 0", fontSize: "0.72rem", color: "#64748b" }}>{last.total} tasks · {last.open} open · {last.done} done · {last.failed} failed (latest tick)</p>
    </section>
  );
}
