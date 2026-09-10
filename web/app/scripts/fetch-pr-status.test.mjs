import test from "node:test";
import assert from "node:assert/strict";

import { buildOutputs, collectRepoStatuses, resolveDefaultRepo, resolveRepos } from "./fetch-pr-status.mjs";

function response(payload, { ok = true, link = null, status = 200 } = {}) {
  return {
    ok,
    status,
    headers: { get: (name) => (name.toLowerCase() === "link" ? link : null) },
    json: async () => payload,
  };
}

test("resolveRepos derives the current repository from environment metadata", () => {
  const env = { GITHUB_REPOSITORY: "4444J99/limen" };
  assert.equal(resolveDefaultRepo(env), "4444J99/limen");
  assert.deepEqual(resolveRepos(env), ["4444J99/limen"]);
});

test("collectRepoStatuses rolls issue and branch aggregates into the generated summary", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (url.includes("/pulls?")) {
      return response([
        {
          number: 12,
          title: "Add monitoring",
          user: { login: "4444J99" },
          created_at: "2026-09-10T00:00:00Z",
          updated_at: "2026-09-10T00:00:00Z",
          draft: false,
          mergeable_state: "clean",
          html_url: "https://github.com/4444J99/limen/pull/12",
          head: { ref: "feat/monitoring", sha: "abc123", repo: { full_name: "4444J99/limen" } },
          base: { ref: "main" },
          labels: [{ name: "dashboard" }],
        },
      ]);
    }
    if (url.includes("/check-runs?")) {
      return response({ check_runs: [{ conclusion: "failure", status: "completed" }] });
    }
    if (url.includes("/search/issues?")) {
      return response({ total_count: 7 });
    }
    if (url.endsWith("/repos/4444J99/limen")) {
      return response({ default_branch: "main" });
    }
    if (url.includes("/branches?")) {
      return response([
        { name: "main", protected: true },
        { name: "feat/monitoring", protected: false },
        { name: "fix/triage", protected: false },
        { name: "gh-pages", protected: true },
      ]);
    }
    throw new Error(`unexpected url ${url}`);
  };

  try {
    const results = await collectRepoStatuses(["4444J99/limen"], null, "token");
    assert.equal(results[0].issue_count, 7);
    assert.equal(results[0].active_work_branches, 2);
    assert.equal(results[0].work_branches_without_open_pr, 1);

    const { publicOutput } = buildOutputs(results, 1, "2026-09-10T00:00:00Z");
    assert.deepEqual(publicOutput.summary, {
      total_repos: 1,
      total_open_prs: 1,
      prs_with_failing_ci: 1,
      total_open_issues: 7,
      total_active_work_branches: 2,
      work_branches_without_open_pr: 1,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("collectRepoStatuses falls back to cached repo monitoring when GitHub requests fail", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => response({}, { ok: false, status: 503 });

  try {
    const previous = {
      repos: [
        {
          repo: "4444J99/limen",
          default_branch: "main",
          prs: [],
          count: 2,
          issue_count: 11,
          active_work_branches: 4,
          work_branches_without_open_pr: 1,
        },
      ],
    };
    const results = await collectRepoStatuses(["4444J99/limen"], previous, "token");
    assert.equal(results[0].stale, true);
    const { publicOutput } = buildOutputs(results, 1, "2026-09-10T00:00:00Z");
    assert.deepEqual(publicOutput.summary, {
      total_repos: 1,
      total_open_prs: 2,
      prs_with_failing_ci: 0,
      total_open_issues: 11,
      total_active_work_branches: 4,
      work_branches_without_open_pr: 1,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("collectRepoStatuses only reuses cached fields for the requests that fail", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (url.includes("/pulls?")) {
      return response([
        {
          number: 18,
          title: "Fresh PR",
          user: { login: "4444J99" },
          created_at: "2026-09-10T00:00:00Z",
          updated_at: "2026-09-10T00:00:00Z",
          draft: false,
          mergeable_state: "clean",
          html_url: "https://github.com/4444J99/limen/pull/18",
          head: { ref: "fix/fresh", sha: "def456", repo: { full_name: "4444J99/limen" } },
          base: { ref: "main" },
          labels: [],
        },
      ]);
    }
    if (url.includes("/check-runs?")) {
      return response({ check_runs: [] });
    }
    if (url.includes("/search/issues?")) {
      return response({}, { ok: false, status: 503 });
    }
    if (url.endsWith("/repos/4444J99/limen")) {
      return response({ default_branch: "main" });
    }
    if (url.includes("/branches?")) {
      return response([
        { name: "main", protected: true },
        { name: "fix/fresh", protected: false },
        { name: "chore/cache", protected: false },
      ]);
    }
    throw new Error(`unexpected url ${url}`);
  };

  try {
    const previous = {
      repos: [
        {
          repo: "4444J99/limen",
          default_branch: "main",
          prs: [],
          count: 9,
          issue_count: 14,
          active_work_branches: 9,
          work_branches_without_open_pr: 8,
        },
      ],
    };
    const results = await collectRepoStatuses(["4444J99/limen"], previous, "token");
    assert.equal(results[0].count, 1);
    assert.equal(results[0].issue_count, 14);
    assert.equal(results[0].active_work_branches, 2);
    assert.equal(results[0].work_branches_without_open_pr, 1);
    assert.equal(results[0].stale, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
