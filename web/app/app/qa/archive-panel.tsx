"use client";

import { useEffect, useState } from "react";
import type { QASteeringItem } from "../lib/data";

type ArchiveState = {
  loading: boolean;
  result: string;
  error: string;
};

export default function ArchivePanel({
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
  const [taskId, setTaskId] = useState(items[0]?.id || "");
  const selected = items.find((item) => item.id === taskId) || items[0];
  const [confirmedId, setConfirmedId] = useState("");
  const [apiToken, setApiToken] = useState(initialToken);
  const [state, setState] = useState<ArchiveState>({ loading: false, result: "", error: "" });
  const apiReady = Boolean(apiUrl);
  const archiveReady = Boolean(selected && confirmedId === selected.id);

  useEffect(() => {
    setConfirmedId("");
    setState({ loading: false, result: "", error: "" });
  }, [selected?.id]);

  async function archiveTask() {
    if (!apiReady || !selected || !archiveReady || state.loading) return;
    setState({ loading: true, result: "", error: "" });
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
    try {
      const response = await fetch(`${apiUrl}/api/tasks/${encodeURIComponent(selected.id)}/archive`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          note: "Archived from QA steering panel",
          session_id: "qa-panel",
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || response.statusText);
      setState({ loading: false, result: `${selected.id} archived`, error: "" });
      void onComplete?.();
    } catch (error) {
      setState({ loading: false, result: "", error: error instanceof Error ? error.message : "Archive failed" });
    }
  }

  return (
    <section className="surfacePanel">
      <div className="panelTitle">
        <span>Archive</span>
        <strong>{apiReady ? "API archive ready" : "API archive unavailable"}</strong>
      </div>
      <div className="assignPanel">
        <label>
          <span>Task</span>
          <select
            value={taskId}
            onChange={(event) => {
              setTaskId(event.target.value);
              setConfirmedId("");
            }}
            disabled={!apiReady || !items.length}
          >
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} · {item.status}
              </option>
            ))}
          </select>
        </label>
        {!initialToken && (
          <label>
            <span>Token</span>
            <input value={apiToken} onChange={(event) => setApiToken(event.target.value)} type="password" disabled={!apiReady} />
          </label>
        )}
        {selected && (
          <div className="archiveConfirm">
            <strong>{selected.id}</strong>
            <p>{selected.title}</p>
            <em>{selected.next_gate}</em>
            <button onClick={() => setConfirmedId(selected.id)} disabled={!apiReady || state.loading || archiveReady}>
              {archiveReady ? "Confirmed" : "Confirm closure"}
            </button>
          </div>
        )}
        <button onClick={archiveTask} disabled={!apiReady || !selected || !archiveReady || state.loading}>
          {state.loading ? "Archiving" : "Archive"}
        </button>
        {!apiReady && <p>Build with NEXT_PUBLIC_API_URL to enable archive closure.</p>}
        {(state.result || state.error) && <p className={state.error ? "opsError" : "opsResult"}>{state.error || state.result}</p>}
      </div>
    </section>
  );
}
