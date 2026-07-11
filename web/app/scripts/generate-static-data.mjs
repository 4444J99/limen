#!/usr/bin/env node
import { copyFileSync, existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync, readdirSync, statSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import YAML from "yaml";

const __dirname = dirname(fileURLToPath(import.meta.url));
const appRoot = join(__dirname, "..");
const repoRoot = join(appRoot, "..", "..");
const limenRoot = process.env.LIMEN_ROOT || repoRoot;
const sourcePath = join(repoRoot, "tasks.yaml");
const privateDir = join(appRoot, ".generated", "surfaces");
const outPath = join(privateDir, "tasks.json");
const publicStatusPath = join(appRoot, "public", "public-status.json");
const clientStatusPath = join(privateDir, "client-status.json");
const internalStatusPath = join(privateDir, "internal-status.json");
const surfaceManifestPath = join(appRoot, "public", "surface-manifest.json");
const fleetStatusSourcePath = process.env.LIMEN_FLEET_STATUS || join(limenRoot, "logs", "fleet-status.json");
const fleetStatusOutPath = join(appRoot, "public", "logs", "fleet-status.json");
const ownerSurfaceManifestPath = join(privateDir, "owner-surface-manifest.json");
const clientSurfaceManifestPath = join(privateDir, "client-surface-manifest.json");
const publicSurfaceManifestPath = join(appRoot, "public", "public-surface-manifest.json");
const readinessPath = join(privateDir, "readiness.json");
const qaStatusPath = join(privateDir, "qa-status.json");
const corpusStatusSourcePath = process.env.LIMEN_CORPUS_STATUS || join(limenRoot, ".limen-private", "session-corpus", "lifecycle", "corpus-command-center.public.json");
const corpusStatusPath = join(privateDir, "corpus-status.json");
const observatoryBriefSourcePath = process.env.LIMEN_OBSERVATORY_BRIEF || join(limenRoot, "logs", "observatory", "brief-latest.json");
const observatoryStatusPath = join(privateDir, "observatory-status.json");
const hostedPrivatePaths = [
  join(appRoot, "public", "tasks.json"),
  join(appRoot, "public", "client-status.json"),
  join(appRoot, "public", "internal-status.json"),
  join(appRoot, "public", "qa-status.json"),
  join(appRoot, "public", "corpus-status.json"),
  join(appRoot, "public", "observatory-status.json"),
  join(appRoot, "public", "owner-surface-manifest.json"),
  join(appRoot, "public", "client-surface-manifest.json"),
  join(appRoot, "public", "readiness.json"),
];

function countBy(items, keyFn) {
  return items.reduce((acc, item) => {
    const key = keyFn(item) || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function mirrorFleetStatus() {
  mkdirSync(dirname(fleetStatusOutPath), { recursive: true });
  if (existsSync(fleetStatusOutPath)) unlinkSync(fleetStatusOutPath);

  if (!existsSync(fleetStatusSourcePath)) {
    console.log(`Fleet status feed not found at ${fleetStatusSourcePath}`);
    return;
  }

  copyFileSync(fleetStatusSourcePath, fleetStatusOutPath);
  console.log(`Mirrored ${fleetStatusSourcePath} to ${fleetStatusOutPath}`);
}

function parseDateOnly(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString().slice(0, 10);
}

function getTaskEvents(task) {
  return (task.dispatch_log || [])
    .filter((entry) => entry && entry.timestamp)
    .map((entry) => ({
      ...entry,
      task_id: task.id,
      task_title: task.title,
      repo: task.repo,
      timestamp_ms: Date.parse(entry.timestamp),
    }))
    .filter((entry) => Number.isFinite(entry.timestamp_ms));
}

function deriveVendors(data, todayEvents) {
  // Per-lane usage + refresh, derived from the already-present portal.budget.
  // Mirrors web/api/main.py remaining_budget(): remaining = min(daily-left, cap-spent).
  const budget = data.portal?.budget || {};
  const caps = budget.per_agent || {};
  const daily = Number(budget.daily || 100);
  const dailySpent = Number(budget.track?.spent || 0);
  const trackPer = budget.track?.per_agent || {};
  const tasks = data.tasks || [];
  const order = ["jules", "codex", "opencode", "agy", "claude", "gemini"];
  const names = Array.from(new Set([...order, ...Object.keys(caps)])).filter((a) => caps[a] != null);
  return names.map((agent) => {
    const cap = Number(caps[agent] || 0);
    const spent = Number(trackPer[agent] || 0);
    const remaining = Math.max(0, Math.min(daily - dailySpent, cap - spent));
    return {
      agent,
      kind: agent === "jules" ? "cloud" : "local",
      cap,
      spent,
      remaining,
      pct: cap ? Math.round((spent / cap) * 100) : 0,
      open: tasks.filter((t) => t.status === "open" && t.target_agent === agent).length,
      today_dispatches: todayEvents.filter((e) => e.agent === agent && e.status === "dispatched").length,
    };
  });
}

function readTicks() {
  try {
    const p = join(repoRoot, "logs", "ticks.jsonl");
    if (!existsSync(p)) return [];
    const lines = readFileSync(p, "utf8").trim().split("\n").filter(Boolean);
    return lines.slice(-40).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  } catch {
    return [];
  }
}

function deriveSummary(data) {
  const tasks = data.tasks || [];
  const events = tasks.flatMap(getTaskEvents).sort((a, b) => b.timestamp_ms - a.timestamp_ms);
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const todayEvents = events.filter((event) => new Date(event.timestamp_ms).toISOString().slice(0, 10) === today);
  const todayJulesDispatches = todayEvents.filter((event) => event.agent === "jules" && event.status === "dispatched");
  const activeTasks = tasks.filter((task) => ["dispatched", "in_progress"].includes(task.status));
  const staleTasks = activeTasks.filter((task) => {
    const latest = getTaskEvents(task).sort((a, b) => b.timestamp_ms - a.timestamp_ms)[0];
    if (!latest) return true;
    return now.getTime() - latest.timestamp_ms > 24 * 60 * 60 * 1000;
  });

  return {
    generated_at: now.toISOString(),
    total: tasks.length,
    by_status: countBy(tasks, (task) => task.status),
    by_agent: countBy(tasks, (task) => task.target_agent),
    by_priority: countBy(tasks, (task) => task.priority),
    by_repo: countBy(tasks, (task) => task.repo),
    active_count: activeTasks.length,
    stale_count: staleTasks.length,
    stale_task_ids: staleTasks.map((task) => task.id),
    today,
    today_events: todayEvents.length,
    today_jules_dispatches: todayJulesDispatches.length,
    per_vendor: deriveVendors(data, todayEvents),
    daily_total: {
      spent: Number(data.portal?.budget?.track?.spent || 0),
      cap: Number(data.portal?.budget?.daily || 300),
      date: data.portal?.budget?.track?.date || null,
    },
    ticks: readTicks(),
    throughput: deriveThroughput(data, events, now),
    recent_events: events.slice(0, 40),
  };
}

function deriveThroughput(data, events, now = new Date()) {
  const tasks = data.tasks || [];
  const currentDate = now.toISOString().slice(0, 10);
  const createdDates = tasks.map((task) => parseDateOnly(task.created)).filter(Boolean).sort();
  const firstCreated = createdDates[0] || currentDate;
  const ageDays = Math.max(1, Math.floor((Date.parse(`${currentDate}T00:00:00.000Z`) - Date.parse(`${firstCreated}T00:00:00.000Z`)) / 86400000) + 1);
  const dailyCapacity = Number(data.portal?.budget?.daily || 100);
  const byStatus = countBy(tasks, (task) => task.status);
  const byEventStatus = countBy(events, (event) => event.status);
  const byEventAgent = countBy(events, (event) => event.agent);
  const byEventDate = countBy(events, (event) => new Date(event.timestamp_ms).toISOString().slice(0, 10));
  const done = (byStatus.done || 0) + (byStatus.archived || 0);
  const recordedStarts = (byEventStatus.dispatched || 0) + (byEventStatus.in_progress || 0);
  const recordedFinishes = (byEventStatus.done || 0) + (byEventStatus.completed || 0) + (byEventStatus.failed || 0) + (byEventStatus.failed_blocked || 0);
  const expectedCapacityRuns = dailyCapacity * ageDays;
  const unrecordedCapacityRuns = Math.max(0, expectedCapacityRuns - recordedStarts);
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
    unrecorded_capacity_runs: unrecordedCapacityRuns,
    by_event_status: byEventStatus,
    by_event_agent: byEventAgent,
    by_event_date: byEventDate,
  };
}

function publicSummary(data, generatedAt) {
  const tasks = data.tasks || [];
  const byStatus = countBy(tasks, (task) => task.status);
  const completed = byStatus.done || 0;
  return {
    portal: {
      name: data.portal?.name || "Universal Task Intake",
      description: data.portal?.description || "",
    },
    total: tasks.length,
    completed,
    completion_rate: Number((completed / Math.max(1, tasks.length)).toFixed(3)),
    active: (byStatus.dispatched || 0) + (byStatus.in_progress || 0),
    by_status: byStatus,
    generated_at: generatedAt,
    throughput: deriveThroughput(data, (data.tasks || []).flatMap(getTaskEvents), new Date(generatedAt)),
  };
}

function clientSummary(data, summary) {
  const topRepos = Object.entries(summary.by_repo)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([repo, count]) => ({ repo, count }));
  const activeTasks = (data.tasks || [])
    .filter((task) => ["dispatched", "in_progress"].includes(task.status) || summary.stale_task_ids.includes(task.id))
    .slice(0, 25)
    .map((task) => {
      const lifecycle = taskLifecycle(task, summary);
      return {
        id: task.id,
        title: task.title,
        repo: task.repo || "",
        target_agent: task.target_agent || "unknown",
        status: task.status || "unknown",
        priority: task.priority || "medium",
        stale: summary.stale_task_ids.includes(task.id),
        phase: lifecycle.phase,
        next_gate: lifecycle.next_gate,
      };
    });
  const lifecycle = { recover: 0, verify: 0, assign: 0, archive: 0, archived: 0 };
  for (const task of data.tasks || []) {
    const phase = taskLifecycle(task, summary).phase;
    lifecycle[phase] = (lifecycle[phase] || 0) + 1;
  }
  return {
    ...publicSummary(data, summary.generated_at),
    stale_count: summary.stale_count,
    lifecycle,
    budget: data.portal?.budget || { daily: 100, unit: "runs" },
    top_repos: topRepos,
    active_tasks: activeTasks,
  };
}

function readinessReport(data, summary) {
  const budget = data.portal?.budget || { daily: 100, per_agent: { jules: 100 }, track: { spent: 0, per_agent: {} } };
  const julesLimit = budget.per_agent?.jules || budget.daily || 100;
  const julesSpent = budget.track?.per_agent?.jules || 0;
  const remaining = Math.max(0, Math.min((budget.daily || 100) - (budget.track?.spent || 0), julesLimit - julesSpent));
  const openJules = (data.tasks || []).filter((task) => task.status === "open" && ["jules", "any"].includes(task.target_agent)).length;
  const checks = [
    { id: "static_surfaces", status: "pass", detail: "public-safe static shells generated" },
    { id: "surface_contracts", status: "pass", detail: "public hosted contracts and private validation snapshots generated" },
    { id: "api_runtime", status: process.env.NEXT_PUBLIC_API_URL ? "pass" : "warn", detail: process.env.NEXT_PUBLIC_API_URL || "backend runtime not attached to Firebase static hosting" },
    { id: "stale_claims", status: summary.stale_count ? "warn" : "pass", detail: `${summary.stale_count} stale active tasks` },
    { id: "open_jules_queue", status: openJules ? "pass" : "warn", detail: `${openJules} open Jules tasks` },
    { id: "jules_budget", status: remaining > 0 ? "pass" : "fail", detail: `${remaining}/${julesLimit} Jules runs remaining` },
  ];
  const status = checks.some((check) => check.status === "fail")
    ? "blocked"
    : checks.some((check) => check.status === "warn")
      ? "degraded"
      : "ready";
  const nextActions = [];
  if (summary.stale_count) {
    nextActions.push(process.env.NEXT_PUBLIC_API_URL ? "POST /api/release-stale?hours=24&dry_run=false" : "limen release-stale --agent jules --hours 24 --apply");
  }
  if (openJules && remaining > 0) nextActions.push(`limen dispatch --agent jules --limit ${Math.min(openJules, remaining)} --live`);
  if (!process.env.NEXT_PUBLIC_API_URL) nextActions.push("Attach a backend runtime and rebuild with NEXT_PUBLIC_API_URL");
  return {
    status,
    generated_at: summary.generated_at,
    agent: "jules",
    counts: {
      total: summary.total,
      active: summary.active_count,
      stale: summary.stale_count,
      open_jules: openJules,
    },
    budget: {
      daily: budget.daily || 100,
      agent_limit: julesLimit,
      agent_spent: julesSpent,
      remaining,
    },
    checks,
    next_actions: nextActions.length ? nextActions : ["No immediate action required"],
  };
}

function taskLifecycle(task, summary) {
  const events = getTaskEvents(task).sort((a, b) => b.timestamp_ms - a.timestamp_ms);
  const latest = events[0];
  const stale = summary.stale_task_ids.includes(task.id);
  const hasPR = (task.urls || []).some((url) => url.includes("/pull/"));
  const hasIssue = (task.urls || []).some((url) => url.includes("/issues/"));
  const isDone = task.status === "done";
  const phase = ["archived", "cancelled"].includes(task.status)
    ? "archived"
    : isDone
      ? "archive"
      : stale || ["failed", "failed_blocked", "needs_human"].includes(task.status)
        ? "recover"
        : hasPR || ["dispatched", "in_progress"].includes(task.status)
          ? "verify"
          : "assign";
  const nextGate = phase === "archived"
    ? "suppressed from active steering"
    : isDone
      ? "archive evidence and suppress from active steering"
      : phase === "recover"
        ? "release stale claim or reassign with failure note"
        : phase === "verify"
          ? "verify PR/runtime evidence, then close or return"
          : "assign to agent with budget and acceptance gate";
  const assignee = task.target_agent || "unassigned";

  return {
    id: task.id,
    title: task.title,
    repo: task.repo || "",
    status: task.status || "unknown",
    priority: task.priority || "medium",
    assignee,
    phase,
    next_gate: nextGate,
    stale,
    has_issue: hasIssue,
    has_pr: hasPR,
    latest_event_at: latest?.timestamp || task.updated || task.created || null,
  };
}

function qaStatus(data, summary) {
  const items = (data.tasks || []).map((task) => taskLifecycle(task, summary));
  const steering = items
    .filter((item) => !["archive", "archived"].includes(item.phase))
    .sort((a, b) => {
      const order = { recover: 0, verify: 1, assign: 2, archive: 3, archived: 4 };
      // MUST mirror limen.doctor.qa_report's priority_order (Python source of truth) — was missing
      // `critical`/`backlog`, so critical tasks sorted LAST here (?? 9) but FIRST in the CLI →
      // next_batch drift that verify-whole.sh caught once critical-priority CIFIX tasks existed.
      const priority = { critical: 0, high: 1, medium: 2, low: 3, backlog: 4 };
      return (order[a.phase] ?? 9) - (order[b.phase] ?? 9)
        || (priority[a.priority] ?? 9) - (priority[b.priority] ?? 9)
        || String(a.id).localeCompare(String(b.id));
    });
  const archiveReady = items.filter((item) => item.phase === "archive");
  const qaItems = items.filter((item) => item.phase === "verify");
  const recoverItems = items.filter((item) => item.phase === "recover");
  const assignItems = items.filter((item) => item.phase === "assign");
  const archivedItems = items.filter((item) => item.phase === "archived");

  return {
    status: recoverItems.length ? "degraded" : "ok",
    surface: "qa",
    generated_at: summary.generated_at,
    lifecycle: {
      total: items.length,
      assign: assignItems.length,
      verify: qaItems.length,
      recover: recoverItems.length,
      archive_ready: archiveReady.length,
      archived: archivedItems.length,
    },
    steering: {
      principle: "Every visible item is a portal into one task lifecycle; closed work is archived out of active steering.",
      next_batch: steering.slice(0, 24),
      qa_queue: qaItems.slice(0, 24),
      recovery_queue: recoverItems.slice(0, 24),
      assignment_queue: assignItems.slice(0, 24),
      archive_queue: archiveReady.slice(0, 24),
    },
    mechanisms: [
      {
        id: "release-stale",
        label: "Release stale claims",
        agent: "jules",
        command: "POST /api/release-stale?hours=24&dry_run=false",
        mode: "human-approved apply",
        count: recoverItems.length,
      },
      {
        id: "qa-verify",
        label: "Verify PR and runtime evidence",
        agent: "qa",
        command: "POST /api/tasks/{task_id}/verify",
        mode: "human-approved evidence gate",
        count: qaItems.length,
      },
      {
        id: "assign-next",
        label: "Assign or reassign next task",
        agent: "steering",
        command: "POST /api/tasks/{task_id}/assign",
        mode: "human-approved assignment",
        count: assignItems.length,
      },
      {
        id: "archive-done",
        label: "Archive closed evidence",
        agent: "system",
        command: "POST /api/tasks/{task_id}/archive",
        mode: "human-approved archive",
        count: archiveReady.length,
      },
    ],
  };
}

function corpusStatus() {
  if (existsSync(corpusStatusSourcePath)) {
    return JSON.parse(readFileSync(corpusStatusSourcePath, "utf8"));
  }
  return {
    status: "missing",
    surface: "corpus",
    generated_at: new Date(0).toISOString(),
    privacy: {
      redacted: true,
      contains_raw_text: false,
      private_index: ".limen-private/session-corpus/lifecycle/corpus-command-center.private.json",
      private_html: ".limen-private/session-corpus/lifecycle/corpus-command-center.private.html",
    },
    coverage: {
      units: 0,
      sessions_indexed: 0,
      unique_hashes: 0,
      clusters: 0,
      comparisons: 0,
      allusion_rows: 0,
      private_object_count: 0,
      kinds: {},
      lanes: {},
      sources: {},
    },
    units: [],
    truncated_units: false,
    clusters: [],
    comparisons: [],
    allusions: [],
    aug1: {
      deadline: "2026-08-01",
      gate_pass: false,
      legs_total: 0,
      legs_met: 0,
      ledger: {},
    },
    inbound: {
      value_repo_count: 0,
      seeded_repo_count: 0,
      frontdoor_present: false,
      discoverability_present: false,
      scraper_model_present: false,
      capture_contact_configured: false,
    },
  };
}

function observatoryStatus() {
  // Owner surface: wrap the organ's daily brief (logs/observatory/brief-latest.json) with a
  // surface envelope. Tolerant of absence (the organ ships dark) — a missing brief yields a
  // "missing" stub so the build always succeeds, mirroring corpusStatus()/mirrorInsights().
  if (existsSync(observatoryBriefSourcePath)) {
    const brief = JSON.parse(readFileSync(observatoryBriefSourcePath, "utf8"));
    return {
      status: "ok",
      surface: "observatory",
      generated_at: statSync(observatoryBriefSourcePath).mtime.toISOString(),
      ...brief,
    };
  }
  return {
    status: "missing",
    surface: "observatory",
    generated_at: new Date(0).toISOString(),
    schema: "limen.observatory.brief.v1",
    date: null,
    hero: null,
    internal_gaps: 0,
    external_gaps: 0,
    confounders: [],
    mechanisms: [],
    experiment: null,
    measurement_contract: null,
  };
}

function surfaceManifest(summary) {
  const generatedAt = summary.generated_at;
  return {
    status: "ok",
    generated_at: generatedAt,
    source: {
      type: "static-build",
      task_file: "tasks.yaml",
      api_runtime: process.env.NEXT_PUBLIC_API_URL ? "connected" : "not_connected",
      api_url_configured: Boolean(process.env.NEXT_PUBLIC_API_URL),
      blocker: process.env.NEXT_PUBLIC_API_URL ? null : "backend runtime not attached to Firebase static hosting",
    },
    surfaces: [
      {
        id: "internal",
        title: "Internal operations",
        route: "/",
        contract: "/internal-status.json",
        persona: "owner",
        sanctioned_personas: ["owner"],
        disclosure: "full task board, dispatch controls, PR health, and operational logs",
      },
      {
        id: "client",
        title: "Client status",
        route: "/client",
        contract: "/client-status.json",
        persona: "client",
        sanctioned_personas: ["owner", "client"],
        disclosure: "redacted active task rows, delivery metrics, budget, and repo distribution",
      },
      {
        id: "public",
        title: "Public status",
        route: "/public",
        contract: "/public-status.json",
        persona: "public",
        sanctioned_personas: ["owner", "client", "public"],
        disclosure: "aggregate task health only",
      },
      {
        id: "qa",
        title: "QA and steering",
        route: "/qa",
        contract: "/qa-status.json",
        persona: "owner",
        sanctioned_personas: ["owner"],
        disclosure: "lifecycle gates, assignment queues, verification queues, and archive suppression",
      },
      {
        id: "corpus",
        title: "Corpus command center",
        route: "/corpus",
        contract: "/corpus-status.json",
        persona: "owner",
        sanctioned_personas: ["owner"],
        disclosure: "redacted prompt/reply/artifact atlas, Aug-1 gate, inbound magnet, and private corpus pointers",
      },
      {
        id: "observatory",
        title: "Observatory",
        route: "/observatory",
        contract: "/observatory-status.json",
        persona: "owner",
        sanctioned_personas: ["owner"],
        disclosure: "daily legibility & traction brief: winner mechanisms, confounders, gaps, and one human-gated experiment",
      },
    ],
    contracts: {
      internal: {
        path: "/internal-status.json",
        total: summary.total,
        stale_count: summary.stale_count,
        includes_full_tasks: false,
      },
      client: {
        path: "/client-status.json",
        total: summary.total,
        stale_count: summary.stale_count,
        max_active_tasks: 25,
        includes_dispatch_logs: false,
      },
      public: {
        path: "/public-status.json",
        total: summary.total,
        includes_tasks: false,
        includes_dispatch_logs: false,
      },
      readiness: {
        path: "/readiness.json",
        agent: "jules",
        includes_dispatch_logs: false,
      },
      qa: {
        path: "/qa-status.json",
        verify_endpoint: "/api/tasks/{task_id}/verify",
        assignment_endpoint: "/api/tasks/{task_id}/assign",
        archive_endpoint: "/api/tasks/{task_id}/archive",
        includes_dispatch_logs: false,
        includes_task_context: false,
        includes_task_urls: false,
      },
      corpus: {
        path: "/corpus-status.json",
        includes_raw_text: false,
        includes_private_paths: false,
      },
      observatory: {
        path: "/observatory-status.json",
        includes_raw_text: false,
        human_gated_experiment: true,
      },
    },
  };
}

function sanctionedManifest(manifest, persona) {
  return {
    ...manifest,
    persona,
    surfaces: manifest.surfaces.filter((surface) => surface.sanctioned_personas.includes(persona)),
    contracts: Object.fromEntries(
      Object.entries(manifest.contracts).filter(([id]) => (
        (id === "readiness" && persona === "owner") || manifest.surfaces.some((surface) => (
          surface.id === id && surface.sanctioned_personas.includes(persona)
        ))
      )),
    ),
  };
}


function mirrorInsights() {
  const tiers = ["hourly", "daily", "weekly", "monthly"];
  const insightDir = join(limenRoot, "logs", "insight-cadence");
  let insightFiles = [];
  if (existsSync(insightDir)) {
    insightFiles = readdirSync(insightDir).filter(f => f.endsWith(".json"));
  }

  for (const tier of tiers) {
    const dest = join(appRoot, "public", `${tier}-insights.json`);
    const tierFiles = insightFiles.filter(f => f.startsWith(`${tier}-`));
    
    // Find the latest file by sorting alphabetically (timestamp is in ISO format)
    tierFiles.sort();
    const latestFile = tierFiles.length > 0 ? tierFiles[tierFiles.length - 1] : null;

    if (latestFile) {
      const src = join(insightDir, latestFile);
      copyFileSync(src, dest);
    } else {
      // Create empty payload if missing so build succeeds
      writeFileSync(dest, JSON.stringify({
        tier,
        generated_at: new Date().toISOString(),
        window_start: new Date().toISOString(),
        insights: []
      }));
    }
  }
}

const data = YAML.parse(readFileSync(sourcePath, "utf8"));
const summary = deriveSummary(data);
const output = {
  ...data,
  summary,
};
const publicStatus = {
  status: "ok",
  surface: "public",
  summary: publicSummary(data, summary.generated_at),
};
const clientStatus = {
  status: "ok",
  surface: "client",
  summary: clientSummary(data, summary),
};
const internalStatus = {
  status: "ok",
  surface: "internal",
  summary,
  portal: data.portal || {},
  storage: { mode: "static", path: "tasks.yaml", configured: true },
};
const manifest = surfaceManifest(summary);
const ownerManifest = sanctionedManifest(manifest, "owner");
const clientManifest = sanctionedManifest(manifest, "client");
const publicManifest = sanctionedManifest(manifest, "public");
const readiness = readinessReport(data, summary);
const qa = qaStatus(data, summary);
const corpus = corpusStatus();
const observatory = observatoryStatus();

mkdirSync(dirname(outPath), { recursive: true });
mkdirSync(dirname(publicStatusPath), { recursive: true });
for (const path of hostedPrivatePaths) {
  if (existsSync(path)) unlinkSync(path);
}
writeFileSync(outPath, `${JSON.stringify(output, null, 2)}\n`);
writeFileSync(publicStatusPath, `${JSON.stringify(publicStatus, null, 2)}\n`);
writeFileSync(clientStatusPath, `${JSON.stringify(clientStatus, null, 2)}\n`);
writeFileSync(internalStatusPath, `${JSON.stringify(internalStatus, null, 2)}\n`);
writeFileSync(surfaceManifestPath, `${JSON.stringify(publicManifest, null, 2)}\n`);
writeFileSync(ownerSurfaceManifestPath, `${JSON.stringify(ownerManifest, null, 2)}\n`);
writeFileSync(clientSurfaceManifestPath, `${JSON.stringify(clientManifest, null, 2)}\n`);
writeFileSync(publicSurfaceManifestPath, `${JSON.stringify(publicManifest, null, 2)}\n`);
writeFileSync(readinessPath, `${JSON.stringify(readiness, null, 2)}\n`);
writeFileSync(qaStatusPath, `${JSON.stringify(qa, null, 2)}\n`);
writeFileSync(corpusStatusPath, `${JSON.stringify(corpus, null, 2)}\n`);
writeFileSync(observatoryStatusPath, `${JSON.stringify(observatory, null, 2)}\n`);
mirrorFleetStatus();
mirrorInsights();
console.log(`Generated ${outPath} with ${output.tasks?.length || 0} tasks`);
console.log("Generated public-safe hosted contracts and private validation snapshots");
