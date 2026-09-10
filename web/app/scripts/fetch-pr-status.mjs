#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { execFileSync } from "child_process";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

function resolveGitHubToken() {
  if (process.env.GITHUB_TOKEN || process.env.GH_TOKEN) return process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
  try {
    return execFileSync("gh", ["auth", "token"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

function resolveRepos() {
  const configured = process.env.LIMEN_PR_STATUS_REPOS || process.env.LIMEN_GITHUB_REPO || "4444J99/limen";
  return [...new Set(configured.split(",").map((value) => value.trim()).filter(Boolean))];
}

const GITHUB_TOKEN = resolveGitHubToken();
const REPOS = resolveRepos();
const PUBLIC_OUT_PATH = join(__dirname, "..", "public", "pr-status.json");
const PRIVATE_OUT_PATH = join(__dirname, "..", ".generated", "surfaces", "pr-status.json");
const previousPublic = existsSync(PUBLIC_OUT_PATH) ? JSON.parse(readFileSync(PUBLIC_OUT_PATH, "utf8")) : null;
const previousPrivate = existsSync(PRIVATE_OUT_PATH) ? JSON.parse(readFileSync(PRIVATE_OUT_PATH, "utf8")) : null;
const previous = previousPrivate || previousPublic;
const REQUEST_TIMEOUT_MS = Number(process.env.LIMEN_PR_STATUS_REQUEST_TIMEOUT_MS || 15_000);

function githubHeaders() {
  const headers = { Accept: "application/vnd.github.v3+json" };
  if (GITHUB_TOKEN) headers.Authorization = "Bearer " + GITHUB_TOKEN;
  return headers;
}

function previousRepo(repo) {
  return previous?.repos?.find((item) => item.repo === repo) || null;
}

function nextLink(linkHeader) {
  const match = /<([^>]+)>;\s*rel="next"/.exec(linkHeader || "");
  return match?.[1] || null;
}

async function fetchJson(url, label) {
  let res;
  try {
    res = await fetch(url, { headers: githubHeaders(), signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
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

async function fetchPaginatedArray(url, label, pageLimit = 10) {
  const rows = [];
  let next = url;
  for (let page = 0; next && page < pageLimit; page += 1) {
    const res = await fetchJson(next, label);
    if (!res) return null;
    const payload = await res.json();
    if (!Array.isArray(payload)) return null;
    rows.push(...payload);
    next = nextLink(res.headers.get("link"));
  }
  return rows;
}

async function fetchPRs(repo) {
  const prs = await fetchPaginatedArray(`https://api.github.com/repos/${repo}/pulls?state=open&per_page=100`, `PRs for ${repo}`);
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
    base: pr.base.ref,
    head_repo: pr.head.repo?.full_name || null,
    labels: pr.labels.map((label) => label.name),
  }));
}

async function fetchCheckRuns(repo, headSha) {
  const res = await fetchJson(
    `https://api.github.com/repos/${repo}/commits/${headSha}/check-runs?per_page=10`,
    `check runs for ${repo}@${headSha}`
  );
  if (!res) return null;
  const data = await res.json();
  const runs = data.check_runs || [];
  const failed = runs.filter((run) => run.conclusion === "failure").length;
  const passed = runs.filter((run) => run.conclusion === "success").length;
  const pending = runs.filter((run) => run.status === "in_progress" || run.status === "queued").length;
  return { total: runs.length, failed, passed, pending };
}

async function fetchIssueCount(repo) {
  const query = encodeURIComponent(`repo:${repo} is:issue is:open`);
  const res = await fetchJson(`https://api.github.com/search/issues?q=${query}&per_page=1`, `open issues for ${repo}`);
  if (!res) return null;
  const payload = await res.json();
  return Number.isFinite(payload?.total_count) ? payload.total_count : null;
}

async function fetchRepoMeta(repo) {
  const res = await fetchJson(`https://api.github.com/repos/${repo}`, `repo metadata for ${repo}`);
  if (!res) return null;
  const payload = await res.json();
  return {
    default_branch: typeof payload?.default_branch === "string" && payload.default_branch ? payload.default_branch : "main",
  };
}

async function fetchBranches(repo) {
  const branches = await fetchPaginatedArray(`https://api.github.com/repos/${repo}/branches?per_page=100`, `branches for ${repo}`);
  if (branches === null) return null;
  return branches.map((branch) => ({
    name: branch.name,
    protected: Boolean(branch.protected),
  }));
}

async function main() {
  // Cache-skip-if-fresh: the static site rebuilds every web beat, but PR status does NOT need a live
  // GitHub round-trip each time. If the cached pr-status.json is younger than the TTL, reuse it and
  // skip ALL network — this nested fetch (repos x PRs x check-runs = 200+ sequential calls) is what
  // blew past the build timeout and left the dashboard stale since 2026-06-19. TTL derived from env,
  // never pinned; the money.html surface is the always-fresh primary regardless.
  const ttlMin = Number(process.env.LIMEN_PR_STATUS_TTL_MIN || 30);
  const previousGeneratedAt = previousPrivate?.generated_at || previousPublic?.generated_at;
  if (previousGeneratedAt) {
    const ageMin = (Date.now() - new Date(previousGeneratedAt).getTime()) / 60000;
    if (Number.isFinite(ageMin) && ageMin < ttlMin && previousPrivate) {
      console.log(`PR status cache fresh (${ageMin.toFixed(0)}m < ${ttlMin}m) — skipping fetch.`);
      return;
    }
  }

  console.log("Fetching PR status for", REPOS.length, "repos...");
  const results = [];

  for (const repo of REPOS) {
    const [prs, issueCount, repoMeta, branches] = await Promise.all([
      fetchPRs(repo),
      fetchIssueCount(repo),
      fetchRepoMeta(repo),
      fetchBranches(repo),
    ]);
    if (prs === null || issueCount === null || repoMeta === null || branches === null) {
      const fallback = previousRepo(repo);
      if (fallback) {
        results.push({ ...fallback, stale: true, error: "fetch_failed" });
        console.log(`  ${repo}: reused cached monitoring summary`);
      } else {
        results.push({
          repo,
          default_branch: "main",
          prs: [],
          count: 0,
          issue_count: 0,
          non_default_branches: 0,
          branches_without_open_pr: 0,
          stale: true,
          error: "fetch_failed",
        });
        console.log(`  ${repo}: no cached monitoring data`);
      }
      continue;
    }

    const prsWithChecks = [];
    for (const pr of prs) {
      const checks = await fetchCheckRuns(repo, pr.head);
      prsWithChecks.push({ ...pr, checks });
    }
    const nonDefaultBranches = branches.filter((branch) => branch.name !== repoMeta.default_branch);
    const branchesWithOpenPr = new Set(
      prsWithChecks
        .filter((pr) => pr.head_repo === repo)
        .map((pr) => pr.head)
    );
    const branchesWithoutOpenPr = nonDefaultBranches.filter((branch) => !branchesWithOpenPr.has(branch.name));
    results.push({
      repo,
      default_branch: repoMeta.default_branch,
      prs: prsWithChecks,
      count: prsWithChecks.length,
      issue_count: issueCount,
      non_default_branches: nonDefaultBranches.length,
      branches_without_open_pr: branchesWithoutOpenPr.length,
    });
    console.log(
      `  ${repo}: ${prsWithChecks.length} open PRs, ${issueCount} open issues, ${nonDefaultBranches.length} non-default branches`
    );
  }

  const totalPRs = results.reduce((sum, repo) => sum + repo.count, 0);
  const totalFailed = results.reduce((sum, repo) => sum + repo.prs.filter((pr) => pr.checks?.failed > 0).length, 0);
  const totalIssues = results.reduce((sum, repo) => sum + (repo.issue_count || 0), 0);
  const totalBranches = results.reduce((sum, repo) => sum + (repo.non_default_branches || 0), 0);
  const branchesWithoutOpenPr = results.reduce((sum, repo) => sum + (repo.branches_without_open_pr || 0), 0);
  const generatedAt = new Date().toISOString();
  const summary = {
    total_repos: REPOS.length,
    total_open_prs: totalPRs,
    prs_with_failing_ci: totalFailed,
    total_open_issues: totalIssues,
    total_non_default_branches: totalBranches,
    branches_without_open_pr: branchesWithoutOpenPr,
  };
  const publicOutput = { generated_at: generatedAt, repos: [], summary };
  const privateOutput = { generated_at: generatedAt, repos: results, summary };

  mkdirSync(join(__dirname, "..", ".generated", "surfaces"), { recursive: true });
  writeFileSync(PUBLIC_OUT_PATH, JSON.stringify(publicOutput, null, 2));
  writeFileSync(PRIVATE_OUT_PATH, JSON.stringify(privateOutput, null, 2));
  console.log(
    `Wrote ${PUBLIC_OUT_PATH} (${totalPRs} PRs, ${totalIssues} issues, ${totalBranches} branches across ${REPOS.length} repos)`
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
