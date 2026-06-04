"use client";

import { useState } from "react";
import type { QASteeringItem } from "../lib/data";

type RecoveryState = {
  loading: "preview" | "release" | "";
  result: string;
  error: string;
  candidates: RecoveryCandidate[];
  previewedHours: string;
};

type RecoveryCandidate = {
  id?: string;
  title?: string;
  agent?: string;
  status?: string;
  latest?: string | null;
};

export default function RecoveryPanel({
  items,
  apiUrl,
  initialToken = "",
  onComplete,
}: {
  items: QASteeringItem[];
  apiUrl: string;
  initialToken?: string;
  onComplete?: () => void | Promise<void>;
}) {
  const [hours, setHours] = useState("24");
  const [apiToken, setApiToken] = useState(initialToken);
  const [state, setState] = useState<RecoveryState>({ loading: "", result: "", error: "", candidates: [], previewedHours: "" });
  const apiReady = Boolean(apiUrl);
  const normalizedHours = String(Number(hours) || 24);
  const releaseReady = state.previewedHours === normalizedHours && state.candidates.length > 0;

  async function releaseStale(dryRun: boolean) {
    if (!apiReady || state.loading) return;
    setState((current) => ({ ...current, loading: dryRun ? "preview" : "release", result: "", error: "", candidates: dryRun ? [] : current.candidates }));
    const headers: Record<string, string> = {};
    if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
    try {
      const params = new URLSearchParams({
        hours: normalizedHours,
        dry_run: dryRun ? "true" : "false",
      });
      const response = await fetch(`${apiUrl}/api/release-stale?${params.toString()}`, {
        method: "POST",
        headers,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || response.statusText);
      const verb = dryRun ? "candidate" : "released";
      const candidates = (payload.candidates || []) as RecoveryCandidate[];
      setState({
        loading: "",
        result: `${payload.count || 0} ${verb}${payload.count === 1 ? "" : "s"}`,
        error: "",
        candidates: dryRun ? candidates : [],
        previewedHours: dryRun ? normalizedHours : "",
      });
      if (!dryRun) void onComplete?.();
    } catch (error) {
      setState((current) => ({ ...current, loading: "", result: "", error: error instanceof Error ? error.message : "Recovery failed" }));
    }
  }

  return (
    <section className="surfacePanel">
      <div className="panelTitle">
        <span>Recovery</span>
        <strong>{apiReady ? "API recovery ready" : "API recovery unavailable"}</strong>
      </div>
      <div className="assignPanel">
        <label>
          <span>Window</span>
          <input value={hours} onChange={(event) => setHours(event.target.value)} min="1" type="number" disabled={!apiReady} />
        </label>
        {!initialToken && (
          <label>
            <span>Token</span>
            <input value={apiToken} onChange={(event) => setApiToken(event.target.value)} type="password" disabled={!apiReady} />
          </label>
        )}
        <div className="buttonRow">
          <button onClick={() => releaseStale(true)} disabled={!apiReady || state.loading !== ""}>
            {state.loading === "preview" ? "Checking" : "Preview"}
          </button>
          <button onClick={() => releaseStale(false)} disabled={!apiReady || state.loading !== "" || !releaseReady}>
            {state.loading === "release" ? "Releasing" : "Release"}
          </button>
        </div>
        {state.candidates.length > 0 && (
          <div className="recoveryPreview" aria-label="Recovery preview candidates">
            {state.candidates.slice(0, 8).map((item) => (
              <article key={item.id}>
                <span className="mono">{item.id}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.agent || "unknown"} · {item.status || "active"} · {item.latest || "no latest event"}</p>
                </div>
              </article>
            ))}
          </div>
        )}
        <div className="miniQueue">
          {items.slice(0, 5).map((item) => (
            <span key={item.id}>{item.id}</span>
          ))}
        </div>
        {!apiReady && <p>Build with NEXT_PUBLIC_API_URL to enable recovery.</p>}
        {(state.result || state.error) && <p className={state.error ? "opsError" : "opsResult"}>{state.error || state.result}</p>}
      </div>
    </section>
  );
}
