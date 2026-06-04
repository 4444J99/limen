#!/usr/bin/env node
import { existsSync, readFileSync, writeFileSync } from "fs";
import { execFileSync } from "child_process";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const REPOS = [
  "a-organvm/public-record-data-scrapper",
  "a-organvm/peer-audited--behavioral-blockchain",
  "a-organvm/organvm-corpvs-testamentvm",
  "a-organvm/the-actual-news",
  "a-organvm/petasum-super-petasum",
  "a-organvm/organvm-engine",
  "organvm-i-theoria/conversation-corpus-engine",
];

function resolveGitHubToken() {
  if (process.env.GITHUB_TOKEN || process.env.GH_TOKEN) return process.env.GITHUB_TOKEN || process.env.GH_TOKEN;
  try {
    return execFileSync("gh", ["auth", "token"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

const GITHUB_TOKEN = resolveGitHubToken();
const outPath = join(__dirname, "..", "public", "pr-status.json");
const previous = existsSync(outPath) ? JSON.parse(readFileSync(outPath, "utf8")) : null;

function previousRepo(repo) {
  return previous?.repos?.find((item) => item.repo === repo) || null;
}

async function fetchPRs(repo) {
  const url = `https://api.github.com/repos/${repo}/pulls?state=open&per_page=30`;
  const headers = { Accept: "application/vnd.github.v3+json" };
  if (GITHUB_TOKEN) headers.Authorization = `Bearer ${GITHUB_TOKEN}`;

  const res = await fetch(url, { headers });
  if (!res.ok) {
    console.error(`Failed to fetch PRs for ${repo}: ${res.status}`);
    return null;
  }
  const prs = await res.json();
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
    labels: pr.labels.map((l) => l.name),
  }));
}

async function fetchCheckRuns(repo, headSha) {
  const url = `https://api.github.com/repos/${repo}/commits/${headSha}/check-runs?per_page=10`;
  const headers = { Accept: "application/vnd.github.v3+json" };
  if (GITHUB_TOKEN) headers.Authorization = `Bearer ${GITHUB_TOKEN}`;

  const res = await fetch(url, { headers });
  if (!res.ok) return null;
  const data = await res.json();
  const runs = data.check_runs || [];
  const failed = runs.filter((r) => r.conclusion === "failure").length;
  const passed = runs.filter((r) => r.conclusion === "success").length;
  const pending = runs.filter((r) => r.status === "in_progress" || r.status === "queued").length;
  return { total: runs.length, failed, passed, pending };
}

async function main() {
  console.log("Fetching PR status for", REPOS.length, "repos...");
  const results = [];

  for (const repo of REPOS) {
    const prs = await fetchPRs(repo);
    if (prs === null) {
      const fallback = previousRepo(repo);
      if (fallback) {
        results.push({ ...fallback, stale: true, error: "fetch_failed" });
        console.log(`  ${repo}: reused ${fallback.count} cached PRs`);
      } else {
        results.push({ repo, prs: [], count: 0, stale: true, error: "fetch_failed" });
        console.log(`  ${repo}: no cached PRs`);
      }
      continue;
    }
    const prsWithChecks = [];
    for (const pr of prs) {
      const checks = await fetchCheckRuns(repo, pr.head);
      prsWithChecks.push({ ...pr, checks });
    }
    results.push({ repo, prs: prsWithChecks, count: prsWithChecks.length });
    console.log(`  ${repo}: ${prsWithChecks.length} open PRs`);
  }

  const totalPRs = results.reduce((sum, r) => sum + r.count, 0);
  const totalFailed = results.reduce(
    (sum, r) => sum + r.prs.filter((p) => p.checks?.failed > 0).length,
    0
  );

  const output = {
    generated_at: new Date().toISOString(),
    repos: [],
    summary: {
      total_repos: REPOS.length,
      total_open_prs: totalPRs,
      prs_with_failing_ci: totalFailed,
    },
  };

  writeFileSync(outPath, JSON.stringify(output, null, 2));
  console.log(`Wrote ${outPath} (${totalPRs} PRs across ${REPOS.length} repos)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
