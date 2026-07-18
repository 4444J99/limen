import YAML from "yaml";

const GITHUB_API = "https://api.github.com";
const VERIFY_STATUSES = new Set(["done", "needs_human", "failed", "failed_blocked"]);
const VALID_STATUSES = new Set(["open", "dispatched", "in_progress", "done", "failed", "failed_blocked", "needs_human", "archived"]);
const VALID_PRIORITIES = new Set(["critical", "high", "medium", "low", "backlog"]);
const VALID_AGENTS = new Set(["jules", "claude", "gemini", "opencode", "codex", "copilot", "agy", "warp", "oz", "github_actions", "any"]);
const VALID_DISPATCH_AGENTS = new Set([...VALID_AGENTS].filter((agent) => agent !== "any"));
const TASK_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._/-]*$/;
const SAFE_TEXT_RE = /^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*$/;
const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const PLACEHOLDER_RE = /<[^>]+>|\b(?:tbd|todo|fixme|replace[-_ ]me)\b/i;
const ACTIVE_STATUSES = new Set(["open", "dispatched", "in_progress"]);
const EXECUTABLES = new Set([
  "[", "bash", "bundle", "cargo", "curl", "gh", "git", "go", "just", "make", "node", "nox", "npm",
  "pnpm", "py.test", "pytest", "python", "python3", "ruby", "sh", "test", "tox", "uv", "yarn", "zsh",
]);
const TABULARIUS_TICKET_ACTION = "Submit a TABVLARIVS ticket and let the keeper publish the board projection PR";
let inlineBoardText = null;
// Parsed-board cache: keyed by sha so re-parse only happens when content changes.
let boardCache = null; // { sha: string, data: object }

class IntakeContractError extends Error {}

class BoardMutationDeferred extends Error {
  constructor(target) {
    super("GitHub-backed board mutations are keeper-owned and cannot be written by the Worker");
    this.code = "board_mutation_deferred";
    this.retryable = true;
    this.owner = "tabularius";
    this.target = target;
  }
}

function taskText(task) {
  return [task.title, task.description, task.context].filter(Boolean).map(String).join("\n");
}

function boundednessFinding(task) {
  const text = taskText(task);
  const numbered = new Set([...text.matchAll(/(?:^|\s)\((\d+)\)\s/g)].map((match) => Number(match[1])));
  if (numbered.size >= 4) return `multi-goal bundle (${numbered.size} numbered objectives)`;
  const sequenced = text.match(/;\s*then\b|\band\s+then\s+also\b/gi) || [];
  if (sequenced.length >= 4) return `multi-goal bundle (${sequenced.length + 1} sequenced objectives)`;
  return null;
}

function shellWords(command) {
  return command.match(/(?:[^\s"'\\]+|"(?:\\.|[^"])*"|'[^']*')+/g) || [];
}

function isExecutablePredicate(value) {
  if (typeof value !== "string") return false;
  const command = value.trim();
  if (!command || /[\r\n]/.test(command) || PLACEHOLDER_RE.test(command)) return false;
  const words = shellWords(command);
  let index = 0;
  while (index < words.length) {
    const word = words[index];
    if (["command", "env", "sudo"].includes(word) || word.startsWith("-") || (/^[A-Za-z_][A-Za-z0-9_]*=/.test(word))) {
      index += 1;
      continue;
    }
    break;
  }
  if (index >= words.length) return false;
  const first = words[index].replace(/^['"]|['"]$/g, "");
  return EXECUTABLES.has(first) || first.includes("/") || first.endsWith(".py") || first.endsWith(".sh");
}

function isDurableReceiptTarget(value) {
  if (typeof value !== "string") return false;
  const target = value.trim();
  if (!target || PLACEHOLDER_RE.test(target)) return false;
  if (/^github:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+:(?:pull-request|issue):[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(target)) return true;
  const gitTarget = target.match(/^git:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+:([^\s#]+)(?:#[^\s]+)?$/);
  if (gitTarget) {
    const path = gitTarget[1];
    return !path.startsWith("/") && path.split("/").every((part) => !["", ".", "..", ".git"].includes(part));
  }
  try {
    const url = new URL(target);
    if (url.protocol !== "https:" || url.hostname.toLowerCase() !== "github.com") return false;
    const parts = url.pathname.split("/").filter(Boolean);
    return (parts.length >= 4 && ["issues", "pull", "commit", "blob", "tree"].includes(parts[2]))
      || (parts.length >= 5 && parts[2] === "actions" && ["runs", "workflows"].includes(parts[3]));
  } catch {
    return false;
  }
}

function validateIntakeContract(task, { isNew = false } = {}) {
  const required = isNew || ACTIVE_STATUSES.has(String(task.status || "open"));
  const predicate = String(task.predicate || "").trim();
  const receiptTarget = String(task.receipt_target || "").trim();
  const partial = Boolean(predicate || receiptTarget);
  const errors = [];
  if ((required || partial) && !isExecutablePredicate(predicate)) errors.push("predicate must be one executable command with no placeholders");
  if ((required || partial) && !isDurableReceiptTarget(receiptTarget)) errors.push("receipt_target must name a durable GitHub receipt or repository-owned path");
  const bundle = boundednessFinding(task);
  if (required && bundle) errors.push(bundle);
  if (errors.length) throw new IntakeContractError(errors.join("; "));
  return predicate && receiptTarget ? { predicate, receipt_target: receiptTarget } : null;
}

function githubIssueContract(repo, number) {
  if (!REPO_RE.test(repo) || !/^\d+$/.test(String(number))) throw new IntakeContractError("cannot build issue contract without exact owner/repo and issue number");
  return {
    predicate: `test "$(gh issue view ${number} --repo ${repo} --json state --jq .state)" = CLOSED`,
    receipt_target: `https://github.com/${repo}/issues/${number}`,
  };
}

function githubPrContract(repo, taskId) {
  if (!REPO_RE.test(repo) || !TASK_ID_RE.test(taskId)) throw new IntakeContractError("cannot build PR contract without exact owner/repo and task id");
  return {
    predicate: `test "$(gh pr list --repo ${repo} --state merged --search '${taskId} in:body' --json number --jq length)" -gt 0`,
    receipt_target: `github:${repo}:pull-request:${taskId}`,
  };
}

function githubExistingPrContract(repo, number) {
  if (!REPO_RE.test(repo) || !/^\d+$/.test(String(number))) throw new IntakeContractError("cannot build existing-PR contract without exact owner/repo and PR number");
  return {
    predicate: `test "$(gh pr view ${number} --repo ${repo} --json state --jq .state)" = MERGED`,
    receipt_target: `https://github.com/${repo}/pull/${number}`,
  };
}

function githubContractFromUrl(value) {
  if (typeof value !== "string") return null;
  const match = value.match(/^https:\/\/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)\/(issues|pull)\/(\d+)/);
  if (!match) return null;
  return match[2] === "issues" ? githubIssueContract(match[1], match[3]) : githubExistingPrContract(match[1], match[3]);
}

function normalizeSelectedLegacyTask(task) {
  try {
    const existing = validateIntakeContract(task);
    if (existing) return existing;
  } catch {}

  const text = taskText(task);
  const predicateLine = text.match(/^\s*predicate\s*:\s*([^\r\n]+?)\s*$/im);
  const receiptLine = text.match(/^\s*receipt\s+target\s*:\s*(\S+)\s*$/im);
  let predicate = predicateLine ? predicateLine[1].trim() : "";
  let receiptTarget = receiptLine ? receiptLine[1].trim() : "";
  const urlContract = (task.urls || []).map(githubContractFromUrl).find(Boolean);
  if (urlContract) {
    if (!isExecutablePredicate(predicate)) predicate = urlContract.predicate;
    if (!isDurableReceiptTarget(receiptTarget)) receiptTarget = urlContract.receipt_target;
  }
  if (!isExecutablePredicate(predicate) || !isDurableReceiptTarget(receiptTarget)) {
    const fallback = githubPrContract(String(task.repo || "").trim(), String(task.id || "").trim());
    if (!isExecutablePredicate(predicate)) predicate = fallback.predicate;
    if (!isDurableReceiptTarget(receiptTarget)) receiptTarget = fallback.receipt_target;
  }
  task.predicate = predicate;
  task.receipt_target = receiptTarget;
  return validateIntakeContract(task);
}

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

function safeParseBody(body, allowedFields = []) {
  if (typeof body !== "object" || body === null || Array.isArray(body)) return {};
  const cleaned = {};
  for (const field of allowedFields) {
    if (field in body) cleaned[field] = body[field];
  }
  return cleaned;
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

function validationError(message, env) {
  return { response: error(message, 422, env) };
}

function validateTaskId(value, env) {
  if (typeof value !== "string" || value.length < 1 || value.length > 128 || !TASK_ID_RE.test(value)) {
    return validationError("invalid task_id format", env);
  }
  return { value };
}

function validateEnum(value, allowed, field, env) {
  if (typeof value !== "string" || !allowed.has(value)) {
    return validationError(`${field} must be one of ${[...allowed].sort().join(", ")}`, env);
  }
  return { value };
}

function validateText(value, field, env, { defaultValue = "", max = 2000 } = {}) {
  const actual = value === undefined || value === null ? defaultValue : value;
  if (typeof actual !== "string" || actual.length > max || !SAFE_TEXT_RE.test(actual)) {
    return validationError(`${field} must be a string up to ${max} characters without control characters`, env);
  }
  return { value: actual };
}

function validateInteger(value, field, env, { defaultValue = 1, min = 1, max = 100 } = {}) {
  const actual = value === undefined || value === null ? defaultValue : Number(value);
  if (typeof value === "boolean" || !Number.isInteger(actual) || actual < min || actual > max) {
    return validationError(`${field} must be an integer between ${min} and ${max}`, env);
  }
  return { value: actual };
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

function parseDateOnly(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return null;
  return parsed.toISOString().slice(0, 10);
}

function deriveThroughput(data, events, now = new Date()) {
  const tasks = data.tasks || [];
  const currentDate = now.toISOString().slice(0, 10);
  const createdDates = tasks.map((task) => parseDateOnly(task.created)).filter(Boolean).sort();
  const firstCreated = createdDates[0] || currentDate;
  const firstCreatedMs = Date.parse(`${firstCreated}T00:00:00.000Z`);
  const currentDateMs = Date.parse(`${currentDate}T00:00:00.000Z`);
  const ageDays = Math.max(1, Math.floor((currentDateMs - firstCreatedMs) / 86400000) + 1);
  const dailyCapacity = Number(data.portal?.budget?.daily || 100);
  const byStatus = countBy(tasks, (task) => task.status);
  const byEventStatus = countBy(events, (event) => event.status);
  const byEventAgent = countBy(events, (event) => event.agent);
  const byEventDate = countBy(events, (event) => new Date(event.timestamp_ms).toISOString().slice(0, 10));
  const done = (byStatus.done || 0) + (byStatus.archived || 0);
  const recordedStarts = (byEventStatus.dispatched || 0) + (byEventStatus.in_progress || 0);
  const recordedFinishes = (byEventStatus.done || 0) + (byEventStatus.failed || 0) + (byEventStatus.failed_blocked || 0) + (byEventStatus.archived || 0);
  const expectedCapacityRuns = dailyCapacity * ageDays;
  return {
    first_created: firstCreated,
    current_date: currentDate,
    age_days: ageDays,
    daily_capacity: dailyCapacity,
    expected_capacity_runs: expectedCapacityRuns,
    task_burndown_target_per_day: tasks.length ? Math.ceil(tasks.length / ageDays) : 0,
    recorded_events: events.length,
    recorded_starts: recordedStarts,
    recorded_finishes: recordedFinishes,
    done,
    not_done: tasks.length - done,
    unrecorded_capacity_runs: Math.max(0, expectedCapacityRuns - recordedStarts),
    by_event_status: byEventStatus,
    by_event_agent: byEventAgent,
    by_event_date: byEventDate,
  };
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
    throughput: deriveThroughput(data, events, new Date(now)),
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
    throughput: raw.throughput,
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

function readiness(data, env, agent = "jules") {
  const raw = summary(data);
  const b = budget(data);
  const storage = storageStatus(env);
  const storageWritable = storage.writable === true;
  const limit = b.per_agent?.[agent] || b.daily || 100;
  const spent = b.track?.per_agent?.[agent] || 0;
  const remaining = Math.max(0, Math.min((b.daily || 100) - (b.track?.spent || 0), limit - spent));
  const open = (data.tasks || []).filter((task) => task.status === "open" && [agent, "any"].includes(task.target_agent)).length;
  const checks = [
    { id: "api_runtime", status: "pass", detail: "cloudflare worker runtime attached" },
    {
      id: "storage",
      status: storageWritable ? "pass" : "warn",
      detail: storageWritable
        ? `${storage.mode} board storage is writable`
        : "read-only GitHub projection; mutations defer to TABVLARIVS",
    },
    { id: "stale_claims", status: raw.stale_count ? "warn" : "pass", detail: `${raw.stale_count} stale active tasks` },
    { id: "open_queue", status: open ? "pass" : "warn", detail: `${open} open ${agent} tasks` },
    { id: "budget", status: remaining > 0 ? "pass" : "fail", detail: `${remaining}/${limit} ${agent} runs remaining` },
  ];
  const nextActions = [];
  if (!storageWritable) nextActions.push(TABULARIUS_TICKET_ACTION);
  else if (raw.stale_count) nextActions.push("POST /api/release-stale?hours=24&dry_run=false");
  if (open && remaining > 0) nextActions.push(`POST /api/dispatch live=false limit=${Math.min(open, remaining)}`);
  if (remaining <= 0) nextActions.push(`Wait for ${agent} budget reset or lower dispatch volume`);
  return {
    status: checks.some((check) => check.status === "fail") ? "blocked" : checks.some((check) => check.status === "warn") ? "degraded" : "ready",
    generated_at: nowIso(),
    agent,
    counts: { total: raw.total, active: raw.active_count, stale: raw.stale_count, open, [`open_${agent}`]: open },
    budget: { daily: b.daily || 100, agent_limit: limit, agent_spent: spent, remaining },
    checks,
    mutation: storageWritable
      ? { status: "available", owner: storage.mutation_owner }
      : {
          status: "deferred",
          code: "board_mutation_deferred",
          owner: "tabularius",
          route: "tabularius_ticket",
          next_action: TABULARIUS_TICKET_ACTION,
        },
    next_actions: nextActions.length ? nextActions : ["No immediate action required"],
  };
}

function storageStatus(env) {
  if (inlineBoardSource(env)) {
    return {
      mode: "inline",
      access: "read_write",
      configured: true,
      writable: true,
      mutation_owner: "worker_inline",
    };
  }
  return {
    mode: "github",
    access: "read_only",
    writable: false,
    mutation_owner: "tabularius",
    mutation_route: "tabularius_ticket",
    next_action: TABULARIUS_TICKET_ACTION,
    repo: env.LIMEN_GITHUB_REPO,
    branch: env.LIMEN_GITHUB_BRANCH || "main",
    path: env.LIMEN_GITHUB_PATH || "tasks.yaml",
    configured: Boolean(env.LIMEN_GITHUB_REPO && env.LIMEN_GITHUB_TOKEN),
  };
}

function githubUrl(env) {
  const repo = env.LIMEN_GITHUB_REPO;
  const path = encodeURIComponent(env.LIMEN_GITHUB_PATH || "tasks.yaml").replaceAll("%2F", "/");
  return `${GITHUB_API}/repos/${repo}/contents/${path}`;
}

async function githubRequest(env, method, url, payload = null, { raw = false } = {}) {
  if (!env.LIMEN_GITHUB_TOKEN) throw new Error("LIMEN_GITHUB_TOKEN is required");
  const res = await fetch(url, {
    method,
    headers: {
      authorization: `Bearer ${env.LIMEN_GITHUB_TOKEN}`,
      // Use raw media type for GET requests when caller asks: returns file bytes directly,
      // which is the only correct path for files >1 MB (the JSON API returns empty content).
      accept: raw ? "application/vnd.github.raw+json" : "application/vnd.github+json",
      "user-agent": "limen-runtime-worker",
      "x-github-api-version": "2022-11-28",
      ...(payload ? { "content-type": "application/json" } : {}),
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`GitHub storage request failed (${res.status}): ${text.slice(0, 300)}`);
  if (raw) return text; // caller gets raw text directly
  return text ? JSON.parse(text) : {};
}

function decodeBase64(value) {
  // Use Uint8Array + TextDecoder for O(n) instead of char-by-char %XX encoding.
  const bytes = Uint8Array.from(atob(value.replace(/\n/g, "")), (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

async function loadBoard(env) {
  const inline = inlineBoardSource(env);
  if (inline) {
    inlineBoardText ??= inline;
    return { data: YAML.parse(inlineBoardText) || { portal: {}, tasks: [] }, sha: null };
  }
  const branch = env.LIMEN_GITHUB_BRANCH || "main";
  const baseUrl = `${githubUrl(env)}?ref=${encodeURIComponent(branch)}`;

  // First fetch metadata (JSON) to get the sha for cache keying.
  const meta = await githubRequest(env, "GET", baseUrl);
  const sha = meta.sha || null;

  // Return cached parse if sha matches — avoids re-fetching and re-parsing the 5 MB YAML.
  if (boardCache && sha && boardCache.sha === sha) {
    return { data: boardCache.data, sha };
  }

  let yamlText;
  if (meta.content) {
    // Small file: JSON API returned base64 content inline (≤1 MB).
    yamlText = decodeBase64(meta.content);
  } else {
    // Large file (>1 MB): JSON API returns empty content; fetch raw bytes directly.
    yamlText = await githubRequest(env, "GET", baseUrl, null, { raw: true });
  }

  const data = YAML.parse(yamlText) || { portal: {}, tasks: [] };
  // Update module-level cache; also try the Worker Cache API when available.
  boardCache = { sha, data };
  return { data, sha };
}

async function saveBoard(env, data, sha) {
  requireMutableBoard(env);
  inlineBoardText = YAML.stringify(data);
  void sha;
}

function inlineBoardSource(env) {
  if (env.LIMEN_INLINE_TASKS_YAML) return env.LIMEN_INLINE_TASKS_YAML;
  if (env.LIMEN_INLINE_TASKS_YAML_B64) return decodeBase64(env.LIMEN_INLINE_TASKS_YAML_B64);
  return "";
}

function requireMutableBoard(env) {
  if (!inlineBoardSource(env)) throw new BoardMutationDeferred(storageStatus(env));
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
  if (path === "/api/qa-status" && request.method === "GET") {
    const agent = validateEnum(url.searchParams.get("agent") || "jules", VALID_AGENTS, "agent", env);
    if (agent.response) return agent.response;
    return withBoard(env, (data) => json(qaStatus(data, agent.value), 200, env));
  }
  if (path === "/api/readiness" && request.method === "GET") {
    const agent = validateEnum(url.searchParams.get("agent") || "jules", VALID_AGENTS, "agent", env);
    if (agent.response) return agent.response;
    return withBoard(env, (data) => json(readiness(data, env, agent.value), 200, env));
  }
  if (path === "/api/tasks" && request.method === "GET") return withBoard(env, (data) => json({ tasks: data.tasks || [], count: (data.tasks || []).length }, 200, env));

  if (path === "/api/release-stale" && request.method === "POST") {
    const auth = requirePersona(request, env, ["owner"]);
    if (auth.response) return auth.response;
    const hoursRaw = Number(url.searchParams.get("hours") || "24");
    if (!Number.isFinite(hoursRaw) || hoursRaw < 0 || hoursRaw > 8760) return error("hours must be a number between 0 and 8760", 422, env);
    const hours = hoursRaw;
    const dryRun = (url.searchParams.get("dry_run") || "true") !== "false";
    if (!dryRun) requireMutableBoard(env);
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
    let rawBody;
    try { rawBody = await request.json(); } catch { return error("invalid JSON body", 422, env); }
    const body = safeParseBody(rawBody, ["agent", "limit", "task_id", "live"]);
    const agent = validateEnum(body.agent || "jules", VALID_DISPATCH_AGENTS, "agent", env);
    if (agent.response) return agent.response;
    const taskId = body.task_id === undefined || body.task_id === null ? { value: null } : validateTaskId(body.task_id, env);
    if (taskId.response) return taskId.response;
    const limit = validateInteger(body.limit, "limit", env, { defaultValue: 1, min: 1, max: 100 });
    if (limit.response) return limit.response;
    if (body.live !== undefined && typeof body.live !== "boolean") return error("live must be a boolean", 422, env);
    if (body.live === true) requireMutableBoard(env);
    const doc = await loadBoard(env);
    const candidates = [];
    const intakeBlocked = [];
    for (const task of dispatchCandidates(doc.data, agent.value, taskId.value)) {
      if (candidates.length >= limit.value) break;
      try {
        normalizeSelectedLegacyTask(task);
        candidates.push(task);
      } catch (err) {
        intakeBlocked.push({ id: String(task.id || "unknown"), reason: err instanceof Error ? err.message : String(err) });
      }
    }
    if (body.live === true) return error("live dispatch is not implemented by the Cloudflare adapter", 501, env);
    return json({ status: "dry_run", count: candidates.length, candidates, tasks: candidates, intake_blocked: intakeBlocked, live: false, agent: agent.value }, 200, env);
  }

  const taskMatch = path.match(/^\/api\/tasks\/([^/]+)(?:\/(verify|assign|archive))?$/);
  if (taskMatch) {
    const auth = requirePersona(request, env, ["owner"]);
    if (auth.response) return auth.response;
    const taskId = validateTaskId(decodeURIComponent(taskMatch[1]), env);
    if (taskId.response) return taskId.response;
    const action = taskMatch[2];
    if (!action && request.method === "GET") return withBoard(env, (data) => json(findTask(data, taskId.value), 200, env));
    if (request.method !== "POST") return error("method not allowed", 405, env);
    requireMutableBoard(env);
    let rawBody;
    try { rawBody = await request.json(); } catch { return error("invalid JSON body", 422, env); }
    const body = safeParseBody(rawBody, ["status", "note", "session_id", "target_agent", "priority", "budget_cost", "predicate", "receipt_target"]);
    const doc = await loadBoard(env);
    const task = findTask(doc.data, taskId.value);
    if (action === "verify") {
      const status = validateEnum(body.status || "done", VERIFY_STATUSES, "status", env);
      if (status.response) return status.response;
      const sessionId = validateText(body.session_id, "session_id", env, { defaultValue: "qa-verify", max: 128 });
      if (sessionId.response) return sessionId.response;
      const note = validateText(body.note, "note", env, { defaultValue: "", max: 2000 });
      if (note.response) return note.response;
      if (!["dispatched", "in_progress", "needs_human", "failed", "failed_blocked", "done"].includes(task.status)) return error("only active, attention, or done tasks can be verified", 409, env);
      task.status = status.value;
      appendLog(task, "qa", sessionId.value, task.status, note.value || `QA verified task as ${task.status}`);
      await saveBoard(env, doc.data, doc.sha);
      return json({ status: "verified", task, verified_status: task.status }, 200, env);
    }
    if (action === "assign") {
      const sessionId = validateText(body.session_id, "session_id", env, { defaultValue: "assignment", max: 128 });
      if (sessionId.response) return sessionId.response;
      const note = validateText(body.note, "note", env, { defaultValue: "", max: 2000 });
      if (note.response) return note.response;
      const before = {
        target_agent: task.target_agent,
        priority: task.priority,
        budget_cost: task.budget_cost,
        status: task.status,
        predicate: task.predicate,
        receipt_target: task.receipt_target,
      };
      if (body.target_agent !== undefined) {
        const targetAgent = validateEnum(body.target_agent, VALID_AGENTS, "target_agent", env);
        if (targetAgent.response) return targetAgent.response;
        task.target_agent = targetAgent.value;
      }
      if (body.priority !== undefined) {
        const priority = validateEnum(body.priority, VALID_PRIORITIES, "priority", env);
        if (priority.response) return priority.response;
        task.priority = priority.value;
      }
      if (body.budget_cost !== undefined) {
        const cost = validateInteger(body.budget_cost, "budget_cost", env, { min: 1, max: 100 });
        if (cost.response) return cost.response;
        task.budget_cost = cost.value;
      }
      if (body.predicate !== undefined) {
        const predicate = validateText(body.predicate, "predicate", env, { max: 2000 });
        if (predicate.response) return predicate.response;
        task.predicate = predicate.value;
      }
      if (body.receipt_target !== undefined) {
        const receiptTarget = validateText(body.receipt_target, "receipt_target", env, { max: 2048 });
        if (receiptTarget.response) return receiptTarget.response;
        task.receipt_target = receiptTarget.value;
      }
      if (body.status !== undefined) {
        const status = validateEnum(body.status, VALID_STATUSES, "status", env);
        if (status.response) return status.response;
        task.status = status.value;
      }
      try {
        validateIntakeContract(task);
      } catch (err) {
        if (err instanceof IntakeContractError) return error(`typed intake contract rejected: ${err.message}`, 422, env);
        throw err;
      }
      const after = {
        target_agent: task.target_agent,
        priority: task.priority,
        budget_cost: task.budget_cost,
        status: task.status,
        predicate: task.predicate,
        receipt_target: task.receipt_target,
      };
      const changed = Object.keys(after).filter((key) => before[key] !== after[key]);
      appendLog(task, "api", sessionId.value, "assigned", note.value || `Assigned via steering controls: ${changed.join(", ") || "no field changes"}`);
      await saveBoard(env, doc.data, doc.sha);
      return json({ status: "assigned", task, changed }, 200, env);
    }
    if (action === "archive") {
      const sessionId = validateText(body.session_id, "session_id", env, { defaultValue: "archive", max: 128 });
      if (sessionId.response) return sessionId.response;
      const note = validateText(body.note, "note", env, { defaultValue: "", max: 2000 });
      if (note.response) return note.response;
      if (!["done", "archived"].includes(task.status)) return error("only done tasks can be archived", 409, env);
      if (task.status !== "archived") {
        task.status = "archived";
        appendLog(task, "api", sessionId.value, "archived", note.value || "Archived from QA steering");
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
      if (err instanceof BoardMutationDeferred) {
        return json({
          status: "mutation_deferred",
          code: err.code,
          retryable: err.retryable,
          owner: err.owner,
          target: err.target,
          detail: err.message,
          next_action: "Submit a TABVLARIVS ticket and let the keeper publish the board projection PR",
        }, 409, env);
      }
      return error(err instanceof Error ? err.message : "runtime error", 500, env);
    }
  },
};

export { isDurableReceiptTarget, isExecutablePredicate, normalizeSelectedLegacyTask, validateIntakeContract };
