const PR_RE = /^pr\/([^/]+)\/([^/]+)\/([0-9]+)\/(write|review\/([^@/]+))@([A-Za-z0-9._+-]+)$/;
const REPO_KIND_RE = /^(branch|base|repo-common-dir|agy-scratch|repo)\/([^/]+)\/([^/]+)(?:\/(.*))?$/;
const PATH_RE = /^path\/([^/]+)\/([^/]+)\/([^/]+)(?:\/(.*))?$/;

function normalizePosix(value, { absolute = false } = {}) {
  const parts = String(value).split("/");
  const result = [];
  for (const part of parts) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (result.length && result.at(-1) !== "..") result.pop();
      else if (!absolute) result.push(part);
    } else {
      result.push(part);
    }
  }
  const joined = result.join("/");
  if (absolute) return `/${joined}` || "/";
  return joined || ".";
}

export function normalizeResourceKey(value) {
  let key = String(value || "").trim().replace(/\/+$/, "");
  if (key.startsWith("worktree/")) {
    const rawPath = key.slice("worktree/".length) || "/";
    return `worktree/${normalizePosix(rawPath, { absolute: rawPath.startsWith("/") })}`;
  }
  const pr = key.match(PR_RE);
  if (pr) {
    const kind = pr[5] ? `review/${pr[5]}` : "write";
    return `pr/${pr[1].toLowerCase()}/${pr[2].toLowerCase()}/${pr[3]}/${kind}@${pr[6]}`;
  }
  if (key.startsWith("path/")) {
    const match = key.match(PATH_RE);
    if (match) {
      const prefix = normalizePosix(`/${match[4] || ""}`, { absolute: true }).replace(/^\/+/, "");
      return `path/${match[1].toLowerCase()}/${match[2].toLowerCase()}/${match[3]}/${prefix}`.replace(/\/+$/, "");
    }
  }
  const repo = key.match(REPO_KIND_RE);
  if (repo) {
    const suffix = repo[4] ? `/${repo[4]}` : "";
    return `${repo[1]}/${repo[2].toLowerCase()}/${repo[3].toLowerCase()}${suffix}`;
  }
  return key;
}

export function parseResource(value) {
  const raw = normalizeResourceKey(value);
  if (raw.startsWith("task/")) return { raw, kind: "task", identity: [raw.slice(5)] };
  if (raw.startsWith("external/")) return { raw, kind: "external", identity: [raw.slice(9)] };
  if (raw.startsWith("worktree/")) return { raw, kind: "worktree", identity: [raw.slice(9)] };
  const pr = raw.match(PR_RE);
  if (pr) {
    const repo = `${pr[1]}/${pr[2]}`;
    const provider = pr[5] || "";
    return {
      raw,
      kind: provider ? "pr-review" : "pr-write",
      repo,
      identity: [repo, pr[3], provider],
    };
  }
  const path = raw.match(PATH_RE);
  if (path) {
    const repo = `${path[1]}/${path[2]}`;
    return {
      raw,
      kind: "path",
      repo,
      identity: [repo, path[3]],
      prefix: normalizePosix(`/${path[4] || ""}`, { absolute: true }),
    };
  }
  const repoMatch = raw.match(REPO_KIND_RE);
  if (repoMatch) {
    const repo = `${repoMatch[2]}/${repoMatch[3]}`;
    let kind = repoMatch[1];
    let rest = repoMatch[4] || "";
    if (kind === "base" && rest.endsWith("/integrate")) {
      rest = rest.slice(0, -"/integrate".length);
      kind = "base-integrate";
    } else if (kind === "repo-common-dir" && rest === "plumbing") {
      kind = "repo-plumbing";
    } else if (kind === "repo" && rest === "write") {
      kind = "repo-write";
    }
    return { raw, kind, repo, identity: [repo, rest] };
  }
  return { raw, kind: "opaque", identity: [raw] };
}

function prefixesOverlap(left, right) {
  const a = normalizePosix(left, { absolute: true });
  const b = normalizePosix(right, { absolute: true });
  return a === b || a.startsWith(`${b.replace(/\/+$/, "")}/`) || b.startsWith(`${a.replace(/\/+$/, "")}/`);
}

function sameIdentity(left, right, length = null) {
  const a = length === null ? left : left.slice(0, length);
  const b = length === null ? right : right.slice(0, length);
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function repoWideMatches(repo, other) {
  return repo === "*/*" || repo === other;
}

export function resourcesOverlap(left, right) {
  const a = parseResource(left.key);
  const b = parseResource(right.key);
  if (a.kind === "pr-review" && b.kind === "pr-review" && sameIdentity(a.identity, b.identity)) {
    return true;
  }
  if (left.mode === "shared" && right.mode === "shared" && a.kind === "path" && b.kind === "path") {
    return false;
  }
  if (a.raw === b.raw) return true;
  if (a.kind === "repo-write" && repoWideMatches(a.repo, b.repo)) return b.kind !== "pr-review";
  if (b.kind === "repo-write" && repoWideMatches(b.repo, a.repo)) return a.kind !== "pr-review";
  if (a.kind === "pr-write" && b.kind === "pr-write") return sameIdentity(a.identity, b.identity, 2);
  if (a.kind === "pr-review" || b.kind === "pr-review") {
    return a.kind === b.kind && sameIdentity(a.identity, b.identity);
  }
  if (a.kind === "path" && b.kind === "path") {
    return sameIdentity(a.identity, b.identity) && Boolean(a.prefix && b.prefix && prefixesOverlap(a.prefix, b.prefix));
  }
  if (a.kind === "branch" && b.kind === "branch") return sameIdentity(a.identity, b.identity);
  if (new Set([a.kind, b.kind]).size === 2 && [a.kind, b.kind].includes("branch") && [a.kind, b.kind].includes("path") && a.repo === b.repo) {
    const branch = a.kind === "branch" ? a : b;
    const path = a.kind === "path" ? a : b;
    return Boolean(branch.identity[1] && branch.identity[1] === path.identity[1]);
  }
  if (a.kind === "worktree" && b.kind === "worktree") return sameIdentity(a.identity, b.identity);
  if (a.kind === b.kind && ["task", "external", "repo-plumbing", "base-integrate", "agy-scratch", "opaque"].includes(a.kind)) {
    return sameIdentity(a.identity, b.identity);
  }
  return false;
}

export function conflictingKeys(requested, held) {
  const pairs = new Set();
  for (const left of requested) {
    for (const right of held) {
      if (resourcesOverlap(left, right)) {
        pairs.add(JSON.stringify([normalizeResourceKey(left.key), normalizeResourceKey(right.key)]));
      }
    }
  }
  return [...pairs].map((pair) => JSON.parse(pair)).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
}

export function sortedClaims(claims) {
  const deduplicated = new Map();
  for (const claim of claims) {
    const key = normalizeResourceKey(claim.key);
    const current = deduplicated.get(key);
    const mode = claim.mode === "exclusive" || current?.mode === "exclusive" ? "exclusive" : "shared";
    deduplicated.set(key, {
      schema_version: "limen.resource_claim.v1",
      key,
      mode,
    });
  }
  return [...deduplicated.keys()].sort().map((key) => deduplicated.get(key));
}
