const FIELD_ORDER = [
  "source_origin",
  "horizon",
  "value_case",
  "budget_cost",
  "owner_surface",
  "predicate",
  "receipt_target",
  "due_at",
];
const EXECUTABLES = new Set([
  "[", "bash", "bundle", "cargo", "curl", "gh", "git", "go", "just", "limen", "make", "node", "nox", "npm",
  "pnpm", "py.test", "pytest", "python", "python3", "ruby", "sh", "test", "tox", "uv", "yarn", "zsh",
]);
const ORIGINS = new Map([
  ["ask", "human_prompt"], ["human", "human_prompt"], ["human_ask", "human_prompt"],
  ["prompt", "human_prompt"], ["human_prompt", "human_prompt"],
  ["due", "obligation"], ["external", "obligation"], ["obligation", "obligation"],
  ["agent", "agent_recommendation"], ["agent_recommendation", "agent_recommendation"],
  ["recommendation", "agent_recommendation"], ["system", "system_debt"], ["debt", "system_debt"],
  ["system_debt", "system_debt"],
]);
const HORIZONS = new Map([
  ["past", "past"], ["recovery", "past"], ["present", "present"], ["now", "present"],
  ["current", "present"], ["next", "future"], ["future", "future"], ["later", "future"],
]);
const CANONICAL_ORIGINS = new Set(["obligation", "human_prompt", "agent_recommendation", "system_debt"]);
const CANONICAL_HORIZONS = new Set(["past", "present", "future"]);
const PLACEHOLDER_RE = /(?:<[^>]+>|\b(?:tbd|todo|fixme|replace[-_ ]me)\b)/i;
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATETIME_RE = /^(\d{4})-(\d{2})-(\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;

function slug(value) {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function fieldOrLabel(task, fields, prefixes) {
  for (const field of fields) {
    if (task?.[field] != null && String(task[field]).trim()) return String(task[field]).trim();
  }
  for (const label of task?.labels || []) {
    const normalized = String(label).trim().toLowerCase();
    for (const prefix of prefixes) {
      const marker = `${prefix}:`;
      if (normalized.startsWith(marker) && normalized.slice(marker.length).trim()) {
        return normalized.slice(marker.length).trim();
      }
    }
  }
  return null;
}

export function executablePredicate(value) {
  if (typeof value !== "string" || !value.trim() || /[\r\n\0]/.test(value) || PLACEHOLDER_RE.test(value)) return false;
  const tokens = shellSplit(value.trim());
  if (!tokens) return false;
  let index = 0;
  while (index < tokens.length && (
    ["command", "env", "sudo"].includes(tokens[index])
    || (tokens[index].includes("=") && !["/", "./", "../"].some((prefix) => tokens[index].startsWith(prefix)))
    || tokens[index].startsWith("-")
  )) index += 1;
  if (index >= tokens.length) return false;
  const first = tokens[index].replace(/^['"]|['"]$/g, "");
  return EXECUTABLES.has(first) || first.includes("/") || first.endsWith(".py") || first.endsWith(".sh");
}

export function durableReceiptTarget(value) {
  if (typeof value !== "string" || !value.trim() || /[\s\0]/.test(value) || PLACEHOLDER_RE.test(value)) return false;
  if (/^github:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+:(pull-request|issue):[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(value)) {
    return true;
  }
  const gitTarget = /^git:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+:([^\s#]+)(?:#[^\s]+)?$/.exec(value);
  if (gitTarget) {
    const path = gitTarget[1];
    return !path.startsWith("/") && path.split("/").every((part) => !["", ".", "..", ".git"].includes(part));
  }
  return /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/(?:issues|pull|actions\/(?:runs|workflows)|commit|blob|tree)\/[A-Za-z0-9][^\s?#]*$/.test(value);
}

function ordered(fields) {
  return FIELD_ORDER.filter((field) => fields.has(field));
}

function boundedText(value) {
  return typeof value === "string" && Boolean(value.trim()) && !value.includes("\0") && value.length <= 8192;
}

function shellSplit(command) {
  const tokens = [];
  let token = "";
  let quote = null;
  let escaped = false;
  let started = false;
  for (const char of command) {
    if (escaped) {
      token += char;
      escaped = false;
      started = true;
      continue;
    }
    if (char === "\\" && quote !== "'") {
      escaped = true;
      started = true;
      continue;
    }
    if (quote) {
      if (char === quote) quote = null;
      else token += char;
      started = true;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      started = true;
      continue;
    }
    if (/\s/.test(char)) {
      if (started) {
        tokens.push(token);
        token = "";
        started = false;
      }
      continue;
    }
    token += char;
    started = true;
  }
  if (escaped || quote) return null;
  if (started) tokens.push(token);
  return tokens;
}

function validCalendarDate(year, month, day) {
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31) return false;
  const probe = new Date(Date.UTC(year, month - 1, day));
  return probe.getUTCFullYear() === year && probe.getUTCMonth() === month - 1 && probe.getUTCDate() === day;
}

function validDueAt(value) {
  if (typeof value !== "string") return false;
  const text = value.trim();
  const dateMatch = DATE_RE.exec(text);
  if (dateMatch) return validCalendarDate(Number(dateMatch[1]), Number(dateMatch[2]), Number(dateMatch[3]));
  const datetimeMatch = DATETIME_RE.exec(text);
  if (!datetimeMatch) return false;
  return validCalendarDate(Number(datetimeMatch[1]), Number(datetimeMatch[2]), Number(datetimeMatch[3]))
    && !Number.isNaN(Date.parse(text));
}

function exactSingleton(values, expected) {
  const selected = new Set(values || []);
  return selected.size === 1 && selected.has(expected);
}

export function packetIsNonCapacityProjection(packet) {
  const taskId = packet?.task_id;
  const kind = packet?.intent?.kind;
  const claim = packet?.resource_claims?.[0];
  const receipt = String(packet?.receipt_target || "");
  const escapedTaskId = String(taskId || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return Boolean(
    packet?.execution?.adapter === "tabularius"
    && packet?.execution?.projection === "tasks.yaml"
    && ["task.upsert", "task.status", "task.claim", "task.mutate"].includes(kind)
    && taskId
    && packet?.intent?.task_id === taskId
    && packet?.preferred_agent === "tabularius"
    && exactSingleton(packet?.required_capabilities, "board-write")
    && packet?.resource_claims?.length === 1
    && claim?.key === `task/${taskId}`
    && claim?.mode === "exclusive"
    && packet?.predicate === "python3 scripts/validate-task-board.py --tasks tasks.yaml"
    && new RegExp(`^git:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:tasks\\.yaml#${escapedTaskId}$`).test(receipt)
    && exactSingleton(packet?.authority?.actions, kind)
    && exactSingleton(packet?.authority?.path_prefixes, "tasks.yaml")
    && (packet?.authority?.external_effects || []).length === 0
    && packet?.authority?.may_delegate === false
    && packet?.effect === "write"
    && (packet?.spend?.unit || "runs") === "runs"
    && packet?.spend?.limit === 0
    && (packet?.spend?.reserve || 0) === 0
  );
}

export function packetWorkLoanMissingFields(packet) {
  if (packetIsNonCapacityProjection(packet)) return [];
  const loan = packet.work_loan;
  const missing = new Set();
  if (!loan) {
    for (const field of ["source_origin", "horizon", "value_case", "budget_cost", "owner_surface"]) missing.add(field);
  } else {
    for (const field of ["value_case", "owner_surface"]) {
      if (!boundedText(loan[field])) missing.add(field);
    }
    if (!CANONICAL_ORIGINS.has(loan.source_origin)) missing.add("source_origin");
    if (!CANONICAL_HORIZONS.has(loan.horizon)) missing.add("horizon");
    if (!Number.isInteger(loan.budget_cost) || loan.budget_cost <= 0 || loan.budget_cost !== packet.spend.limit) {
      missing.add("budget_cost");
    }
    if (loan.external_deadline && !validDueAt(loan.due_at)) missing.add("due_at");
  }
  if (!executablePredicate(packet.predicate)) missing.add("predicate");
  if (!durableReceiptTarget(packet.receipt_target)) missing.add("receipt_target");
  return ordered(missing);
}

export function taskWorkLoanMissingFields(task) {
  const missing = new Set();
  const origin = ORIGINS.get(slug(fieldOrLabel(
    task,
    ["source_origin", "intent_origin", "work_origin", "origin"],
    ["origin", "intent-origin", "work-origin"],
  )));
  const horizon = HORIZONS.get(slug(fieldOrLabel(
    task,
    ["time_horizon", "horizon"],
    ["horizon", "time-horizon"],
  )));
  const valueCase = fieldOrLabel(task, ["value_case", "expected_value", "work_credit"], ["value", "value-case", "work-credit"]);
  const owner = fieldOrLabel(task, ["owner_surface", "work_owner"], ["owner-surface", "work-owner"])
    || String(task?.repo || "").trim();
  if (!origin) missing.add("source_origin");
  if (!horizon) missing.add("horizon");
  if (!boundedText(valueCase)) missing.add("value_case");
  if (!Number.isInteger(task?.budget_cost) || task.budget_cost <= 0) missing.add("budget_cost");
  if (!boundedText(owner)) missing.add("owner_surface");
  if (!executablePredicate(task?.predicate)) missing.add("predicate");
  if (!durableReceiptTarget(task?.receipt_target)) missing.add("receipt_target");
  const external = task?.external_deadline === true
    || ["1", "true", "yes"].includes(String(task?.external_deadline || "").trim().toLowerCase());
  const dueAt = fieldOrLabel(task, ["due_at", "due_on", "due_date", "deadline"], ["due", "due-at", "due-on", "deadline"]);
  if (external && !validDueAt(dueAt)) missing.add("due_at");
  return ordered(missing);
}

export function workLoanDenial(fields) {
  return `task-not-underwritten:${ordered(new Set(fields)).join(",")}`;
}
