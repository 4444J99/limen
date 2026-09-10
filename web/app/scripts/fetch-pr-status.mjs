#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { execFileSync } from "child_process";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";

const THIS_FILE = fileURLToPath(import.meta.url);
const __dirname = dirname(THIS_FILE);
const REPO_ROOT = join(__dirname, "..", "..", "..");
const PUBLIC_OUT_PATH = join(__dirname, "..", "public", "pr-status.json");
const PRIVATE_OUT_PATH = join(__dirname, "..", ".generated", "surfaces", "pr-status.json");
const ISSUE_PUBLIC_OUT_PATH = join(__dirname, "..", "public", "issue-status.json");
const ISSUE_PRIVATE_OUT_PATH = join(__dirname, "..", ".generated", "surfaces", "issue-status.json");
const HEALTH_PUBLIC_OUT_PATH = join(__dirname, "..", "public", "repo-health.json");
const HEALTH_PRIVATE_OUT_PATH = join(__dirname, "..", ".generated", "surfaces", "repo-health.json");
const REQUEST_TIMEOUT_MS = Number(process.env.LIMEN_PR_STATUS_REQUEST_TIMEOUT_MS || 15_000);
const TOPIC_BRANCH_PREFIXES = [
  "feat/",
  "fix/",
  "heal/",
  "chore/",
  "docs/",
  "refactor/",
  "work/",
  "copilot/",
  "codex/",
  "dependabot/",
  "security/",
  "corrective/",
  "recovery/",
  "capture/",
];

function resolveGitHubToken() {
  if (process.env.GITHUB_TOKEN || process.env.GH_TOKEN) return process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
  try {
    return execFileSync("gh", ["auth", "token"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

function parseGitHubRepo(remoteUrl) {
  const normalized = (remoteUrl || "").trim();
  const match = normalized.match(/github\.com[:/]([^/]+\/[^/.]+?)(?:\.git)?$/i);
  return match?.[1] || "";
}

export function resolveDefaultRepo(env = process.env) {
  if (env.LIMEN_GITHUB_REPO) return env.LIMEN_GITHUB_REPO.trim();
  if (env.GITHUB_REPOSITORY) return env.GITHUB_REPOSITORY.trim();
  try {
    return parseGitHubRepo(execFileSync("git", ["-C", REPO_ROOT, "remote", "get-url", "origin"], { encoding: "utf8" }));
  } catch {
    return "";
  }
}

export function resolveRepos(env = process.env) {
  const configured = env.LIMEN_PR_STATUS_REPOS || resolveDefaultRepo(env);
  return [...new Set((configured || "").split(",").map((value) => value.trim()).filter(Boolean))];
}

function previousPayload(path) {
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : null;
}

function githubHeaders(githubToken) {
  const headers = { Accept: "application/vnd.github.v3+json" };
  if (githubToken) headers.Authorization = "Bearer " + githubToken;
  return headers;
}

function previousRepo(previous, repo) {
  return previous?.repos?.find((item) => item.repo === repo) || null;
}

function sameRepo(left, right) {
  return (left || "").trim().toLowerCase() === (right || "").trim().toLowerCase();
}

function nextLink(linkHeader) {
  const match = /<([^>]+)>;\s*rel="next"/.exec(linkHeader || "");
  return match?.[1] || null;
}

async function fetchJson(url, label, githubToken) {
  let res;
  try {
    res = await fetch(url, { headers: githubHeaders(githubToken), signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  } catch (error) {
    console.error(`Failed to fetch ${label}: ${error instanceof Error ? error.message : "network error"}`);
    return null;
  }
  if (!res.ok) {
    console.error(`Failed to fetch ${label}: ${res.status}`);
    return null;
  }
  return res;
}

async function fetchPaginatedArray(url, label, githubToken, pageLimit = 10) {
  const rows = [];
  let next = url;
  for (let page = 0; next && page < pageLimit; page += 1) {
    const res = await fetchJson(next, label, githubToken);
    if (!res) return null;
    const payload = await res.json();
    if (!Array.isArray(payload)) return null;
    rows.push(...payload);
    next = nextLink(res.headers.get("link"));
  }
  if (next) {
    console.error(`Failed to fetch ${label}: exceeded ${pageLimit} pages`);
    return null;
  }
  return rows;
}

async function fetchPRs(repo, githubToken) {
  const prs = await fetchPaginatedArray(`https://api.github.com/repos/${repo}/pulls?state=open&per_page=100`, `PRs for ${repo}`, githubToken);
  if (prs === null) return null;

  return prs.map((pr) => ({
    number: pr.number,
    title: pr.title,
    author: pr.user.login,
    created_at: pr.created_at,
    updated_at: pr.updated_at,
    draft: pr.draft,
    mergeable_state: pr.mergeable_state,
    html_url: pr.html_url,
    head: pr.head.ref,
    head_sha: pr.head.sha,
    base: pr.base.ref,
    head_repo: pr.head.repo?.full_name || null,
    labels: pr.labels.map((label) => label.name),
  }));
}

async function fetchCheckRuns(repo, headSha, githubToken) {
  const res = await fetchJson(
    `https://api.github.com/repos/${repo}/commits/${headSha}/check-runs?per_page=10`,
    `check runs for ${repo}@${headSha}`,
    githubToken
  );
  if (!res) return null;
  const data = await res.json();
  const runs = data.check_runs || [];
  const failed = runs.filter((run) => run.conclusion === "failure").length;
  const passed = runs.filter((run) => run.conclusion === "success").length;
  const pending = runs.filter((run) => run.status === "in_progress" || run.status === "queued").length;
  return { total: runs.length, failed, passed, pending };
}

async function fetchIssueCount(repo, githubToken) {
  const query = encodeURIComponent(`repo:${repo} is:issue is:open -is:pr`);
  const res = await fetchJson(`https://api.github.com/search/issues?q=${query}&per_page=1`, `open issues for ${repo}`, githubToken);
  if (!res) return null;
  const payload = await res.json();
  return Number.isFinite(payload?.total_count) ? payload.total_count : null;
}

async function fetchIssues(repo, githubToken) {
  const issues = await fetchPaginatedArray(
    `https://api.github.com/repos/${repo}/issues?state=open&per_page=100`,
    `issues for ${repo}`,
    githubToken
  );
  if (issues === null) return null;
  return issues.filter((issue) => !issue.pull_request).map((issue) => ({
    number: issue.number,
    title: issue.title,
    created_at: issue.created_at,
    updated_at: issue.updated_at,
    labels: issue.labels.map((label) => label.name),
    assignees: issue.assignees.map((assignee) => assignee.login),
  }));
}

async function fetchWorkflowRuns(repo, githubToken) {
  const res = await fetchJson(
    `https://api.github.com/repos/${repo}/actions/runs?per_page=100`,
    `workflow runs for ${repo}`,
    githubToken
  );
  if (!res) return null;
  const payload = await res.json();
  return Array.isArray(payload.workflow_runs) ? payload.workflow_runs : null;
}

// Canonical task priority vocabulary (mcp/src/limen_mcp/server.py:31). p0-p3 are
// accepted as aliases from label conventions but always mapped to these buckets so
// issue priority counts are comparable with the existing triage priorities.
const CANONICAL_PRIORITIES = ["critical", "high", "medium", "low", "backlog"];
const PRIORITY_ALIASES = { p0: "critical", p1: "high", p2: "medium", p3: "low" };

function issuePriority(labels) {
  const normalized = labels.map((label) => label.toLowerCase());
  const canonical = normalized.find((label) => CANONICAL_PRIORITIES.includes(label));
  if (canonical) return canonical;
  const aliased = normalized.find((label) => PRIORITY_ALIASES[label]);
  if (aliased) return PRIORITY_ALIASES[aliased];
  return "unprioritized";
}

function classifyIssues(issues, now = Date.now()) {
  const staleCutoff = now - 30 * 24 * 60 * 60 * 1000;
  const summary = {
    total_open_issues: issues.length,
    unlabeled_issues: issues.filter((issue) => issue.labels.length === 0).length,
    unassigned_issues: issues.filter((issue) => issue.assignees.length === 0).length,
    stale_issues: issues.filter((issue) => Date.parse(issue.updated_at) < staleCutoff).length,
    ready_to_triage: issues.filter((issue) => issue.labels.length === 0 || issue.assignees.length === 0).length,
    priority_counts: {},
  };
  for (const issue of issues) {
    const priority = issuePriority(issue.labels);
    summary.priority_counts[priority] = (summary.priority_counts[priority] || 0) + 1;
  }
  return summary;
}

function latestRunPerWorkflow(runs) {
  const latest = new Map();
  for (const run of runs) {
    const key = run.workflow_id;
    const existing = latest.get(key);
    if (!existing || Date.parse(run.created_at) > Date.parse(existing.created_at)) {
      latest.set(key, run);
    }
  }
  return Array.from(latest.values());
}

function classifyHealth(runs) {
  // Only the latest run per workflow reflects current health; counting every
  // historical run would report workflows as failing long after they recovered.
  const latestRuns = latestRunPerWorkflow(runs);
  const failing_workflows = latestRuns.filter((run) => run.conclusion === "failure").length;
  const in_progress_runs = runs.filter((run) =>
    ["queued", "in_progress", "waiting", "requested", "pending"].includes(run.status)
  ).length;
  return {
    failing_workflows,
    in_progress_runs,
    degraded: failing_workflows > 0 || in_progress_runs > 0,
  };
}

async function fetchRepoMeta(repo, githubToken) {
  const res = await fetchJson(`https://api.github.com/repos/${repo}`, `repo metadata for ${repo}`, githubToken);
  if (!res) return null;
  const payload = await res.json();
  return {
    default_branch: typeof payload?.default_branch === "string" && payload.default_branch ? payload.default_branch : "main",
  };
}

async function fetchBranches(repo, githubToken) {
  const branches = await fetchPaginatedArray(`https://api.github.com/repos/${repo}/branches?per_page=100`, `branches for ${repo}`, githubToken);
  if (branches === null) return null;
  return branches.map((branch) => ({
    name: branch.name,
    protected: Boolean(branch.protected),
  }));
}

function activeWorkBranches(branches, defaultBranch) {
  return branches.filter(
    (branch) =>
      branch.name !== defaultBranch &&
      !branch.protected &&
      TOPIC_BRANCH_PREFIXES.some((prefix) => branch.name.startsWith(prefix))
  );
}

function summaryIsCurrent(summary) {
  return [
    "total_repos",
    "total_open_prs",
    "prs_with_failing_ci",
    "total_open_issues",
    "total_active_work_branches",
    "work_branches_without_open_pr",
  ].every((key) => Number.isFinite(summary?.[key]));
}

export function buildOutputs(results, totalRepos, generatedAt = new Date().toISOString()) {
  const totalPRs = results.reduce((sum, repo) => sum + repo.count, 0);
  const totalFailed = results.reduce((sum, repo) => sum + repo.prs.filter((pr) => pr.checks?.failed > 0).length, 0);
  const totalIssues = results.reduce((sum, repo) => sum + (repo.issue_count || 0), 0);
  const totalBranches = results.reduce((sum, repo) => sum + (repo.active_work_branches || 0), 0);
  const branchesWithoutOpenPr = results.reduce((sum, repo) => sum + (repo.work_branches_without_open_pr || 0), 0);
  const summary = {
    total_repos: totalRepos,
    total_open_prs: totalPRs,
    prs_with_failing_ci: totalFailed,
    total_open_issues: totalIssues,
    total_active_work_branches: totalBranches,
    work_branches_without_open_pr: branchesWithoutOpenPr,
  };
  return {
    publicOutput: { generated_at: generatedAt, repos: [], summary },
    privateOutput: { generated_at: generatedAt, repos: results, summary },
  };
}

export async function collectRepoStatuses(repos, previous, githubToken = resolveGitHubToken()) {
  const results = [];
  for (const repo of repos) {
    const fallback = previousRepo(previous, repo);
    const fallbackPrsByNumber = new Map((fallback?.prs || []).map((pr) => [pr.number, pr]));
    const [prs, issueCount, repoMeta, branches, issues, workflowRuns] = await Promise.all([
      fetchPRs(repo, githubToken),
      fetchIssueCount(repo, githubToken),
      fetchRepoMeta(repo, githubToken),
      fetchBranches(repo, githubToken),
      fetchIssues(repo, githubToken),
      fetchWorkflowRuns(repo, githubToken),
    ]);
    const effectivePrs = [];
    for (const pr of prs || []) {
      const checks = await fetchCheckRuns(repo, pr.head_sha, githubToken);
      effectivePrs.push({ ...pr, checks: checks ?? fallbackPrsByNumber.get(pr.number)?.checks ?? null });
    }
    const mergedPrs = prs === null ? (fallback?.prs || []) : effectivePrs;
    const mergedDefaultBranch = repoMeta?.default_branch || fallback?.default_branch || "main";
    let activeWorkBranchCount = fallback?.active_work_branches || 0;
    let workBranchesWithoutOpenPrCount = fallback?.work_branches_without_open_pr || 0;
    if (branches !== null && mergedDefaultBranch) {
      const workBranches = activeWorkBranches(branches, mergedDefaultBranch);
      const branchesWithOpenPr = new Set(
        mergedPrs
          .filter((pr) => sameRepo(pr.head_repo || repo, repo))
          .map((pr) => pr.head)
      );
      const workBranchesWithoutOpenPr = workBranches.filter((branch) => !branchesWithOpenPr.has(branch.name));
      activeWorkBranchCount = workBranches.length;
      workBranchesWithoutOpenPrCount = workBranchesWithoutOpenPr.length;
    }
    const stale = prs === null || issueCount === null || repoMeta === null || branches === null;
    const result = {
      repo,
      default_branch: mergedDefaultBranch,
      prs: mergedPrs,
      count: mergedPrs.length,
      issue_count: issueCount ?? fallback?.issue_count ?? 0,
      active_work_branches: activeWorkBranchCount,
      work_branches_without_open_pr: workBranchesWithoutOpenPrCount,
      ...(stale ? { stale: true, error: "fetch_failed" } : {}),
    };
    // Fail closed: a transient fetch failure must never publish false healthy data.
    // Reuse the cached domain when available; only fall back to an empty array (and
    // flag it) when there is truly nothing cached to preserve.
    const issuesStale = issues === null && !fallback?.issues;
    const healthStale = workflowRuns === null && !fallback?.workflow_runs;
    result.issues = issues ?? fallback?.issues ?? [];
    result.issue_summary = { ...classifyIssues(result.issues), ...(issuesStale ? { stale: true } : {}) };
    result.workflow_health = { ...classifyHealth(workflowRuns ?? fallback?.workflow_runs ?? []), ...(healthStale ? { stale: true } : {}) };
    result.workflow_runs = workflowRuns ?? fallback?.workflow_runs ?? [];
    results.push(result);
    console.log(
      `  ${repo}: ${result.count} open PRs, ${result.issue_count} open issues, ${result.active_work_branches} active work branches`
    );
  }
    return results;
}

export function buildMonitoringOutputs(results, totalRepos, generatedAt = new Date().toISOString()) {
    const issueSummaries = results.map((repo) => ({
      repo: repo.repo,
      ...repo.issue_summary,
      issues: repo.issues,
    }));
    const issueSummary = issueSummaries.reduce(
      (summary, repo) => ({
        total_open_issues: summary.total_open_issues + repo.total_open_issues,
        unlabeled_issues: summary.unlabeled_issues + repo.unlabeled_issues,
        unassigned_issues: summary.unassigned_issues + repo.unassigned_issues,
        stale_issues: summary.stale_issues + repo.stale_issues,
        ready_to_triage: summary.ready_to_triage + repo.ready_to_triage,
        priority_counts: Object.entries(repo.priority_counts).reduce(
          (counts, [priority, count]) => ({ ...counts, [priority]: (counts[priority] || 0) + count }),
          summary.priority_counts
        ),
        stale_repos: summary.stale_repos + (repo.stale ? 1 : 0),
      }),
      { total_open_issues: 0, unlabeled_issues: 0, unassigned_issues: 0, stale_issues: 0, ready_to_triage: 0, priority_counts: {}, stale_repos: 0 }
    );
    const healthRepos = results.map((repo) => ({ repo: repo.repo, ...repo.workflow_health, runs: repo.workflow_runs }));
    const healthSummary = healthRepos.reduce(
      (summary, repo) => ({
        degraded_repos: summary.degraded_repos + (repo.degraded ? 1 : 0),
        failing_workflows: summary.failing_workflows + repo.failing_workflows,
        in_progress_runs: summary.in_progress_runs + repo.in_progress_runs,
        stale_repos: summary.stale_repos + (repo.stale ? 1 : 0),
      }),
      { degraded_repos: 0, failing_workflows: 0, in_progress_runs: 0, stale_repos: 0 }
    );
    return {
      issuePublicOutput: { generated_at: generatedAt, repos: [], summary: { total_repos: totalRepos, ...issueSummary } },
      issuePrivateOutput: { generated_at: generatedAt, repos: issueSummaries, summary: { total_repos: totalRepos, ...issueSummary } },
      healthPublicOutput: {
        generated_at: generatedAt,
        repos: [],
        summary: {
          total_repos: totalRepos,
          ...healthSummary,
          healthy_repos: totalRepos - healthSummary.degraded_repos,
        },
      },
      healthPrivateOutput: {
        generated_at: generatedAt,
        repos: healthRepos,
        summary: {
          total_repos: totalRepos,
          ...healthSummary,
          healthy_repos: totalRepos - healthSummary.degraded_repos,
        },
      },
    };
}

export async function main() {
  const previousPublic = previousPayload(PUBLIC_OUT_PATH);
  const previousPrivate = previousPayload(PRIVATE_OUT_PATH);
  const previous = previousPrivate || previousPublic;
  const ttlMin = Number(process.env.LIMEN_PR_STATUS_TTL_MIN || 30);
  const previousGeneratedAt = previousPrivate?.generated_at || previousPublic?.generated_at;
  if (previousGeneratedAt) {
    const ageMin = (Date.now() - new Date(previousGeneratedAt).getTime()) / 60000;
    const privateCurrent = previousPrivate?.generated_at === previousGeneratedAt && summaryIsCurrent(previousPrivate?.summary);
    // The issue/repo-health feeds must also exist and be current, or a rollout / a
    // previously-missing artifact would keep them unavailable indefinitely even
    // though the pr-status cache alone looks fresh.
    const monitoringArtifactsCurrent = [ISSUE_PRIVATE_OUT_PATH, HEALTH_PRIVATE_OUT_PATH].every((path) => {
      const payload = previousPayload(path);
      return payload?.generated_at === previousGeneratedAt;
    });
    if (
      Number.isFinite(ageMin) &&
      ageMin < ttlMin &&
      summaryIsCurrent(previousPublic?.summary) &&
      privateCurrent &&
      monitoringArtifactsCurrent
    ) {
      console.log(`PR status cache fresh (${ageMin.toFixed(0)}m < ${ttlMin}m) — skipping fetch.`);
      return;
    }
  }

  const repos = resolveRepos();
  console.log("Fetching PR status for", repos.length, "repos...");
  const results = await collectRepoStatuses(repos, previous, resolveGitHubToken());
  const { publicOutput, privateOutput } = buildOutputs(results, repos.length);
  const monitoring = buildMonitoringOutputs(results, repos.length, publicOutput.generated_at);

  mkdirSync(join(__dirname, "..", "public"), { recursive: true });
  mkdirSync(join(__dirname, "..", ".generated", "surfaces"), { recursive: true });
  writeFileSync(PUBLIC_OUT_PATH, JSON.stringify(publicOutput, null, 2));
  writeFileSync(PRIVATE_OUT_PATH, JSON.stringify(privateOutput, null, 2));
  writeFileSync(ISSUE_PUBLIC_OUT_PATH, JSON.stringify(monitoring.issuePublicOutput, null, 2));
  writeFileSync(ISSUE_PRIVATE_OUT_PATH, JSON.stringify(monitoring.issuePrivateOutput, null, 2));
  writeFileSync(HEALTH_PUBLIC_OUT_PATH, JSON.stringify(monitoring.healthPublicOutput, null, 2));
  writeFileSync(HEALTH_PRIVATE_OUT_PATH, JSON.stringify(monitoring.healthPrivateOutput, null, 2));
  console.log(
    `Wrote ${PUBLIC_OUT_PATH} (${publicOutput.summary.total_open_prs} PRs, ` +
    `${publicOutput.summary.total_open_issues} issues, ${publicOutput.summary.total_active_work_branches} active branches across ${repos.length} repos)`
  );
}

if (process.argv[1] && resolve(process.argv[1]) === THIS_FILE) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
