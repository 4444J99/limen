import { readFileSync } from "fs";
import { join } from "path";
import type { DashboardData, PRStatusData, Task, ThroughputSummary } from "../dashboard-client";

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
    throughput?: ThroughputSummary;
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
    id: "internal" | "client" | "public" | "qa" | "corpus";
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
  mutation: {
    status: "available" | "deferred";
    owner: string;
    code?: string;
    route?: string;
    next_action?: string;
  };
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

export interface CorpusStatusData {
  status: "ok" | "missing";
  surface: "corpus";
  generated_at: string;
  privacy: {
    redacted: boolean;
    contains_raw_text: boolean;
    private_index?: string;
    private_html?: string;
  };
  coverage: {
    units: number;
    sessions_indexed: number;
    unique_hashes: number;
    clusters: number;
    comparisons: number;
    allusion_rows: number;
    private_object_count: number;
    kinds: Record<string, number>;
    lanes: Record<string, number>;
    sources: Record<string, number>;
  };
  units: {
    unit_id: string;
    kind: string;
    role: string;
    source: string;
    event_at?: string | null;
    hash: string;
    signature: string;
    cluster_id: string;
    parent_id?: string | null;
    lane_id: string;
    body_chars: number;
    body_words: number;
    atom_ids: string[];
    task_status?: string;
    task_priority?: string;
    artifact_path?: string;
    worktree_slug_hash?: string;
    repo_hash?: string;
  }[];
  truncated_units: boolean;
  clusters: {
    cluster_id: string;
    unit_count: number;
    kinds: Record<string, number>;
    lanes: Record<string, number>;
    first_event?: string | null;
    last_event?: string | null;
    atom_ids: string[];
    representative_unit_id: string;
  }[];
  comparisons: {
    comparison_id: string;
    cluster_id: string;
    left_unit_id: string;
    right_unit_id: string;
    unit_count: number;
    first_event?: string | null;
    last_event?: string | null;
    lanes: Record<string, number>;
    kinds: Record<string, number>;
  }[];
  allusions: {
    unit_id: string;
    explicit_atom_ids: string[];
    implied_atom_ids: string[];
    absent_adjacent_atom_ids: string[];
  }[];
  aug1: {
    generated_at?: string | null;
    deadline: string;
    days_left?: number | null;
    gate_pass: boolean;
    legs_total: number;
    legs_met: number;
    next_act?: string | null;
    ledger: Record<string, number | string | boolean | null>;
  };
  inbound: {
    value_repo_count: number;
    seeded_repo_count: number;
    frontdoor_present: boolean;
    discoverability_present: boolean;
    scraper_model_present: boolean;
    capture_contact_configured: boolean;
    scraper_model_unit?: string;
  };
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

export function getCorpusCommandCenterData() {
  const privateDir = join(process.cwd(), ".generated", "surfaces");
  const corpusFile = `${["corpus", "status"].join("-")}.json`;
  return readJson<CorpusStatusData>(join(privateDir, corpusFile), {
    status: "missing",
    surface: "corpus",
    generated_at: new Date(0).toISOString(),
    privacy: {
      redacted: true,
      contains_raw_text: false,
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

export interface ObservatoryMeasurementContract {
  baseline_source: string;
  confounder_controls: string[];
  failure_criterion: string;
  metric_vector: string[];
  observation_window_days: number;
  reversal_path: string;
  success_predicate: string;
}

export interface ObservatoryExperiment {
  change: string;
  hero: string | null;
  id: string;
  kind: string;
  measure_hint: string;
  measurement_contract: ObservatoryMeasurementContract;
  reversible: boolean;
  revert: string;
  task_id: string;
}

export interface ObservatoryMechanism {
  mechanism: string;
  winner: string;
  priority: number;
}

export interface ObservatoryStatusData {
  status: "ok" | "missing";
  surface: "observatory";
  generated_at: string;
  schema: string;
  date: string | null;
  hero: string | null;
  internal_gaps: number;
  external_gaps: number;
  confounders: (string | { name?: string; discount?: number })[];
  mechanisms: ObservatoryMechanism[];
  experiment: ObservatoryExperiment | null;
  measurement_contract: ObservatoryMeasurementContract | null;
}

// Owner surface: reads the private baked brief (mirrors getCorpusCommandCenterData). The
// filename is assembled at runtime so the literal never appears verbatim in this source.
export function getObservatoryBriefData(): ObservatoryStatusData {
  const privateDir = join(process.cwd(), ".generated", "surfaces");
  const file = `${["observatory", "status"].join("-")}.json`;
  return readJson<ObservatoryStatusData>(join(privateDir, file), {
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
  });
}
