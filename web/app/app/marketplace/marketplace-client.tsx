"use client";

import { useState } from "react";
import SurfaceNav from "../surface-nav";

export interface AgentApp {
  id: string;
  name: string;
  category: "Coding" | "Reasoning" | "Orchestration" | "CI/CD";
  status: "Installed" | "Available";
  description: string;
  capabilities: string[];
  version: string;
}

const AGENT_APPS: AgentApp[] = [
  {
    id: "jules",
    name: "Jules",
    category: "Coding",
    status: "Installed",
    description: "Autonomous coding agent & async task executor with Jules capacity recovery.",
    capabilities: ["Autonomous Code Edit", "Async Task Dispatch", "Worktree Scoping"],
    version: "2.4.0",
  },
  {
    id: "codex",
    name: "Codex",
    category: "Coding",
    status: "Installed",
    description: "Specialized code generation, static analysis, and fast patch creation.",
    capabilities: ["Patch Generation", "Refactoring", "Type Safety Check"],
    version: "1.8.2",
  },
  {
    id: "claude",
    name: "Claude",
    category: "Reasoning",
    status: "Installed",
    description: "Strategic architecture review, complex reasoning, and multi-file synthesis.",
    capabilities: ["Architectural Review", "Multi-file Editing", "Handoff Synthesis"],
    version: "3.5.0",
  },
  {
    id: "opencode",
    name: "OpenCode",
    category: "Coding",
    status: "Available",
    description: "Open-source multi-model substrate for flexible local & cloud execution.",
    capabilities: ["Multi-Model Support", "Local Inference", "Custom Drivers"],
    version: "0.9.1",
  },
  {
    id: "agy",
    name: "Agy",
    category: "Orchestration",
    status: "Installed",
    description: "Peer-conductor protocol agent for authenticated work harvesting & graph splitting.",
    capabilities: ["Graph Splitting", "Conductor Protocol", "Lease Management"],
    version: "2.1.0",
  },
  {
    id: "gemini",
    name: "Gemini",
    category: "Reasoning",
    status: "Installed",
    description: "Large context window analysis, multimodal evaluation, and rapid search.",
    capabilities: ["Large Context Search", "Documentation Indexing", "Multimodal Analysis"],
    version: "1.5.0",
  },
  {
    id: "copilot",
    name: "Copilot",
    category: "Coding",
    status: "Available",
    description: "AI pair programmer & automated GitHub PR reviewer.",
    capabilities: ["PR Review", "Inline Suggestion", "Automated Diff Check"],
    version: "1.12.0",
  },
  {
    id: "warp",
    name: "Warp",
    category: "Orchestration",
    status: "Available",
    description: "Terminal automation & worktree shell integration.",
    capabilities: ["Terminal Execution", "Worktree Isolation", "Command Piping"],
    version: "0.8.0",
  },
  {
    id: "oz",
    name: "Oz",
    category: "Orchestration",
    status: "Available",
    description: "System automation & cross-component workflow orchestration engine.",
    capabilities: ["Workflow Automation", "Event Triggers", "State Persistence"],
    version: "1.0.4",
  },
  {
    id: "github_actions",
    name: "GitHub Actions",
    category: "CI/CD",
    status: "Installed",
    description: "Automated CI gate execution, build validation, and remote runner dispatch.",
    capabilities: ["CI Pipeline Run", "PR Gate Validation", "Artifact Management"],
    version: "4.0.0",
  },
];

type TaskFormState = {
  title: string;
  repo: string;
  target_agent: string;
  priority: string;
  budget_cost: string;
  predicate: string;
  receipt_target: string;
  token: string;  // allow-secret
  loading: boolean;
  result: string;
  error: string;
};

export default function MarketplaceClient({ apiUrl }: { apiUrl: string }) {
  const [apps, setApps] = useState<AgentApp[]>(AGENT_APPS);
  const [categoryFilter, setCategoryFilter] = useState<string>("All");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedApp, setSelectedApp] = useState<AgentApp | null>(null);

  const [form, setForm] = useState<TaskFormState>({
    title: "",
    repo: "organvm/limen",
    target_agent: "jules",
    priority: "high",
    budget_cost: "1",
    predicate: "scripts/verify-scoped.sh",
    receipt_target: "github_pr",
    token: "",
    loading: false,
    result: "",
    error: "",
  });

  const filteredApps = apps.filter((app) => {
    const matchesCategory = categoryFilter === "All" || app.category === categoryFilter;
    const matchesSearch =
      app.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      app.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  function toggleInstall(appId: string) {
    setApps((prev) =>
      prev.map((app) =>
        app.id === appId
          ? { ...app, status: app.status === "Installed" ? "Available" : "Installed" }
          : app
      )
    );
    if (selectedApp?.id === appId) {
      setSelectedApp((prev) => (prev ? { ...prev, status: prev.status === "Installed" ? "Available" : "Installed" } : null));
    }
  }

  async function handleSubmitTask(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) {
      setForm((f) => ({ ...f, error: "Task title is required" }));
      return;
    }
    setForm((f) => ({ ...f, loading: true, result: "", error: "" }));

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (form.token) {
      headers.Authorization = `Bearer ${form.token}`;
    }

    const payload = {
      title: form.title,
      repo: form.repo,
      target_agent: form.target_agent,
      priority: form.priority,
      budget_cost: Number(form.budget_cost) || 1,
      predicate: form.predicate,
      receipt_target: form.receipt_target,
    };

    try {
      const targetUrl = apiUrl ? `${apiUrl}/api/tasks` : "/api/tasks";
      const res = await fetch(targetUrl, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || res.statusText || "Failed to create task");
      }

      setForm((f) => ({
        ...f,
        loading: false,
        result: `Task submitted successfully! ID: ${data.id || data.task_id || "created"}`,
        error: "",
        title: "",
      }));
    } catch (err) {
      setForm((f) => ({
        ...f,
        loading: false,
        result: "",
        error: err instanceof Error ? err.message : "Task submission failed",
      }));
    }
  }

  return (
    <main className="audienceShell">
      <SurfaceNav active="marketplace" persona="client" />

      <header className="audienceHeader clientHeader">
        <p className="caption">Marketplace Catalog</p>
        <h1>Agent Integrations & Application Hub</h1>
        <p>Discover, install, and dispatch task requests across multi-agent operational lanes.</p>
      </header>

      <section className="audienceMetrics" aria-label="Marketplace overview metrics">
        <div>
          <span>Total Integrations</span>
          <strong>{apps.length}</strong>
          <p>Available agent connectors</p>
        </div>
        <div>
          <span>Installed</span>
          <strong>{apps.filter((a) => a.status === "Installed").length}</strong>
          <p>Active execution lanes</p>
        </div>
        <div>
          <span>Categories</span>
          <strong>4</strong>
          <p>Coding, Reasoning, Orchestration, CI/CD</p>
        </div>
        <div>
          <span>Status</span>
          <strong>{apiUrl ? "API Connected" : "Static Preview"}</strong>
          <p>{apiUrl ? "POST /api/tasks ready" : "Configure NEXT_PUBLIC_API_URL"}</p>
        </div>
      </section>

      <section className="audienceGrid">
        <div className="surfacePanel wide">
          <div className="panelTitle">
            <span>Integration Catalog</span>
            <strong>Browse & Install Agent Connectors</strong>
          </div>

          <div className="filterControls" style={{ display: "flex", gap: "1rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder="Search agent integrations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ padding: "0.5rem 0.75rem", borderRadius: "6px", border: "1px solid #d1d5db", flex: "1", minWidth: "200px" }}
            />
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {["All", "Coding", "Reasoning", "Orchestration", "CI/CD"].map((cat) => (
                <button
                  key={cat}
                  onClick={() => setCategoryFilter(cat)}
                  className={`button ${categoryFilter === cat ? "active" : ""}`}
                  style={{
                    padding: "0.4rem 0.8rem",
                    borderRadius: "6px",
                    border: "1px solid #d1d5db",
                    background: categoryFilter === cat ? "#2563eb" : "#ffffff",
                    color: categoryFilter === cat ? "#ffffff" : "#374151",
                    cursor: "pointer",
                  }}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          <div
            className="catalogGrid"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: "1rem",
            }}
          >
            {filteredApps.map((app) => (
              <article
                key={app.id}
                style={{
                  border: "1px solid #e5e7eb",
                  borderRadius: "8px",
                  padding: "1rem",
                  background: "#ffffff",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <strong style={{ fontSize: "1.1rem" }}>{app.name}</strong>
                    <span
                      style={{
                        padding: "0.2rem 0.5rem",
                        borderRadius: "12px",
                        fontSize: "0.75rem",
                        fontWeight: "600",
                        background: app.status === "Installed" ? "#dcfce7" : "#f3f4f6",
                        color: app.status === "Installed" ? "#166534" : "#4b5563",
                      }}
                    >
                      {app.status}
                    </span>
                  </div>
                  <p style={{ fontSize: "0.85rem", color: "#6b7280", marginBottom: "0.75rem" }}>{app.description}</p>
                  <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap", marginBottom: "1rem" }}>
                    {app.capabilities.map((cap) => (
                      <span
                        key={cap}
                        style={{
                          background: "#f3f4f6",
                          color: "#374151",
                          fontSize: "0.7rem",
                          padding: "0.15rem 0.4rem",
                          borderRadius: "4px",
                        }}
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
                  <button
                    onClick={() => setSelectedApp(app)}
                    style={{
                      flex: 1,
                      padding: "0.4rem 0.6rem",
                      borderRadius: "6px",
                      border: "1px solid #d1d5db",
                      background: "#f9fafb",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                    }}
                  >
                    Inspect
                  </button>
                  <button
                    onClick={() => toggleInstall(app.id)}
                    style={{
                      flex: 1,
                      padding: "0.4rem 0.6rem",
                      borderRadius: "6px",
                      border: "none",
                      background: app.status === "Installed" ? "#ef4444" : "#2563eb",
                      color: "#ffffff",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                      fontWeight: "500",
                    }}
                  >
                    {app.status === "Installed" ? "Uninstall" : "Install"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="surfacePanel">
          <div className="panelTitle">
            <span>Dispatch Intake</span>
            <strong>Task Submission Form</strong>
          </div>
          <form onSubmit={handleSubmitTask} className="assignPanel">
            <label>
              <span>Task Title</span>
              <input
                type="text"
                placeholder="e.g. Implement React marketplace UI"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                required
              />
            </label>

            <label>
              <span>Repository</span>
              <input
                type="text"
                value={form.repo}
                onChange={(e) => setForm({ ...form, repo: e.target.value })}
                required
              />
            </label>

            <label>
              <span>Target Agent</span>
              <select
                value={form.target_agent}
                onChange={(e) => setForm({ ...form, target_agent: e.target.value })}
              >
                {apps.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.category})
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Priority</span>
              <select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
              >
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
                <option value="backlog">Backlog</option>
              </select>
            </label>

            <label>
              <span>Budget Cost</span>
              <input
                type="number"
                min="1"
                value={form.budget_cost}
                onChange={(e) => setForm({ ...form, budget_cost: e.target.value })}
              />
            </label>

            <label>
              <span>Verification Predicate</span>
              <input
                type="text"
                value={form.predicate}
                onChange={(e) => setForm({ ...form, predicate: e.target.value })}
              />
            </label>

            <label>
              <span>Receipt Target</span>
              <input
                type="text"
                value={form.receipt_target}
                onChange={(e) => setForm({ ...form, receipt_target: e.target.value })}
              />
            </label>

            <label>
              <span>Auth Token (Optional)</span>
              <input
                type="password"
                placeholder="Bearer token"
                value={form.token}
                onChange={(e) => setForm({ ...form, token: e.target.value })}  // allow-secret
              />
            </label>

            <button type="submit" disabled={form.loading}>
              {form.loading ? "Submitting..." : "Submit Task Request"}
            </button>

            {form.result && <p className="opsResult">{form.result}</p>}
            {form.error && <p className="opsError">{form.error}</p>}
          </form>
        </div>
      </section>

      {selectedApp && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#ffffff",
              padding: "2rem",
              borderRadius: "10px",
              maxWidth: "500px",
              width: "90%",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2>{selectedApp.name} Integration</h2>
              <button
                onClick={() => setSelectedApp(null)}
                style={{ background: "none", border: "none", fontSize: "1.2rem", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>
            <p><strong>Category:</strong> {selectedApp.category}</p>
            <p><strong>Version:</strong> {selectedApp.version}</p>
            <p><strong>Status:</strong> {selectedApp.status}</p>
            <p style={{ margin: "1rem 0" }}>{selectedApp.description}</p>
            <h4>Capabilities</h4>
            <ul style={{ paddingLeft: "1.2rem", margin: "0.5rem 0 1.5rem 0" }}>
              {selectedApp.capabilities.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <div style={{ display: "flex", gap: "1rem" }}>
              <button
                onClick={() => toggleInstall(selectedApp.id)}
                style={{
                  flex: 1,
                  padding: "0.6rem",
                  borderRadius: "6px",
                  border: "none",
                  background: selectedApp.status === "Installed" ? "#ef4444" : "#2563eb",
                  color: "#ffffff",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                {selectedApp.status === "Installed" ? "Uninstall App" : "Install Integration"}
              </button>
              <button
                onClick={() => setSelectedApp(null)}
                style={{
                  padding: "0.6rem 1.2rem",
                  borderRadius: "6px",
                  border: "1px solid #d1d5db",
                  background: "#ffffff",
                  cursor: "pointer",
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
