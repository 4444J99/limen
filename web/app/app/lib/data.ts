import { readFileSync } from "fs";
import { join } from "path";
import type { DashboardData, PRStatusData, Task } from "../dashboard-client";

export interface PublicStatusData {
  status: string;
  surface: "public";
  summary: {
    portal: {
      name: string;
      description: string;
    };
    total: number;
    completed: number;
    completion_rate: number;
    active: number;
    by_status: Record<string, number>;
    generated_at: string;
  };
}

export interface ClientStatusData {
  status: string;
  surface: "client";
  summary: PublicStatusData["summary"] & {
    stale_count: number;
    lifecycle: {
      recover: number;
      verify: number;
      assign: number;
      archive: number;
      archived: number;
    };
    budget: {
      daily: number;
      unit: string;
      per_agent?: Record<string, number>;
      track?: { date: string; spent: number; per_agent?: Record<string, number> };
    };
    top_repos: { repo: string; count: number }[];
    active_tasks: {
      id: string;
      title: string;
      repo: string;
      target_agent: string;
      status: string;
      priority: string;
      stale: boolean;
      phase?: "assign" | "verify" | "recover" | "archive" | "archived";
      next_gate?: string;
    }[];
  };
}

export interface SurfaceManifestData {
  status: string;
  persona?: "owner" | "client" | "public";
  generated_at: string;
  source: {
    type: string;
    task_file: string;
    api_runtime: string;
    api_url_configured: boolean;
    blocker: string | null;
  };
  surfaces: {
    id: "internal" | "client" | "public" | "qa";
    title: string;
    route: string;
    contract: string;
    persona?: "owner" | "client" | "public";
    sanctioned_personas?: ("owner" | "client" | "public")[];
    disclosure: string;
  }[];
  contracts: Record<string, Record<string, string | number | boolean | null>>;
}

export interface ReadinessData {
  status: "ready" | "degraded" | "blocked" | "missing";
  generated_at: string;
  agent: string;
  counts: Record<string, number>;
  budget: Record<string, number>;
  checks: { id: string; status: "pass" | "warn" | "fail"; detail: string }[];
  next_actions: string[];
}

export interface QASteeringItem {
  id: string;
  title: string;
  repo: string;
  status: string;
  priority: string;
  assignee: string;
  phase: "assign" | "verify" | "recover" | "archive" | "archived";
  next_gate: string;
  stale: boolean;
  has_issue: boolean;
  has_pr: boolean;
  latest_event_at: string | null;
}

export interface QAMechanism {
  id: string;
  label: string;
  agent: string;
  command: string;
  mode: string;
  count: number;
}

export interface QAStatusData {
  status: "ok" | "degraded" | "missing";
  surface: "qa";
  generated_at: string;
  lifecycle: {
    total: number;
    assign: number;
    verify: number;
    recover: number;
    archive_ready: number;
    archived: number;
  };
  steering: {
    principle: string;
    next_batch: QASteeringItem[];
    qa_queue: QASteeringItem[];
    recovery_queue: QASteeringItem[];
    assignment_queue: QASteeringItem[];
    archive_queue: QASteeringItem[];
  };
  mechanisms: QAMechanism[];
}

function readJson<T>(path: string, fallback: T): T {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return fallback;
  }
}

export function getPublicSurfaceData() {
  const publicDir = join(process.cwd(), "public");
  return {
    statusData: readJson<PublicStatusData>(join(publicDir, "public-status.json"), {
      status: "missing",
      surface: "public",
      summary: {
        portal: {
          name: "Limen",
          description: "",
        },
        total: 0,
        completed: 0,
        completion_rate: 0,
        active: 0,
        by_status: {},
        generated_at: new Date(0).toISOString(),
      },
    }),
    prData: readJson<PRStatusData | null>(join(publicDir, "pr-status.json"), null),
    manifest: getSurfaceManifest(),
  };
}

export function getSurfaceManifest() {
  const publicDir = join(process.cwd(), "public");
  return readJson<SurfaceManifestData>(join(publicDir, "surface-manifest.json"), {
    status: "missing",
    persona: "public",
    generated_at: new Date(0).toISOString(),
    source: {
      type: "static-build",
      task_file: "tasks.yaml",
      api_runtime: "unknown",
      api_url_configured: false,
      blocker: "surface manifest missing",
    },
    surfaces: [],
    contracts: {},
  });
}

export function formatDate(value?: string) {
  if (!value) return "Never";
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(time));
}

export function repoName(repo: string) {
  return repo ? repo.split("/").pop() || repo : "limen";
}

export function isActive(task: Task) {
  return ["dispatched", "in_progress"].includes(task.status);
}

export function isAttentionTask(task: Task, staleIds: string[]) {
  return staleIds.includes(task.id) || ["failed", "failed_blocked", "needs_human"].includes(task.status);
}

export function topRepos(data: DashboardData, limit = 6) {
  return Object.entries(data.summary.by_repo)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([repo, count]) => ({ repo, name: repoName(repo), count }));
}

export function recentActiveTasks(data: DashboardData, limit = 8) {
  return data.tasks
    .filter((task) => isActive(task) || isAttentionTask(task, data.summary.stale_task_ids))
    .slice(0, limit);
}
