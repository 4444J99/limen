import SurfaceNav from "../surface-nav";
import { formatDate, getObservatoryBriefData } from "../lib/data";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Observatory",
  description: "Observatory — daily brief on GitHub legibility gaps, transferable winner mechanisms, and active experiments.",
};

function confounderLabel(c: string | { name?: string; discount?: number }): string {
  if (typeof c === "string") return c;
  return c.name ?? JSON.stringify(c);
}

export default function ObservatoryPage() {
  const data = getObservatoryBriefData();
  const experiment = data.experiment;
  const contract = experiment?.measurement_contract ?? data.measurement_contract ?? null;
  const hasBrief = data.status === "ok";

  return (
    <main className="shell observatoryShell">
      <SurfaceNav active="observatory" />
      <header className="topbar">
        <div>
          <p className="caption">Owner surface</p>
          <h1>Observatory</h1>
        </div>
        <div className="topbarMeta">
          <span>{hasBrief ? "Latest daily brief" : "No brief yet"}</span>
          <span>{formatDate(data.generated_at)}</span>
        </div>
      </header>

      {!hasBrief ? (
        <section className="surfacePanel">
          <div className="panelTitle">
            <span>Legibility &amp; traction</span>
            <strong>Organ ships dark</strong>
          </div>
          <p className="muted">
            No brief has been produced yet. OBSERVATORY runs read-only against public GitHub surfaces
            and is gated off by <code>LIMEN_OBSERVATORY=0</code> until armed by the lever{" "}
            <code>L-OBSERVATORY-ACTIVATE</code>. Once armed, each daily beat writes{" "}
            <code>logs/observatory/brief-latest.json</code> and this page renders it.
          </p>
        </section>
      ) : (
        <>
          <section className="metrics">
            <div className="metric blue">
              <span>Internal gaps</span>
              <strong>{data.internal_gaps.toLocaleString()}</strong>
              <p>own public numbers vs. truth</p>
            </div>
            <div className="metric green">
              <span>External gaps</span>
              <strong>{data.external_gaps.toLocaleString()}</strong>
              <p>winner mechanisms we lack</p>
            </div>
            <div className="metric amber">
              <span>Mechanisms</span>
              <strong>{data.mechanisms.length}</strong>
              <p>{data.confounders.length} confounder(s) discounting</p>
            </div>
            <div className="metric violet">
              <span>Hero</span>
              <strong>{data.hero ?? "—"}</strong>
              <p>highest-ranked repo with a gap</p>
            </div>
          </section>

          {experiment ? (
            <section className="surfacePanel">
              <div className="panelTitle">
                <span>Today&apos;s experiment ({experiment.kind})</span>
                <strong>{experiment.reversible ? "Reversible" : "Irreversible"}</strong>
              </div>
              <p className="observatoryChange">{experiment.change}</p>
              {contract ? (
                <ul className="rankList">
                  <li>
                    <span>Metric vector</span>
                    <strong>{contract.metric_vector.join(", ") || "—"}</strong>
                  </li>
                  <li>
                    <span>Observation window</span>
                    <strong>{contract.observation_window_days} days</strong>
                  </li>
                  <li>
                    <span>Success predicate</span>
                    <strong>{contract.success_predicate}</strong>
                  </li>
                  <li>
                    <span>Failure criterion</span>
                    <strong>{contract.failure_criterion}</strong>
                  </li>
                  <li>
                    <span>Reversal path</span>
                    <strong>{contract.reversal_path}</strong>
                  </li>
                </ul>
              ) : null}
              <p className="muted">
                Human-gated proposal — dry by default; nothing is applied to a public surface without
                the lever.
              </p>
            </section>
          ) : null}

          <section className="surfacePanel">
            <div className="panelTitle">
              <span>Transferable mechanisms</span>
              <strong>{data.mechanisms.length}</strong>
            </div>
            {data.mechanisms.length ? (
              <ul className="rankList">
                {data.mechanisms.map((m, i) => (
                  <li key={`${m.mechanism}-${i}`}>
                    <span>
                      {m.mechanism} <em className="muted">({m.winner})</em>
                    </span>
                    <strong>{m.priority.toFixed(1)}</strong>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No mechanisms observed this run.</p>
            )}
          </section>

          {data.confounders.length ? (
            <section className="surfacePanel">
              <div className="panelTitle">
                <span>Confounders (discount explanatory strength)</span>
                <strong>{data.confounders.length}</strong>
              </div>
              <ul className="rankList">
                {data.confounders.map((c, i) => (
                  <li key={`confounder-${i}`}>
                    <span>{confounderLabel(c)}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </main>
  );
}
