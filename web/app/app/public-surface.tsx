import SurfaceNav from "./surface-nav";
import { formatDate, getPublicSurfaceData } from "./lib/data";
import RuntimeStatusPanel from "./runtime-status-panel";

function formatNumber(value?: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value || 0);
}

function statusLabel(status: string) {
  return status.replace(/_/g, " ");
}

export default function PublicSurface() {
  const { statusData, prData, manifest } = getPublicSurfaceData();
  const summary = statusData.summary;
  const throughput = summary.throughput;
  const prSummary = prData?.summary;
  const completion = Math.round(summary.completion_rate * 100);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
  const active = summary.active || 0;
  const notDone = throughput?.not_done ?? Math.max(0, summary.total - summary.completed);
  const unrecordedCapacityRuns = throughput?.unrecorded_capacity_runs ?? null;

  return (
    <main className="audienceShell publicCockpit">
      <SurfaceNav active="public" persona="public" />
      <header className="publicHero">
        <div>
          <h1>
            <span>Limen is tracking {formatNumber(summary.total)}</span>
            <span>cross-agent tasks.</span>
          </h1>
          <p>
            <span>{formatNumber(summary.completed)} done, {formatNumber(notDone)} not done, {formatNumber(active)} active.</span>
            <span>{throughput ? `Created ${throughput.first_created}; ledger ${throughput.current_date}.` : "Public static snapshot is waiting on the throughput ledger."}</span>
          </p>
        </div>
        <a className="heroAction" href="/internal">Owner console</a>
      </header>

      <section className="publicOpsGrid" aria-label="Execution ledger">
        <div className="publicMetric primary">
          <span>Run plan</span>
          <strong>{throughput ? `${formatNumber(throughput.task_burndown_target_per_day)}/day` : "n/a"}</strong>
          <p>{throughput ? `${throughput.age_days} inclusive days at ${formatNumber(throughput.daily_capacity)} run slots/day` : "Rebuild static data to publish this calculation."}</p>
        </div>
        <div className="publicMetric">
          <span>Recorded starts</span>
          <strong>{formatNumber(throughput?.recorded_starts)}</strong>
          <p>{throughput ? `${formatNumber(throughput.recorded_events)} log events, ${formatNumber(throughput.recorded_finishes)} finishes` : "No public ledger yet"}</p>
        </div>
        <div className="publicMetric">
          <span>Unrecorded capacity</span>
          <strong>{unrecordedCapacityRuns === null ? "n/a" : formatNumber(unrecordedCapacityRuns)}</strong>
          <p>{throughput ? `${formatNumber(throughput.expected_capacity_runs)} expected slots minus recorded starts` : "Not available in this snapshot"}</p>
        </div>
        <div className="publicMetric">
          <span>Completion</span>
          <strong>{completion}%</strong>
          <p>{formatNumber(summary.completed)} closed of {formatNumber(summary.total)}</p>
        </div>
      </section>

      <section className="publicStatusBand" aria-label="Current work state">
        <div className="surfacePanel wide">
          <div className="panelTitle">
            <span>What got done</span>
            <strong>{formatNumber(summary.completed)} completed tasks are recorded on the board</strong>
          </div>
          <p className="surfaceCopy">
            Public status stays aggregate-only. It shows the operational ledger and completion state without exposing task titles, dispatch logs, tokens, or owner controls.
          </p>
          <div className="publicSplit">
            <div>
              <span>Done</span>
              <strong>{formatNumber(summary.completed)}</strong>
            </div>
            <div>
              <span>Not done</span>
              <strong>{formatNumber(notDone)}</strong>
            </div>
            <div>
              <span>Active</span>
              <strong>{formatNumber(active)}</strong>
            </div>
          </div>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>What is not done</span>
            <strong>Status mix</strong>
          </div>
          <ul className="rankList">
            {Object.entries(summary.by_status).map(([status, count]) => (
              <li key={status}><span>{statusLabel(status)}</span><strong>{formatNumber(count)}</strong></li>
            ))}
          </ul>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Runtime</span>
            <strong>{manifest.source.api_runtime}</strong>
          </div>
          <p className="surfaceCopy">Static snapshot generated {formatDate(summary.generated_at)}. Hosted public contracts remain aggregate-only.</p>
          <a className="contractLink" href="/public-status.json">Public contract</a>
          <a className="contractLink" href="/public-surface-manifest.json">Surface manifest</a>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Pull requests</span>
            <strong>{formatNumber(prSummary?.total_open_prs)} open across {formatNumber(prSummary?.total_repos)} tracked repos</strong>
          </div>
          <p className="surfaceCopy">{formatNumber(prSummary?.prs_with_failing_ci)} open pull requests currently report failing CI checks.</p>
        </div>

        <div className="surfacePanel">
          <RuntimeStatusPanel
            apiUrl={apiUrl}
            endpoint="/api/public-status"
            title="Public runtime refresh"
          />
        </div>
      </section>
    </main>
  );
}
