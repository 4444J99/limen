#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { execFileSync } from "child_process";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const appRoot = join(__dirname, "..");
const publicDir = join(appRoot, "public");
const privateDir = join(appRoot, ".generated", "surfaces");

const REPOS = [
  "a-organvm/public-record-data-scrapper",
  "a-organvm/peer-audited--behavioral-blockchain",
  "a-organvm/organvm-corpvs-testamentvm",
  "a-organvm/the-actual-news",
  "a-organvm/petasum-super-petasum",
  "a-organvm/organvm-engine",
  "organvm-i-theoria/conversation-corpus-engine",
];

const publicPrPath = join(publicDir, "pr-status.json");
const ownerPrPath = join(privateDir, "pr-status-owner.json");
const publicIssuePath = join(publicDir, "issue-status.json");
const ownerIssuePath = join(privateDir, "issue-status-owner.json");
const publicRepoHealthPath = join(publicDir, "repo-health.json");
const ownerRepoHealthPath = join(privateDir, "repo-health-owner.json");

const REQUEST_TIMEOUT_MS = Number(process.env.LIMEN_PR_STATUS_REQUEST_TIMEOUT_MS || 15_000);
const TTL_MIN = Number(process.env.LIMEN_PR_STATUS_TTL_MIN || 30);
const ISSUE_STALE_DAYS = Number(process.env.LIMEN_ISSUE_STALE_DAYS || 14);

function readJson(path, fallback = null) {
  try {
    return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : fallback;
  } catch {
    return fallback;
  }
}

function resolveGitHubToken() {
  if (process.env.GITHUB_TOKEN || process.env.GH_TOKEN) return process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
  try {
    return execFileSync("gh", ["auth", "token"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

const GITHUB_TOKEN = resolveGitHubToken();
const previousOwnerPR = readJson(ownerPrPath, { repos: [] });
const previousOwnerIssue = readJson(ownerIssuePath, { repos: [] });
const previousOwnerRepoHealth = readJson(ownerRepoHealthPath, { repos: [] });
const previousPublicPR = readJson(publicPrPath);
const previousPublicIssue = readJson(publicIssuePath);
const previousPublicRepoHealth = readJson(publicRepoHealthPath);

function previousRepo(payload, repo) {
  return payload?.repos?.find((item) => item.repo === repo) || null;
}

function headers() {
  const out = { Accept: "application/vnd.github+json" };
  if (GITHUB_TOKEN) out.Authorization = "Bearer " + GITHUB_TOKEN;
  return out;
}

async function fetchJson(url) {
  const res = await fetch(url, { headers: headers(), signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function staleAgeDays(updatedAt) {
  const updatedMs = Date.parse(updatedAt || "");
  if (!Number.isFinite(updatedMs)) return null;
  return Math.floor((Date.now() - updatedMs) / 86400000);
}

function inferPriority(labels) {
  const lowered = labels.map((label) => String(label || "").toLowerCase());
  if (lowered.some((label) => ["critical", "p0", "priority:critical", "priority/p0"].includes(label))) return "critical";
  if (lowered.some((label) => ["high", "p1", "priority:high", "priority/p1"].includes(label))) return "high";
  if (lowered.some((label) => ["medium", "p2", "priority:medium", "priority/p2"].includes(label))) return "medium";
  if (lowered.some((label) => ["low", "p3", "priority:low", "priority/p3"].includes(label))) return "low";
  if (lowered.some((label) => ["backlog", "p4", "priority:backlog", "priority/p4"].includes(label))) return "backlog";
  return "unset";
}

function mergeBucket(pr, checks, review) {
  const mergeableState = pr.mergeable_state || "unknown";
  if (pr.draft) return { bucket: "draft", ready: false, mergeable_state: mergeableState };
  if (review.state === "changes_requested") return { bucket: "blocked", ready: false, mergeable_state: mergeableState };
  if ((checks?.failed || 0) > 0) return { bucket: "blocked", ready: false, mergeable_state: mergeableState };
  if ((checks?.pending || 0) > 0) return { bucket: "waiting_checks", ready: false, mergeable_state: mergeableState };
  if (review.pending_review || review.state === "unreviewed") return { bucket: "awaiting_review", ready: false, mergeable_state: mergeableState };
  if (["dirty", "blocked", "behind"].includes(mergeableState)) return { bucket: "blocked", ready: false, mergeable_state: mergeableState };
  if (["unknown", "unstable", "has_hooks"].includes(mergeableState)) return { bucket: "unstable", ready: false, mergeable_state: mergeableState };
  if (review.state === "approved" && ["clean"].includes(mergeableState)) {
    return { bucket: "ready", ready: true, mergeable_state: mergeableState };
  }
  return { bucket: "reviewed", ready: false, mergeable_state: mergeableState };
}

function summarizeReviews(reviews, pr) {
  const byReviewer = new Map();
  for (const review of reviews || []) {
    const user = review?.user?.login;
    if (!user) continue;
    byReviewer.set(user, review.state || "COMMENTED");
  }
  const states = [...byReviewer.values()];
  const requested = (pr.requested_reviewers || []).length + (pr.requested_teams || []).length;
  const approved = states.filter((state) => state === "APPROVED").length;
  const changesRequested = states.filter((state) => state === "CHANGES_REQUESTED").length;
  const commented = states.filter((state) => state === "COMMENTED").length;
  const state = changesRequested > 0
    ? "changes_requested"
    : approved > 0
      ? "approved"
      : requested > 0
        ? "review_requested"
        : states.length > 0
          ? "commented"
          : "unreviewed";
  return {
    total_reviews: states.length,
    approved,
    changes_requested: changesRequested,
    commented,
    pending_review: requested,
    state,
  };
}

async function fetchPRs(repo) {
  const prs = await fetchJson(`https://api.github.com/repos/${repo}/pulls?state=open&per_page=30`);
  return prs.map((pr) => ({
    number: pr.number,
    title: pr.title,
    author: pr.user?.login || "unknown",
    created_at: pr.created_at,
    updated_at: pr.updated_at,
    draft: Boolean(pr.draft),
    mergeable_state: pr.mergeable_state || "unknown",
    html_url: pr.html_url,
    head: pr.head?.ref || "",
    head_sha: pr.head?.sha || "",
    base: pr.base?.ref || "",
    labels: (pr.labels || []).map((label) => label.name),
    requested_reviewers: (pr.requested_reviewers || []).map((reviewer) => reviewer.login),
    requested_teams: (pr.requested_teams || []).map((team) => team.slug),
  }));
}

async function fetchCheckRuns(repo, headSha) {
  if (!headSha) return null;
  const data = await fetchJson(`https://api.github.com/repos/${repo}/commits/${headSha}/check-runs?per_page=20`);
  const runs = data.check_runs || [];
  const failed = runs.filter((run) => ["failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"].includes(run.conclusion)).length;
  const passed = runs.filter((run) => run.conclusion === "success").length;
  const pending = runs.filter((run) => run.status === "in_progress" || run.status === "queued").length;
  return { total: runs.length, failed, passed, pending };
}

async function fetchReviews(repo, number) {
  return fetchJson(`https://api.github.com/repos/${repo}/pulls/${number}/reviews?per_page=50`);
}

function summarizePRPayload(repos) {
  const repoSummaries = repos.map((repo) => ({
    repo: repo.repo,
    count: repo.count,
    failing_ci_count: repo.failing_ci_count,
    pending_checks_count: repo.pending_checks_count,
    review_pending_count: repo.review_pending_count,
    ready_to_merge_count: repo.ready_to_merge_count,
    blocked_count: repo.blocked_count,
    merge_readiness: repo.merge_readiness,
  }));
  const rollup = repoSummaries.reduce((acc, repo) => {
    acc.total_open_prs += repo.count;
    acc.prs_with_failing_ci += repo.failing_ci_count;
    acc.prs_with_pending_checks += repo.pending_checks_count;
    acc.review_pending_prs += repo.review_pending_count;
    acc.ready_to_merge_prs += repo.ready_to_merge_count;
    acc.blocked_prs += repo.blocked_count;
    for (const [bucket, count] of Object.entries(repo.merge_readiness || {})) {
      acc.merge_readiness[bucket] = (acc.merge_readiness[bucket] || 0) + count;
    }
    return acc;
  }, {
    total_repos: repos.length,
    total_open_prs: 0,
    prs_with_failing_ci: 0,
    prs_with_pending_checks: 0,
    review_pending_prs: 0,
    ready_to_merge_prs: 0,
    blocked_prs: 0,
    merge_readiness: {},
  });
  return {
    generated_at: new Date().toISOString(),
    repos: repoSummaries,
    summary: rollup,
  };
}

async function fetchPRStatusForRepo(repo) {
  const prs = await fetchPRs(repo);
  const detailed = await Promise.all(prs.map(async (pr) => {
    const [checks, reviews] = await Promise.all([
      fetchCheckRuns(repo, pr.head_sha).catch(() => null),
      fetchReviews(repo, pr.number).catch(() => []),
    ]);
    const review = summarizeReviews(reviews, pr);
    const merge = mergeBucket(pr, checks, review);
    return { ...pr, checks, review, merge };
  }));
  const mergeReadiness = detailed.reduce((acc, pr) => {
    acc[pr.merge.bucket] = (acc[pr.merge.bucket] || 0) + 1;
    return acc;
  }, {});
  return {
    repo,
    prs: detailed,
    count: detailed.length,
    failing_ci_count: detailed.filter((pr) => (pr.checks?.failed || 0) > 0).length,
    pending_checks_count: detailed.filter((pr) => (pr.checks?.pending || 0) > 0).length,
    review_pending_count: detailed.filter((pr) => pr.review.pending_review > 0 || pr.review.state === "unreviewed").length,
    ready_to_merge_count: detailed.filter((pr) => pr.merge.ready).length,
    blocked_count: detailed.filter((pr) => pr.merge.bucket === "blocked").length,
    merge_readiness: mergeReadiness,
  };
}

async function fetchIssuesForRepo(repo) {
  const issues = await fetchJson(`https://api.github.com/repos/${repo}/issues?state=open&sort=updated&direction=desc&per_page=100`);
  const detailed = issues
    .filter((issue) => !issue.pull_request)
    .map((issue) => {
      const labels = (issue.labels || []).map((label) => typeof label === "string" ? label : label.name);
      const assignees = (issue.assignees || []).map((assignee) => assignee.login);
      const priority = inferPriority(labels);
      const ageDays = staleAgeDays(issue.updated_at);
      const stale = ageDays !== null && ageDays >= ISSUE_STALE_DAYS;
      const readyToTriage = labels.length === 0 || assignees.length === 0 || priority === "unset";
      return {
        number: issue.number,
        title: issue.title,
        html_url: issue.html_url,
        labels,
        assignees,
        created_at: issue.created_at,
        updated_at: issue.updated_at,
        stale,
        ready_to_triage: readyToTriage,
        priority,
      };
    });
  const priority_counts = detailed.reduce((acc, issue) => {
    acc[issue.priority] = (acc[issue.priority] || 0) + 1;
    return acc;
  }, {});
  return {
    repo,
    issues: detailed,
    count: detailed.length,
    unlabeled_count: detailed.filter((issue) => issue.labels.length === 0).length,
    unassigned_count: detailed.filter((issue) => issue.assignees.length === 0).length,
    stale_count: detailed.filter((issue) => issue.stale).length,
    ready_to_triage_count: detailed.filter((issue) => issue.ready_to_triage).length,
    priority_counts,
  };
}

function summarizeIssuePayload(repos) {
  const repoSummaries = repos.map((repo) => ({
    repo: repo.repo,
    count: repo.count,
    unlabeled_count: repo.unlabeled_count,
    unassigned_count: repo.unassigned_count,
    stale_count: repo.stale_count,
    ready_to_triage_count: repo.ready_to_triage_count,
    priority_counts: repo.priority_counts,
  }));
  const summary = repoSummaries.reduce((acc, repo) => {
    acc.total_open_issues += repo.count;
    acc.unlabeled_issues += repo.unlabeled_count;
    acc.unassigned_issues += repo.unassigned_count;
    acc.stale_issues += repo.stale_count;
    acc.ready_to_triage += repo.ready_to_triage_count;
    for (const [priority, count] of Object.entries(repo.priority_counts || {})) {
      acc.priority_counts[priority] = (acc.priority_counts[priority] || 0) + count;
    }
    return acc;
  }, {
    total_repos: repos.length,
    total_open_issues: 0,
    unlabeled_issues: 0,
    unassigned_issues: 0,
    stale_issues: 0,
    ready_to_triage: 0,
    priority_counts: {},
  });
  return {
    generated_at: new Date().toISOString(),
    repos: repoSummaries,
    summary,
  };
}

async function fetchRepoHealthForRepo(repo) {
  const payload = await fetchJson(`https://api.github.com/repos/${repo}/actions/runs?per_page=20`);
  const runs = (payload.workflow_runs || []).map((run) => ({
    id: run.id,
    name: run.name,
    status: run.status,
    conclusion: run.conclusion,
    html_url: run.html_url,
    updated_at: run.updated_at,
    head_branch: run.head_branch,
    event: run.event,
  }));
  const failingRuns = runs.filter((run) => run.status === "completed" && ["failure", "timed_out", "cancelled", "startup_failure", "action_required", "stale"].includes(run.conclusion)).length;
  const inProgressRuns = runs.filter((run) => ["queued", "in_progress", "requested", "waiting", "pending"].includes(run.status)).length;
  const latest_run = runs[0] || null;
  const status = failingRuns > 0 ? "degraded" : inProgressRuns > 0 ? "active" : latest_run?.conclusion === "success" ? "healthy" : "unknown";
  return {
    repo,
    status,
    failing_runs: failingRuns,
    in_progress_runs: inProgressRuns,
    latest_run,
    recent_runs: runs.slice(0, 5),
  };
}

function summarizeRepoHealthPayload(repos) {
  const repoSummaries = repos.map((repo) => ({
    repo: repo.repo,
    status: repo.status,
    failing_runs: repo.failing_runs,
    in_progress_runs: repo.in_progress_runs,
    latest_run: repo.latest_run
      ? {
          name: repo.latest_run.name,
          status: repo.latest_run.status,
          conclusion: repo.latest_run.conclusion,
          updated_at: repo.latest_run.updated_at,
        }
      : null,
  }));
  const summary = repoSummaries.reduce((acc, repo) => {
    acc.failing_workflows += repo.failing_runs;
    acc.in_progress_runs += repo.in_progress_runs;
    if (repo.status === "degraded") acc.degraded_repos += 1;
    if (repo.status === "healthy") acc.healthy_repos += 1;
    return acc;
  }, {
    total_repos: repos.length,
    degraded_repos: 0,
    healthy_repos: 0,
    failing_workflows: 0,
    in_progress_runs: 0,
  });
  return {
    generated_at: new Date().toISOString(),
    repos: repoSummaries,
    summary,
  };
}

function cachedIsFresh() {
  const stamps = [
    previousPublicPR?.generated_at,
    previousPublicIssue?.generated_at,
    previousPublicRepoHealth?.generated_at,
    previousOwnerPR?.generated_at,
    previousOwnerIssue?.generated_at,
    previousOwnerRepoHealth?.generated_at,
  ].filter(Boolean);
  if (stamps.length !== 6) return false;
  const latest = Math.max(...stamps.map((stamp) => Date.parse(stamp)));
  if (!Number.isFinite(latest)) return false;
  const ageMin = (Date.now() - latest) / 60000;
  return ageMin < TTL_MIN;
}

function writeJson(path, payload) {
  writeFileSync(path, `${JSON.stringify(payload, null, 2)}\n`);
}

async function main() {
  mkdirSync(publicDir, { recursive: true });
  mkdirSync(privateDir, { recursive: true });

  if (cachedIsFresh()) {
    console.log(`Monitoring status cache fresh (< ${TTL_MIN}m) — skipping fetch.`);
    return;
  }

  console.log(`Fetching PR, issue, and repo-health status for ${REPOS.length} repos...`);
  const prRepos = [];
  const issueRepos = [];
  const repoHealthRepos = [];

  for (const repo of REPOS) {
    try {
      const [prStatus, issueStatus, repoHealth] = await Promise.all([
        fetchPRStatusForRepo(repo),
        fetchIssuesForRepo(repo),
        fetchRepoHealthForRepo(repo),
      ]);
      prRepos.push(prStatus);
      issueRepos.push(issueStatus);
      repoHealthRepos.push(repoHealth);
      console.log(`  ${repo}: ${prStatus.count} PRs, ${issueStatus.count} issues, ${repoHealth.status} workflows`);
    } catch (error) {
      console.error(`  ${repo}: fetch failed (${error instanceof Error ? error.message : "unknown error"})`);
      prRepos.push(previousRepo(previousOwnerPR, repo) || { repo, prs: [], count: 0, failing_ci_count: 0, pending_checks_count: 0, review_pending_count: 0, ready_to_merge_count: 0, blocked_count: 0, merge_readiness: {}, stale: true, error: "fetch_failed" });
      issueRepos.push(previousRepo(previousOwnerIssue, repo) || { repo, issues: [], count: 0, unlabeled_count: 0, unassigned_count: 0, stale_count: 0, ready_to_triage_count: 0, priority_counts: {}, stale: true, error: "fetch_failed" });
      repoHealthRepos.push(previousRepo(previousOwnerRepoHealth, repo) || { repo, status: "unknown", failing_runs: 0, in_progress_runs: 0, latest_run: null, recent_runs: [], stale: true, error: "fetch_failed" });
    }
  }

  const ownerPrPayload = summarizePRPayload(prRepos);
  ownerPrPayload.repos = prRepos;
  const publicPrPayload = { ...ownerPrPayload, repos: [] };

  const ownerIssuePayload = summarizeIssuePayload(issueRepos);
  ownerIssuePayload.repos = issueRepos;
  const publicIssuePayload = { ...ownerIssuePayload, repos: [] };

  const ownerRepoHealthPayload = summarizeRepoHealthPayload(repoHealthRepos);
  ownerRepoHealthPayload.repos = repoHealthRepos;
  const publicRepoHealthPayload = { ...ownerRepoHealthPayload, repos: [] };

  writeJson(publicPrPath, publicPrPayload);
  writeJson(ownerPrPath, ownerPrPayload);
  writeJson(publicIssuePath, publicIssuePayload);
  writeJson(ownerIssuePath, ownerIssuePayload);
  writeJson(publicRepoHealthPath, publicRepoHealthPayload);
  writeJson(ownerRepoHealthPath, ownerRepoHealthPayload);

  console.log(`Wrote monitoring feeds for ${REPOS.length} repos`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
