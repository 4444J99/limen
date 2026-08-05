import SurfaceNav from "../surface-nav";
import { formatDate, getCorpusCommandCenterData } from "../lib/data";
import CorpusCommandCenterClient from "./corpus-command-center-client";
import type { Metadata } from "next";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Corpus",
  description: "Corpus Command Center — prompt atlas coverage, cluster stats, and Aug 1 readiness gate.",
};

export default function CorpusCommandCenterPage() {
  const data = getCorpusCommandCenterData();
  const coverage = data.coverage;

  return (
    <main className="shell corpusShell">
      <SurfaceNav active="corpus" />
      <header className="topbar">
        <div>
          <p className="caption">Owner surface</p>
          <h1>Corpus Command Center</h1>
        </div>
        <div className="topbarMeta">
          <span>{data.status === "ok" ? "Redacted snapshot" : "Snapshot missing"}</span>
          <span>{formatDate(data.generated_at)}</span>
        </div>
      </header>

      <section className="metrics">
        <div className="metric blue">
          <span>Units</span>
          <strong>{coverage.units.toLocaleString()}</strong>
          <p>{coverage.sessions_indexed.toLocaleString()} sessions indexed</p>
        </div>
        <div className="metric green">
          <span>Clusters</span>
          <strong>{coverage.clusters.toLocaleString()}</strong>
          <p>{coverage.unique_hashes.toLocaleString()} unique hashes</p>
        </div>
        <div className="metric amber">
          <span>Comparisons</span>
          <strong>{coverage.comparisons.toLocaleString()}</strong>
          <p>{coverage.allusion_rows.toLocaleString()} allusion rows</p>
        </div>
        <div className={data.aug1.gate_pass ? "metric green" : "metric red"}>
          <span>Aug 1</span>
          <strong>{data.aug1.legs_met}/{data.aug1.legs_total}</strong>
          <p>{data.aug1.deadline}</p>
        </div>
        <div className="metric blue">
          <span>Inbound</span>
          <strong>{data.inbound.seeded_repo_count}</strong>
          <p>{data.inbound.value_repo_count} value repos</p>
        </div>
      </section>

      <CorpusCommandCenterClient data={data} />
    </main>
  );
}
