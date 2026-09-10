"use client";

import { useState } from "react";
import type { IssueStatusData, PRStatusData, RepoHealthData } from "../dashboard-client";
import SurfaceNav from "../surface-nav";
import type { QASteeringItem, QAStatusData, ReadinessData, SurfaceManifestData } from "../lib/data";
import AssignmentPanel from "./assignment-panel";
import ArchivePanel from "./archive-panel";
import RecoveryPanel from "./recovery-panel";
import VerifyPanel from "./verify-panel";

type LoadState = {
  loading: boolean;
  error: string;
  statusData: QAStatusData | null;
  manifest: SurfaceManifestData | null;
  readiness: ReadinessData | null;
  prData: PRStatusData | null;
  issueData: IssueStatusData | null;
  repoHealthData: RepoHealthData | null;
};

const phaseTone: Record<QASteeringItem["phase"], string> = {
  assign: "blue",
  verify: "violet",
  recover: "red",
  archive: "green",
  archived: "slate",
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

export default function QASurfaceClient({ apiUrl }: { apiUrl: string }) {
  const [token, setToken] = useState("");
  const [state, setState] = useState<LoadState>({
    loading: false,
    error: "",
    statusData: null,
    manifest: null,
    readiness: null,
    prData: null,
    issueData: null,
    repoHealthData: null,
  });

  async function loadSurface(nextToken = token, clearExisting = true) {
    if (!apiUrl) return;
    setState((current) => ({
      loading: true,
      error: "",
      statusData: clearExisting ? null : current.statusData,
      manifest: clearExisting ? null : current.manifest,
      readiness: clearExisting ? null : current.readiness,
      prData: clearExisting ? null : current.prData,
      issueData: clearExisting ? null : current.issueData,
      repoHealthData: clearExisting ? null : current.repoHealthData,
    }));
    const headers: Record<string, string> = nextToken ? { Authorization: "Bearer " + nextToken } : {};
    try {
      const optionalFetch = (path: string) => fetch(`${apiUrl}${path}`, { headers }).catch(() => null);
      const [qaRes, manifestRes, readinessRes, prRes, issueRes, repoHealthRes] = await Promise.all([
        fetch(`${apiUrl}/api/qa-status`, { headers }),
        fetch(`${apiUrl}/api/surface-manifest`, { headers }),
        fetch(`${apiUrl}/api/readiness`, { headers }),
        optionalFetch("/api/pr-status"),
        optionalFetch("/api/issue-status"),
        optionalFetch("/api/repo-health"),
      ]);
      const qaPayload = await qaRes.json();
      const manifestPayload = await manifestRes.json();
      const readinessPayload = await readinessRes.json();
      if (!qaRes.ok) throw new Error(qaPayload.detail || qaRes.statusText);
      if (!manifestRes.ok) throw new Error(manifestPayload.detail || manifestRes.statusText);
      if (!readinessRes.ok) throw new Error(readinessPayload.detail || readinessRes.statusText);
      setState({
        loading: false,
        error: "",
        statusData: qaPayload,
        manifest: manifestPayload,
        readiness: readinessPayload,
        prData: prRes && prRes.ok ? await prRes.json() : null,
        issueData: issueRes && issueRes.ok ? await issueRes.json() : null,
        repoHealthData: repoHealthRes && repoHealthRes.ok ? await repoHealthRes.json() : null,
      });
    } catch (error) {
      setState({
        loading: false,
        error: error instanceof Error ? error.message : "QA load failed",
        statusData: null,
        manifest: null,
        readiness: null,
        prData: null,
        issueData: null,
        repoHealthData: null,
      });
    }
  }

  async function load() {
    await loadSurface(token, true);
  }

  async function refreshAfterAction() {
    await loadSurface(token, false);
  }

  const statusData = state.statusData;
  const lifecycle = statusData?.lifecycle;
  const nextBatch = statusData?.steering.next_batch || [];

  return (
    <main className="audienceShell qaShell">
      <SurfaceNav active="qa" />
      <header className="audienceHeader qaHeader">
        <p className="caption">QA and Steering</p>
        <h1>Lifecycle control</h1>
        <p>{statusData?.steering.principle || "QA lifecycle controls load after owner authorization."}</p>
      </header>

      {!statusData || !lifecycle ? (
        <section className="surfacePanel authPanel">
          <div className="panelTitle">
            <span>Access</span>
            <strong>{apiUrl ? "Owner token required" : "Runtime unavailable"}</strong>
          </div>
          <div className="assignPanel">
            <label>
              <span>Token</span>
              <input value={token} onChange={(event) => setToken(event.target.value)} type="password" disabled={!apiUrl} />
            </label>
            <button onClick={load} disabled={!apiUrl || state.loading}>
              {state.loading ? "Loading" : "Load QA"}
            </button>
            {!apiUrl && <p>Build with NEXT_PUBLIC_API_URL to enable QA.</p>}
            {state.error && <p className="opsError">{state.error}</p>}
          </div>
        </section>
      ) : (
        <>
          <section className="audienceMetrics" aria-label="Lifecycle metrics">
            <div><span>Recover</span><strong>{lifecycle.recover}</strong><p>Stale or failed claims</p></div>
            <div><span>Verify</span><strong>{lifecycle.verify}</strong><p>Needs evidence gate</p></div>
            <div><span>Assign</span><strong>{lifecycle.assign}</strong><p>Ready for budgeted work</p></div>
            <div><span>Closure</span><strong>{lifecycle.archive_ready}/{lifecycle.archived || 0}</strong><p>Ready / archived</p></div>
          </section>

          <section className="qaLayout">
            <div className="surfacePanel wide">
              <div className="panelTitle">
                <span>Next steering batch</span>
                <strong>{nextBatch.length} lifecycle gates, generated {formatDate(statusData.generated_at)}</strong>
              </div>
              <div className="qaQueue">
                {nextBatch.map((item) => (
                  <article key={item.id}>
                    <div>
                      <span className="mono">{item.id}</span>
                      <strong>{item.title}</strong>
                      <p>{repoName(item.repo)} · {item.assignee} · {item.next_gate}</p>
                    </div>
                    <span className={`status ${phaseTone[item.phase]}`}>{item.phase}</span>
                  </article>
                ))}
              </div>
            </div>

            <aside className="qaSide">
              <RecoveryPanel items={statusData.steering.recovery_queue} apiUrl={apiUrl} initialToken={token} onComplete={refreshAfterAction} />
              <VerifyPanel items={statusData.steering.qa_queue} apiUrl={apiUrl} initialToken={token} onComplete={refreshAfterAction} />
              <AssignmentPanel items={nextBatch} apiUrl={apiUrl} initialToken={token} onComplete={refreshAfterAction} />
              <ArchivePanel items={statusData.steering.archive_queue} apiUrl={apiUrl} initialToken={token} onComplete={refreshAfterAction} />

              <section className="surfacePanel">
                <div className="panelTitle">
                  <span>PR watch</span>
                  <strong>{state.prData?.summary.total_open_prs || 0} open</strong>
                </div>
                <p className="surfaceCopy">
                  {(state.prData?.summary.review_pending_prs || 0)} awaiting review · {(state.prData?.summary.prs_with_pending_checks || 0)} pending checks · {(state.prData?.summary.ready_to_merge_prs || 0)} ready
                </p>
                <div className="mechanismList">
                  {(state.prData?.repos || []).slice(0, 4).map((repo) => (
                    <article key={repo.repo}>
                      <div>
                        <span>{repoName(repo.repo)}</span>
                        <strong>{repo.ready_to_merge_count || 0} ready · {repo.blocked_count || 0} blocked</strong>
                      </div>
                      <b>{repo.count}</b>
                    </article>
                  ))}
                </div>
              </section>

              <section className="surfacePanel">
                <div className="panelTitle">
                  <span>Issue triage</span>
                  <strong>{state.issueData?.summary.total_open_issues || 0} open</strong>
                </div>
                <p className="surfaceCopy">
                  {(state.issueData?.summary.ready_to_triage || 0)} triage-ready · {(state.issueData?.summary.stale_issues || 0)} stale · {(state.issueData?.summary.unassigned_issues || 0)} unassigned
                </p>
                <div className="mechanismList">
                  {(state.issueData?.repos || []).slice(0, 4).map((repo) => (
                    <article key={repo.repo}>
                      <div>
                        <span>{repoName(repo.repo)}</span>
                        <strong>{repo.ready_to_triage_count} ready · {repo.unlabeled_count} unlabeled</strong>
                      </div>
                      <b>{repo.count}</b>
                    </article>
                  ))}
                </div>
              </section>

              <section className="surfacePanel">
                <div className="panelTitle">
                  <span>Repo health</span>
                  <strong>{state.repoHealthData?.summary.degraded_repos || 0} degraded</strong>
                </div>
                <p className="surfaceCopy">
                  {(state.repoHealthData?.summary.failing_workflows || 0)} failing workflow runs · {(state.repoHealthData?.summary.in_progress_runs || 0)} in progress
                </p>
                <div className="mechanismList">
                  {(state.repoHealthData?.repos || []).slice(0, 4).map((repo) => (
                    <article key={repo.repo}>
                      <div>
                        <span>{repoName(repo.repo)}</span>
                        <strong>{repo.latest_run?.name || "No latest run"}</strong>
                        <code>{repo.latest_run?.conclusion || repo.latest_run?.status || repo.status}</code>
                      </div>
                      <b>{repo.status}</b>
                    </article>
                  ))}
                </div>
              </section>

              <section className="surfacePanel">
                <div className="panelTitle">
                  <span>Mechanisms</span>
                  <strong>Steering controls</strong>
                </div>
                <div className="mechanismList">
                  {statusData.mechanisms.map((mechanism) => (
                    <article key={mechanism.id}>
                      <div>
                        <span>{mechanism.agent} · {mechanism.mode}</span>
                        <strong>{mechanism.label}</strong>
                        <code>{mechanism.command}</code>
                      </div>
                      <b>{mechanism.count}</b>
                    </article>
                  ))}
                </div>
              </section>

              <section className="surfacePanel">
                <div className="panelTitle">
                  <span>Runtime</span>
                  <strong>{state.readiness?.status || "unknown"}</strong>
                </div>
                <p className="surfaceCopy">API runtime: {state.manifest?.source.api_runtime || "connected"}. Backend controls are attached.</p>
                {state.readiness?.checks.length ? (
                  <div className="readinessList">
                    {state.readiness.checks.map((check) => (
                      <article key={check.id}>
                        <span className={`status ${check.status === "fail" ? "red" : check.status === "warn" ? "amber" : "green"}`}>{check.status}</span>
                        <div>
                          <strong>{check.id.replaceAll("_", " ")}</strong>
                          <p>{check.detail}</p>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : null}
                {state.readiness?.next_actions.length ? (
                  <div className="nextActionList">
                    {state.readiness.next_actions.map((action) => <code key={action}>{action}</code>)}
                  </div>
                ) : null}
              </section>
            </aside>
          </section>
        </>
      )}
    </main>
  );
}
