"use client";

import { useState } from "react";

type RuntimeState = {
  loading: boolean;
  result: string;
  error: string;
};

export default function RuntimeStatusPanel({
  apiUrl,
  endpoint,
  title,
  tokenRequired = false,
  initialToken = "",
}: {
  apiUrl: string;
  endpoint: "/api/client-status" | "/api/public-status";
  title: string;
  tokenRequired?: boolean;
  initialToken?: string;
}) {
  const [apiToken, setApiToken] = useState(initialToken);
  const [state, setState] = useState<RuntimeState>({ loading: false, result: "", error: "" });
  const apiReady = Boolean(apiUrl);

  async function refreshRuntime() {
    if (!apiReady || state.loading) return;
    setState({ loading: true, result: "", error: "" });
    const headers: Record<string, string> = {};
    if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
    try {
      const response = await fetch(`${apiUrl}${endpoint}`, { headers });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || response.statusText);
      const summary = payload.summary || {};
      const generated = summary.generated_at ? new Date(summary.generated_at).toLocaleString() : "runtime";
      setState({
        loading: false,
        result: `${summary.total ?? 0} tasks · ${summary.completed ?? 0} closed · ${generated}`,
        error: "",
      });
    } catch (error) {
      setState({ loading: false, result: "", error: error instanceof Error ? error.message : "Runtime refresh failed" });
    }
  }

  return (
    <div className="runtimePanel">
      <div className="panelTitle">
        <span>Runtime</span>
        <strong>{apiReady ? title : "Static snapshot only"}</strong>
      </div>
      {tokenRequired && !initialToken && (
        <input
          value={apiToken}
          onChange={(event) => setApiToken(event.target.value)}
          placeholder="Client token"
          type="password"
          disabled={!apiReady}
        />
      )}
      <button onClick={refreshRuntime} disabled={!apiReady || state.loading}>
        {state.loading ? "Refreshing" : "Refresh"}
      </button>
      {!apiReady && <p>Build with NEXT_PUBLIC_API_URL to enable runtime refresh.</p>}
      {(state.result || state.error) && <p className={state.error ? "opsError" : "opsResult"}>{state.error || state.result}</p>}
    </div>
  );
}
