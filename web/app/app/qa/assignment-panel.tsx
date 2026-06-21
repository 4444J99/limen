"use client";

import { useEffect, useMemo, useState } from "react";
import type { QASteeringItem } from "../lib/data";

type AssignState = {
  loading: boolean;
  result: string;
  error: string;
};

const priorities = ["critical", "high", "medium", "low", "backlog"];
const agents = [
  "jules",
  "codex",
  "claude",
  "opencode",
  "agy",
  "gemini",
  "copilot",
  "warp",
  "oz",
  "github_actions",
  "any",
];

export default function AssignmentPanel({
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
  const candidates = useMemo(() => items.filter((item) => item.phase !== "archive"), [items]);
  const [taskId, setTaskId] = useState(candidates[0]?.id || "");
  const selected = candidates.find((item) => item.id === taskId) || candidates[0];
  const [agent, setAgent] = useState(selected?.assignee || "jules");
  const [priority, setPriority] = useState(selected?.priority || "high");
  const [budgetCost, setBudgetCost] = useState("1");
  const [apiToken, setApiToken] = useState(initialToken);
  const [state, setState] = useState<AssignState>({ loading: false, result: "", error: "" });
  const apiReady = Boolean(apiUrl);

  useEffect(() => {
    if (!selected) return;
    setAgent(selected.assignee || "jules");
    setPriority(selected.priority || "high");
    setBudgetCost("1");
    setState({ loading: false, result: "", error: "" });
  }, [selected?.id, selected?.assignee, selected?.priority]);

  async function assignTask() {
    if (!apiReady || !selected || state.loading) return;
    setState({ loading: true, result: "", error: "" });
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
    try {
      const response = await fetch(`${apiUrl}/api/tasks/${encodeURIComponent(selected.id)}/assign`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          target_agent: agent,
          priority,
          budget_cost: Number(budgetCost) || 1,
          status: "open",
          note: "Assigned from QA steering panel",
          session_id: "qa-panel",
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || response.statusText);
      setState({ loading: false, result: `${selected.id} assigned to ${agent}`, error: "" });
      void onComplete?.();
    } catch (error) {
      setState({ loading: false, result: "", error: error instanceof Error ? error.message : "Assignment failed" });
    }
  }

  return (
    <section className="surfacePanel">
      <div className="panelTitle">
        <span>Assignment</span>
        <strong>{apiReady ? "API assignment ready" : "API assignment unavailable"}</strong>
      </div>
      <div className="assignPanel">
        <label>
          <span>Task</span>
          <select value={taskId} onChange={(event) => setTaskId(event.target.value)} disabled={!apiReady || !candidates.length}>
            {candidates.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} · {item.phase}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Agent</span>
          <select value={agent} onChange={(event) => setAgent(event.target.value)} disabled={!apiReady}>
            {agents.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>
          <span>Priority</span>
          <select value={priority} onChange={(event) => setPriority(event.target.value)} disabled={!apiReady}>
            {priorities.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>
          <span>Cost</span>
          <input value={budgetCost} onChange={(event) => setBudgetCost(event.target.value)} min="1" type="number" disabled={!apiReady} />
        </label>
        {!initialToken && (
          <label>
            <span>Token</span>
            <input value={apiToken} onChange={(event) => setApiToken(event.target.value)} type="password" disabled={!apiReady} />
          </label>
        )}
        <button onClick={assignTask} disabled={!apiReady || !selected || state.loading}>
          {state.loading ? "Assigning" : "Assign"}
        </button>
        {!apiReady && <p>Build with NEXT_PUBLIC_API_URL to enable assignment.</p>}
        {(state.result || state.error) && <p className={state.error ? "opsError" : "opsResult"}>{state.error || state.result}</p>}
      </div>
    </section>
  );
}
