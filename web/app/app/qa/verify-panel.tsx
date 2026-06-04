"use client";

import { useEffect, useMemo, useState } from "react";
import type { QASteeringItem } from "../lib/data";

type VerifyState = {
  loading: boolean;
  result: string;
  error: string;
};

const statuses = ["done", "needs_human", "failed", "failed_blocked"];

export default function VerifyPanel({
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
  const candidates = useMemo(() => items.filter((item) => item.phase === "verify"), [items]);
  const [taskId, setTaskId] = useState(candidates[0]?.id || "");
  const selected = candidates.find((item) => item.id === taskId) || candidates[0];
  const [status, setStatus] = useState("done");
  const [note, setNote] = useState("");
  const [apiToken, setApiToken] = useState(initialToken);
  const [state, setState] = useState<VerifyState>({ loading: false, result: "", error: "" });
  const apiReady = Boolean(apiUrl);

  useEffect(() => {
    setStatus("done");
    setNote("");
    setState({ loading: false, result: "", error: "" });
  }, [selected?.id]);

  async function verifyTask() {
    if (!apiReady || !selected || state.loading) return;
    setState({ loading: true, result: "", error: "" });
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
    try {
      const response = await fetch(`${apiUrl}/api/tasks/${encodeURIComponent(selected.id)}/verify`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          status,
          note: note || `Verified from QA steering panel as ${status}`,
          session_id: "qa-panel",
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || response.statusText);
      setState({ loading: false, result: `${selected.id} verified as ${status}`, error: "" });
      void onComplete?.();
    } catch (error) {
      setState({ loading: false, result: "", error: error instanceof Error ? error.message : "Verification failed" });
    }
  }

  return (
    <section className="surfacePanel">
      <div className="panelTitle">
        <span>Verification</span>
        <strong>{apiReady ? "API verification ready" : "API verification unavailable"}</strong>
      </div>
      <div className="assignPanel">
        <label>
          <span>Task</span>
          <select value={taskId} onChange={(event) => setTaskId(event.target.value)} disabled={!apiReady || !candidates.length}>
            {candidates.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} · {item.status}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Result</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)} disabled={!apiReady}>
            {statuses.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>
          <span>Note</span>
          <input value={note} onChange={(event) => setNote(event.target.value)} disabled={!apiReady} />
        </label>
        {!initialToken && (
          <label>
            <span>Token</span>
            <input value={apiToken} onChange={(event) => setApiToken(event.target.value)} type="password" disabled={!apiReady} />
          </label>
        )}
        <button onClick={verifyTask} disabled={!apiReady || !selected || state.loading}>
          {state.loading ? "Verifying" : "Verify"}
        </button>
        {!apiReady && <p>Build with NEXT_PUBLIC_API_URL to enable verification.</p>}
        {(state.result || state.error) && <p className={state.error ? "opsError" : "opsResult"}>{state.error || state.result}</p>}
      </div>
    </section>
  );
}
