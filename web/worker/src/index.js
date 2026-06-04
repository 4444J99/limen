import YAML from "yaml";

const GITHUB_API = "https://api.github.com";
const VERIFY_STATUSES = new Set(["done", "needs_human", "failed", "failed_blocked"]);
let inlineBoardText = null;

function nowIso() {
  return new Date().toISOString();
}

function json(payload, status = 200, env = {}) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...corsHeaders(env),
    },
  });
}

function corsHeaders(env) {
  const origins = (env.LIMEN_CORS_ORIGINS || "*").split(",").map((item) => item.trim()).filter(Boolean);
  return {
    "access-control-allow-origin": origins[0] || "*",
    "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
    "access-control-allow-headers": "authorization,content-type",
  };
}

function error(message, status, env) {
  return json({ detail: message }, status, env);
}

function configuredPersonaTokens(env) {
  const owner = [env.LIMEN_API_TOKEN, env.LIMEN_OWNER_TOKEN].filter(Boolean);
  const client = [env.LIMEN_CLIENT_TOKEN].filter(Boolean);
  return { owner, client };
}

function resolvePersona(request, env, allowPublic = false) {
  const tokens = configuredPersonaTokens(env);
  if (!tokens.owner.length && !tokens.client.length) return "owner";
  const authorization = request.headers.get("authorization") || "";
  if (!authorization) return allowPublic ? "public" : null;
  const [scheme, token] = authorization.split(/\s+/, 2);
  if ((scheme || "").toLowerCase() !== "bearer") return null;
  if (tokens.owner.includes(token)) return "owner";
  if (tokens.client.includes(token)) return "client";
  return null;
}

function requirePersona(request, env, allowed) {
  const persona = resolvePersona(request, env, allowed.includes("public"));
  if (!persona) return { response: error("missing or invalid Authorization header", 401, env) };
  if (!allowed.includes(persona)) {
    return { response: error(`${persona} persona is not sanctioned for this endpoint`, 403, env), persona };
  }
  return { persona };
}

function countBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item) || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function taskEvents(task) {
  return (task.dispatch_log || [])
    .filter((entry) => entry && entry.timestamp && Number.isFinite(Date.parse(entry.timestamp)))
    .map((entry) => ({ ...entry, timestamp_ms: Date.parse(entry.timestamp) }))
    .sort((a, b) => b.timestamp_ms - a.timestamp_ms);
}

function summary(data) {
  const tasks = data.tasks || [];
  const events = tasks.flatMap(taskEvents).sort((a, b) => b.timestamp_ms - a.timestamp_ms);
  const now = Date.now();
  const today = new Date(now).toISOString().slice(0, 10);
  const active = tasks.filter((task) => ["dispatched", "in_progress"].includes(task.status));
  const stale = active.filter((task) => {
    const latest = taskEvents(task)[0];
    return !latest || now - latest.timestamp_ms > 24 * 60 * 60 * 1000;
  });
  const todayEvents = events.filter((event) => new Date(event.timestamp_ms).toISOString().slice(0, 10) === today);
  return {
    generated_at: nowIso(),
    total: tasks.length,
    by_status: countBy(tasks, (task) => task.status),
    by_agent: countBy(tasks, (task) => task.target_agent),
    by_priority: countBy(tasks, (task) => task.priority),
    by_repo: countBy(tasks, (task) => task.repo),
    active_count: active.length,
    stale_count: stale.length,
    stale_task_ids: stale.map((task) => task.id),
    today,
    today_events: todayEvents.length,
    today_jules_dispatches: todayEvents.filter((event) => event.agent === "jules" && event.status === "dispatched").length,
    recent_events: events.slice(0, 40),
  };
}

function publicSummary(data) {
  const raw = summary(data);
  const done = (raw.by_status.done || 0) + (raw.by_status.archived || 0);
  return {
    portal: {
      name: data.portal?.name || "Universal Task Intake",
      description: data.portal?.description || "",
    },
    total: raw.total,
    completed: done,
    completion_rate: Number((done / Math.max(1, raw.total)).toFixed(3)),
    active: (raw.by_status.dispatched || 0) + (raw.by_status.in_progress || 0),
    by_status: raw.by_status,
    generated_at: raw.generated_at,
  };
}

function budget(data) {
  return data.portal?.budget || { daily: 100, unit: "runs", track: { spent: 0, per_agent: {} } };
}

function clientSummary(data) {
  const raw = summary(data);
  const pub = publicSummary(data);
  const staleIds = new Set(raw.stale_task_ids);
  const lifecycle = { recover: 0, verify: 0, assign: 0, archive: 0, archived: 0 };
  for (const task of data.tasks || []) {
    const phase = taskLifecycle(task, staleIds).phase;
    lifecycle[phase] = (lifecycle[phase] || 0) + 1;
  }
  return {
    ...pub,
    stale_count: raw.stale_count,
    lifecycle,
    budget: budget(data),
    top_repos: Object.entries(raw.by_repo).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([repo, count]) => ({ repo, count })),
    active_tasks: (data.tasks || [])
      .filter((task) => ["dispatched", "in_progress"].includes(task.status) || raw.stale_task_ids.includes(task.id))
      .slice(0, 25)
      .map((task) => {
        const lifecycle = taskLifecycle(task, staleIds);
        return {
          id: task.id,
          title: task.title,
          repo: task.repo || "",
          target_agent: task.target_agent || "unknown",
          status: task.status || "unknown",
          priority: task.priority || "medium",
          stale: raw.stale_task_ids.includes(task.id),
          phase: lifecycle.phase,
          next_gate: lifecycle.next_gate,
        };
      }),
  };
}

function releaseStaleCandidates(data, hours = 24) {
  const cutoff = Date.now() - Number(hours) * 60 * 60 * 1000;
  return (data.tasks || [])
    .filter((task) => ["dispatched", "in_progress"].includes(task.status))
    .filter((task) => {
      const latest = taskEvents(task)[0];
      return !latest || latest.timestamp_ms < cutoff;
    })
    .map((task) => ({
      id: task.id || "unknown",
      title: task.title || "",
      agent: task.target_agent || "unknown",
      status: task.status || "unknown",
      latest: taskEvents(task)[0]?.timestamp || null,
    }));
}

function taskLifecycle(task, staleIds) {
  const latest = taskEvents(task)[0];
  const urls = task.urls || [];
  const stale = staleIds.has(task.id);
  const has_pr = urls.some((url) => url.includes("/pull/"));
  const has_issue = urls.some((url) => url.includes("/issues/"));
  const status = task.status || "unknown";
  let phase = "assign";
  if (status === "archived") phase = "archived";
  else if (status === "done") phase = "archive";
  else if (stale || ["failed", "failed_blocked", "needs_human"].includes(status)) phase = "recover";
  else if (has_pr || ["dispatched", "in_progress"].includes(status)) phase = "verify";
  const gates = {
    archived: "suppressed from active steering",
    archive: "archive evidence and suppress from active steering",
    recover: "release stale claim or reassign with failure note",
    verify: "verify PR/runtime evidence, then close or return",
    assign: "assign to agent with budget and acceptance gate",
  };
  return {
    id: task.id,
    title: task.title,
    repo: task.repo || "",
    status,
    priority: task.priority || "medium",
    assignee: task.target_agent || "unassigned",
    phase,
    next_gate: gates[phase],
    stale,
    has_issue,
    has_pr,
    latest_event_at: latest?.timestamp || task.updated || task.created || null,
  };
}

function qaStatus(data, agent = "jules") {
  const staleIds = new Set(releaseStaleCandidates(data, 24).map((task) => task.id));
  const items = (data.tasks || []).map((task) => taskLifecycle(task, staleIds));
  const phaseOrder = { recover: 0, verify: 1, assign: 2, archive: 3, archived: 4 };
  const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3, backlog: 4 };
  const steering = items
    .filter((item) => !["archive", "archived"].includes(item.phase))
    .sort((a, b) => (phaseOrder[a.phase] ?? 99) - (phaseOrder[b.phase] ?? 99)
      || (priorityOrder[a.priority] ?? 99) - (priorityOrder[b.priority] ?? 99)
      || String(a.id).localeCompare(String(b.id)));
  const qa = items.filter((item) => item.phase === "verify");
  const recover = items.filter((item) => item.phase === "recover");
  const assign = items.filter((item) => item.phase === "assign");
  const archive = items.filter((item) => item.phase === "archive");
  const archived = items.filter((item) => item.phase === "archived");
  return {
    status: recover.length ? "degraded" : "ok",
    surface: "qa",
    generated_at: nowIso(),
    lifecycle: { total: items.length, assign: assign.length, verify: qa.length, recover: recover.length, archive_ready: archive.length, archived: archived.length },
    steering: {
      principle: "Every visible item is a portal into one task lifecycle; closed work is archived out of active steering.",
      next_batch: steering.slice(0, 24),
      qa_queue: qa.slice(0, 24),
      recovery_queue: recover.slice(0, 24),
      assignment_queue: assign.slice(0, 24),
      archive_queue: archive.slice(0, 24),
    },
    mechanisms: [
      { id: "release-stale", label: "Release stale claims", agent, command: "POST /api/release-stale?hours=24&dry_run=false", mode: "human-approved apply", count: recover.length },
      { id: "qa-verify", label: "Verify PR and runtime evidence", agent: "qa", command: "POST /api/tasks/{task_id}/verify", mode: "human-approved evidence gate", count: qa.length },
      { id: "assign-next", label: "Assign or reassign next task", agent: "steering", command: "POST /api/tasks/{task_id}/assign", mode: "human-approved assignment", count: assign.length },
      { id: "archive-done", label: "Archive closed evidence", agent: "system", command: "POST /api/tasks/{task_id}/archive", mode: "human-approved archive", count: archive.length },
    ],
  };
}

function surfaceManifest(data, env, persona = "owner") {
  const raw = summary(data);
  const staleCount = releaseStaleCandidates(data, 24).length;
  const manifest = {
    status: "ok",
    persona,
    generated_at: nowIso(),
    source: {
      type: "cloudflare-worker",
      task_file: env.LIMEN_GITHUB_PATH || "tasks.yaml",
      api_runtime: "connected",
      api_url_configured: true,
      blocker: null,
      storage: storageStatus(env),
    },
    surfaces: [
      { id: "internal", title: "Internal operations", route: "/", contract: "/api/status", persona: "owner", sanctioned_personas: ["owner"], disclosure: "full task board, dispatch controls, PR health, and operational logs" },
      { id: "client", title: "Client status", route: "/client", contract: "/api/client-status", persona: "client", sanctioned_personas: ["owner", "client"], disclosure: "redacted active task rows, delivery metrics, budget, and repo distribution" },
      { id: "public", title: "Public status", route: "/public", contract: "/api/public-status", persona: "public", sanctioned_personas: ["owner", "client", "public"], disclosure: "aggregate task health only" },
      { id: "qa", title: "QA and steering", route: "/qa", contract: "/api/qa-status", persona: "owner", sanctioned_personas: ["owner"], disclosure: "lifecycle gates, assignment queues, verification queues, and archive suppression" },
    ],
    contracts: {
      internal: { path: "/api/status", total: raw.total, stale_count: staleCount },
      client: { path: "/api/client-status", total: raw.total, stale_count: staleCount, max_active_tasks: 25, includes_dispatch_logs: false },
      public: { path: "/api/public-status", total: raw.total, includes_tasks: false, includes_dispatch_logs: false },
      qa: { path: "/api/qa-status", total: raw.total, stale_count: staleCount, verify_endpoint: "/api/tasks/{task_id}/verify", assignment_endpoint: "/api/tasks/{task_id}/assign", archive_endpoint: "/api/tasks/{task_id}/archive", includes_dispatch_logs: false, includes_task_context: false, includes_task_urls: false },
      readiness: { path: "/api/readiness", includes_dispatch_logs: false },
    },
  };
  manifest.surfaces = manifest.surfaces.filter((surface) => surface.sanctioned_personas.includes(persona));
  const sanctioned = new Set(manifest.surfaces.map((surface) => surface.id));
  manifest.contracts = Object.fromEntries(Object.entries(manifest.contracts).filter(([key]) => sanctioned.has(key) || (key === "readiness" && persona === "owner")));
  return manifest;
}

function readiness(data, agent = "jules") {
  const raw = summary(data);
  const b = budget(data);
  const limit = b.per_agent?.[agent] || b.daily || 100;
  const spent = b.track?.per_agent?.[agent] || 0;
  const remaining = Math.max(0, Math.min((b.daily || 100) - (b.track?.spent || 0), limit - spent));
  const open = (data.tasks || []).filter((task) => task.status === "open" && [agent, "any"].includes(task.target_agent)).length;
  const checks = [
    { id: "api_runtime", status: "pass", detail: "cloudflare worker runtime attached" },
    { id: "github_storage", status: "pass", detail: "GitHub Contents storage" },
    { id: "stale_claims", status: raw.stale_count ? "warn" : "pass", detail: `${raw.stale_count} stale active tasks` },
    { id: "open_queue", status: open ? "pass" : "warn", detail: `${open} open ${agent} tasks` },
    { id: "budget", status: remaining > 0 ? "pass" : "fail", detail: `${remaining}/${limit} ${agent} runs remaining` },
  ];
  const nextActions = [];
  if (raw.stale_count) nextActions.push("POST /api/release-stale?hours=24&dry_run=false");
  if (open && remaining > 0) nextActions.push(`POST /api/dispatch live=false limit=${Math.min(open, remaining)}`);
  if (remaining <= 0) nextActions.push(`Wait for ${agent} budget reset or lower dispatch volume`);
  return {
    status: checks.some((check) => check.status === "fail") ? "blocked" : checks.some((check) => check.status === "warn") ? "degraded" : "ready",
    generated_at: nowIso(),
    agent,
    counts: { total: raw.total, active: raw.active_count, stale: raw.stale_count, open, [`open_${agent}`]: open },
    budget: { daily: b.daily || 100, agent_limit: limit, agent_spent: spent, remaining },
    checks,
    next_actions: nextActions.length ? nextActions : ["No immediate action required"],
  };
}

function storageStatus(env) {
  if (inlineBoardSource(env)) {
    return { mode: "inline", configured: true };
  }
  return { mode: "github", repo: env.LIMEN_GITHUB_REPO, branch: env.LIMEN_GITHUB_BRANCH || "main", path: env.LIMEN_GITHUB_PATH || "tasks.yaml", configured: Boolean(env.LIMEN_GITHUB_REPO && env.LIMEN_GITHUB_TOKEN) };
}

function githubUrl(env) {
  const repo = env.LIMEN_GITHUB_REPO;
  const path = encodeURIComponent(env.LIMEN_GITHUB_PATH || "tasks.yaml").replaceAll("%2F", "/");
  return `${GITHUB_API}/repos/${repo}/contents/${path}`;
}

async function githubRequest(env, method, url, payload = null) {
  if (!env.LIMEN_GITHUB_TOKEN) throw new Error("LIMEN_GITHUB_TOKEN is required");
  const res = await fetch(url, {
    method,
    headers: {
      authorization: `Bearer ${env.LIMEN_GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "limen-runtime-worker",
      "x-github-api-version": "2022-11-28",
      ...(payload ? { "content-type": "application/json" } : {}),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`GitHub storage request failed (${res.status}): ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : {};
}

function decodeBase64(value) {
  return decodeURIComponent(Array.prototype.map.call(atob(value.replace(/\n/g, "")), (char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`).join(""));
}

function encodeBase64(value) {
  return btoa(unescape(encodeURIComponent(value)));
}

async function loadBoard(env) {
  const inline = inlineBoardSource(env);
  if (inline) {
    inlineBoardText ??= inline;
    return { data: YAML.parse(inlineBoardText) || { portal: {}, tasks: [] }, sha: null };
  }
  const branch = env.LIMEN_GITHUB_BRANCH || "main";
  const raw = await githubRequest(env, "GET", `${githubUrl(env)}?ref=${encodeURIComponent(branch)}`);
  return { data: YAML.parse(decodeBase64(raw.content || "")) || { portal: {}, tasks: [] }, sha: raw.sha };
}

async function saveBoard(env, data, sha) {
  if (inlineBoardSource(env)) {
    inlineBoardText = YAML.stringify(data);
    return;
  }
  const branch = env.LIMEN_GITHUB_BRANCH || "main";
  await githubRequest(env, "PUT", githubUrl(env), {
    message: env.LIMEN_GITHUB_COMMIT_MESSAGE || "Update Limen task board",
    content: encodeBase64(YAML.stringify(data)),
    branch,
    ...(sha ? { sha } : {}),
  });
}

function inlineBoardSource(env) {
  if (env.LIMEN_INLINE_TASKS_YAML) return env.LIMEN_INLINE_TASKS_YAML;
  if (env.LIMEN_INLINE_TASKS_YAML_B64) return decodeBase64(env.LIMEN_INLINE_TASKS_YAML_B64);
  return "";
}

function findTask(data, taskId) {
  const task = (data.tasks || []).find((item) => item.id === taskId);
  if (!task) throw new Response(JSON.stringify({ detail: `task ${taskId} not found` }), { status: 404 });
  return task;
}

function dispatchCandidates(data, agent = "jules", taskId = null) {
  const priority = { critical: 0, high: 1, medium: 2, low: 3, backlog: 4 };
  return (data.tasks || [])
    .filter((task) => task.status === "open")
    .filter((task) => !taskId || task.id === taskId)
    .filter((task) => !agent || [agent, "any"].includes(task.target_agent))
    .sort((a, b) => (priority[a.priority] ?? 99) - (priority[b.priority] ?? 99));
}

function appendLog(task, agent, sessionId, status, output = "") {
  task.dispatch_log = task.dispatch_log || [];
  task.dispatch_log.push({ timestamp: nowIso(), agent, session_id: sessionId, status, output });
  task.updated = nowIso();
}

async function withBoard(env, fn) {
  const doc = await loadBoard(env);
  return fn(doc.data, doc.sha);
}

async function route(request, env) {
  if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders(env) });
  const url = new URL(request.url);
  const path = url.pathname;

  if (path === "/health") return json({ status: "ok", time: nowIso(), storage: storageStatus(env) }, 200, env);
  if (path === "/api/public-status" && request.method === "GET") return withBoard(env, (data) => json({ status: "ok", surface: "public", summary: publicSummary(data) }, 200, env));
  if (path === "/api/surface-manifest" && request.method === "GET") {
    const persona = resolvePersona(request, env, true);
    if (!persona) return error("missing or invalid Authorization header", 401, env);
    return withBoard(env, (data) => json(surfaceManifest(data, env, persona), 200, env));
  }

  if (path === "/api/client-status" && request.method === "GET") {
    const auth = requirePersona(request, env, ["owner", "client"]);
    if (auth.response) return auth.response;
    return withBoard(env, (data) => json({ status: "ok", surface: "client", summary: clientSummary(data), storage: storageStatus(env) }, 200, env));
  }

  for (const ownerPath of ["/api/status", "/api/qa-status", "/api/readiness", "/api/tasks"]) {
    if (path === ownerPath) {
      const auth = requirePersona(request, env, ["owner"]);
      if (auth.response) return auth.response;
      break;
    }
  }

  if (path === "/api/status" && request.method === "GET") return withBoard(env, (data) => json({ status: "ok", surface: "internal", portal: data.portal || {}, summary: summary(data), storage: storageStatus(env) }, 200, env));
  if (path === "/api/qa-status" && request.method === "GET") return withBoard(env, (data) => json(qaStatus(data, url.searchParams.get("agent") || "jules"), 200, env));
  if (path === "/api/readiness" && request.method === "GET") return withBoard(env, (data) => json(readiness(data, url.searchParams.get("agent") || "jules"), 200, env));
  if (path === "/api/tasks" && request.method === "GET") return withBoard(env, (data) => json({ tasks: data.tasks || [], count: (data.tasks || []).length }, 200, env));

  if (path === "/api/release-stale" && request.method === "POST") {
    const auth = requirePersona(request, env, ["owner"]);
    if (auth.response) return auth.response;
    const hours = Number(url.searchParams.get("hours") || "24");
    const dryRun = (url.searchParams.get("dry_run") || "true") !== "false";
    const doc = await loadBoard(env);
    const candidates = releaseStaleCandidates(doc.data, hours);
    if (!dryRun) {
      const ids = new Set(candidates.map((task) => task.id));
      for (const task of doc.data.tasks || []) {
        if (ids.has(task.id)) {
          task.status = "open";
          appendLog(task, "api", "release-stale", "open", `Released stale claim older than ${hours} hours`);
        }
      }
      await saveBoard(env, doc.data, doc.sha);
    }
    return json({ status: dryRun ? "dry_run" : "released", count: candidates.length, candidates, released: dryRun ? [] : candidates.map((task) => task.id) }, 200, env);
  }

  if (path === "/api/dispatch" && request.method === "POST") {
    const auth = requirePersona(request, env, ["owner"]);
    if (auth.response) return auth.response;
    const body = await request.json().catch(() => ({}));
    const doc = await loadBoard(env);
    const candidates = dispatchCandidates(doc.data, body.agent || "jules", body.task_id || null).slice(0, Math.max(1, Math.min(Number(body.limit || 1), 100)));
    if (body.live) return error("live dispatch is not implemented by the Cloudflare adapter", 501, env);
    return json({ status: "dry_run", count: candidates.length, candidates, tasks: candidates, live: false, agent: body.agent || "jules" }, 200, env);
  }

  const taskMatch = path.match(/^\/api\/tasks\/([^/]+)(?:\/(verify|assign|archive))?$/);
  if (taskMatch) {
    const auth = requirePersona(request, env, ["owner"]);
    if (auth.response) return auth.response;
    const taskId = decodeURIComponent(taskMatch[1]);
    const action = taskMatch[2];
    if (!action && request.method === "GET") return withBoard(env, (data) => json(findTask(data, taskId), 200, env));
    if (request.method !== "POST") return error("method not allowed", 405, env);
    const body = await request.json().catch(() => ({}));
    const doc = await loadBoard(env);
    const task = findTask(doc.data, taskId);
    if (action === "verify") {
      if (!VERIFY_STATUSES.has(body.status || "done")) return error("invalid verification status", 422, env);
      if (!["dispatched", "in_progress", "needs_human", "failed", "failed_blocked", "done"].includes(task.status)) return error("only active, attention, or done tasks can be verified", 409, env);
      task.status = body.status || "done";
      appendLog(task, "qa", body.session_id || "qa-verify", task.status, body.note || `QA verified task as ${task.status}`);
      await saveBoard(env, doc.data, doc.sha);
      return json({ status: "verified", task, verified_status: task.status }, 200, env);
    }
    if (action === "assign") {
      const before = { target_agent: task.target_agent, priority: task.priority, budget_cost: task.budget_cost, status: task.status };
      if (body.target_agent !== undefined) task.target_agent = body.target_agent;
      if (body.priority !== undefined) task.priority = body.priority;
      if (body.budget_cost !== undefined) task.budget_cost = body.budget_cost;
      if (body.status !== undefined) task.status = body.status;
      const after = { target_agent: task.target_agent, priority: task.priority, budget_cost: task.budget_cost, status: task.status };
      const changed = Object.keys(after).filter((key) => before[key] !== after[key]);
      appendLog(task, "api", body.session_id || "assignment", "assigned", body.note || `Assigned via steering controls: ${changed.join(", ") || "no field changes"}`);
      await saveBoard(env, doc.data, doc.sha);
      return json({ status: "assigned", task, changed }, 200, env);
    }
    if (action === "archive") {
      if (!["done", "archived"].includes(task.status)) return error("only done tasks can be archived", 409, env);
      if (task.status !== "archived") {
        task.status = "archived";
        appendLog(task, "api", body.session_id || "archive", "archived", body.note || "Archived from QA steering");
        await saveBoard(env, doc.data, doc.sha);
      }
      return json({ status: "archived", task }, 200, env);
    }
  }

  return error("not found", 404, env);
}

export default {
  async fetch(request, env) {
    try {
      return await route(request, env);
    } catch (err) {
      if (err instanceof Response) return err;
      return error(err instanceof Error ? err.message : "runtime error", 500, env);
    }
  },
};
