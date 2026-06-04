import SurfaceNav from "../surface-nav";
import { formatDate, getPublicSurfaceData } from "../lib/data";
import RuntimeStatusPanel from "../runtime-status-panel";

export const dynamic = "force-static";

export default function PublicSurface() {
  const { statusData, prData, manifest } = getPublicSurfaceData();
  const summary = statusData.summary;
  const prSummary = prData?.summary;
  const completion = Math.round(summary.completion_rate * 100);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";

  return (
    <main className="audienceShell publicShell">
      <SurfaceNav active="public" persona="public" />
      <header className="audienceHeader publicHeader">
        <p className="caption">Public Surface</p>
        <h1>Limen</h1>
        <p>Operational signal for a cross-agent task intake system coordinating async software work.</p>
      </header>

      <section className="publicSignal" aria-label="Public status">
        <div>
          <span>Task intake</span>
          <strong>{summary.total}</strong>
        </div>
        <div>
          <span>Completed</span>
          <strong>{completion}%</strong>
        </div>
        <div>
          <span>Open PRs tracked</span>
          <strong>{prSummary?.total_open_prs || 0}</strong>
        </div>
        <div>
          <span>CI attention</span>
          <strong>{prSummary?.prs_with_failing_ci || 0}</strong>
        </div>
      </section>

      <section className="audienceGrid">
        <div className="surfacePanel wide">
          <div className="panelTitle">
            <span>Status</span>
            <strong>Static snapshot published from the current task board</strong>
          </div>
          <p className="surfaceCopy">
            The public view reports aggregate execution health only. Internal task controls, tokens, dispatch logs, and full task details stay on the internal surface.
          </p>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Top areas</span>
            <strong>Workload signal</strong>
          </div>
          <ul className="rankList">
            {Object.entries(summary.by_status).slice(0, 5).map(([status, count]) => (
              <li key={status}><span>{status}</span><strong>{count}</strong></li>
            ))}
          </ul>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Updated</span>
            <strong>{formatDate(summary.generated_at)}</strong>
          </div>
          <p className="surfaceCopy">Firebase Hosting is live. API runtime: {manifest.source.api_runtime}. Public contract only.</p>
          <a className="contractLink" href="/public-surface-manifest.json">Surface manifest</a>
          <a className="contractLink" href="/public-status.json">Public contract</a>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Pull requests</span>
            <strong>{prSummary?.total_open_prs || 0} open across {prSummary?.total_repos || 0} tracked repos</strong>
          </div>
          <p className="surfaceCopy">{prSummary?.prs_with_failing_ci || 0} open pull requests currently report failing CI checks. Public status keeps this aggregate-only.</p>
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
