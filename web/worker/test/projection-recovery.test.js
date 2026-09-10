import assert from "node:assert/strict";
import test from "node:test";
import { recoverProjectionBranch, publishPublicBoard, commitTaskCompatibilityEvent } from "../src/conduct/projection.js";
import { savePrivateBoard, loadPrivateBoard } from "../src/conduct/private-board.js";

const env = { LIMEN_GITHUB_REPO: "owner/repo", LIMEN_GITHUB_TOKEN: "fixture" };
const root = "https://api.github.com/repos/owner/repo";
const branch = "tabularius/board-projection";
const sha = "a".repeat(40);
const peerSha = "b".repeat(40);
function fixture(options = {}) {
  let head = options.existing || null;
  let creates = 0;
  const writes = [];
  const ref = (name, commit) => ({ ref: `refs/heads/${name}`, object: { sha: commit, type: "commit" } });
  const response = (status, data) => new Response(data === null ? null : JSON.stringify(data), { status });
  const fetchImpl = async (url, { method, body } = {}) => {
    const payload = body ? JSON.parse(body) : null;
    if (method !== "GET") writes.push({ url, method, payload });
    if (url === root) return response(200, { full_name: options.repo || "owner/repo", default_branch: options.defaultBranch || "main" });
    if (url === `${root}/git/refs/heads/${branch}` && method === "GET") {
      return response(options.refStatus || (head ? 200 : 404), head ? ref(branch, head) : {});
    }
    if (url.startsWith(`${root}/git/ref/heads/`)) {
      return response(200, ref(options.defaultBranch || "main", options.defaultSha || sha));
    }
    if (url === `${root}/git/refs` && method === "POST") {
      creates += 1;
      if (options.concurrent) head = peerSha;
      else if (!options.creationFails) head = sha;
      return response(options.concurrent || options.creationFails ? 422 : 201, {});
    }
    if (url === `${root}/merges`) return response(head ? 204 : 404, head ? null : { message: "Base does not exist" });
    if (url.startsWith(`${root}/git/commits/`)) return response(200, { tree: { sha: "tree" } });
    if (url.startsWith(`${root}/contents/`)) return response(200, { content: Buffer.from("tasks: []\n").toString("base64") });
    if (url.endsWith("/git/blobs")) return response(201, { sha: "blob" });
    if (url.endsWith("/git/trees")) return response(201, { sha: "tree" });
    if (url.endsWith("/git/commits")) return response(201, { sha: peerSha });
    if (method === "PATCH") { head = payload.sha; return response(200, ref(branch, head)); }
    throw new Error(`Unexpected request ${method} ${url}`);
  };
  return { fetchImpl, writes, get creates() { return creates; }, get head() { return head; } };
}

test("missing publication branch is created from the observed default commit", async () => {
  const f = fixture({ defaultBranch: "trunk" });
  assert.equal(await recoverProjectionBranch(env, f.fetchImpl), "trunk");
  assert.deepEqual(f.writes[0].payload, { ref: `refs/heads/${branch}`, sha });
});
test("concurrent creation preserves the other publisher's history", async () => {
  const f = fixture({ concurrent: true });
  await recoverProjectionBranch(env, f.fetchImpl);
  assert.equal(f.head, peerSha);
  assert.equal(f.creates, 1);
  assert.ok(f.writes.every((w) => w.method !== "PATCH"));
});
test("existing publication history is never reset", async () => {
  const f = fixture({ existing: peerSha });
  await recoverProjectionBranch(env, f.fetchImpl);
  assert.equal(f.head, peerSha);
  assert.equal(f.writes.length, 0);
});
for (const [name, options, configuration] of [
  ["repository mismatch", { repo: "other/repo" }, env],
  ["default mismatch", { defaultBranch: "trunk" }, { ...env, LIMEN_GITHUB_DEFAULT_BRANCH: "main" }],
  ["default target", { defaultBranch: branch }, env],
  ["invalid default SHA", { defaultSha: "bad" }, env],
  ["invalid existing SHA", { existing: "bad" }, env],
  ["permission denied", { refStatus: 403 }, env],
  ["failed creation", { creationFails: true }, env],
]) {
  test(`recovery refuses ${name}`, async () => {
    const f = fixture(options);
    await assert.rejects(recoverProjectionBranch(configuration, f.fetchImpl));
    assert.ok(f.writes.every((w) => w.method !== "PATCH"));
  });
}
test("two consecutive publications succeed after deletion with one automatic creation", async () => {
  const f = fixture();
  const board = { portal: {}, tasks: [] };
  for (let n = 0; n < 2; n += 1) {
    assert.equal((await publishPublicBoard(env, board, { fetchImpl: f.fetchImpl })).status, "committed");
  }
  assert.equal(f.creates, 1);
  const commits = f.writes.filter((w) => w.url.endsWith("/git/commits"));
  assert.deepEqual(commits.map((w) => w.payload.parents), [[sha], [peerSha]]);
  assert.ok(f.writes.filter((w) => w.method === "PATCH").every((w) => w.payload.force === false));
});

test("consecutive keeper mutations preserve private history after automatic ref recovery", async () => {
  const values = new Map();
  const storage = {
    async get(key) {
      if (Array.isArray(key)) return new Map(key.filter((k) => values.has(k)).map((k) => [k, structuredClone(values.get(k))]));
      return structuredClone(values.get(key));
    },
    async put(key, value) { values.set(key, structuredClone(value)); },
    async delete(key) { for (const k of Array.isArray(key) ? key : [key]) values.delete(k); },
    async list({ prefix } = {}) { return new Map([...values].filter(([k]) => !prefix || k.startsWith(prefix))); },
  };
  await savePrivateBoard(storage, { portal: {}, tasks: [{
    id: "RECOVERY-TEST", title: "private fixture", status: "in_progress",
    target_agent: "codex", priority: "high", budget_cost: 1, dispatch_log: [],
  }] });
  const f = fixture();
  for (const [n, before, after] of [[1, "in_progress", "failed"], [2, "failed", "open"]]) {
    const result = await commitTaskCompatibilityEvent(env, {
      schema_version: "limen.task_packet_projection_event.v1",
      event_id: `recovery:${n}`, kind: "task.status", timestamp: `2026-09-08T12:00:0${n}.000Z`,
      task_id: "RECOVERY-TEST", run_id: `run-${n}`, lease_id: `lease-${n}`, generation: n,
      agent: "codex", session_id: "fixture",
      intent: { kind: "task.status", task_id: "RECOVERY-TEST", expected_status: before,
        patch: { status: after }, log: { status: after, output: "fixture mutation" } },
    }, { fetchImpl: f.fetchImpl, storage });
    assert.equal(result.status, "committed");
    assert.equal(result.task.status, after);
    assert.deepEqual(result.publication, { status: "committed", mode: "public-aggregate", sha: peerSha });
  }
  const board = await loadPrivateBoard(storage);
  assert.deepEqual(board.tasks[0].dispatch_log.map((entry) => entry.status), ["failed", "open"]);
  assert.equal(f.creates, 1);
  assert.ok(f.writes.filter((w) => w.url.endsWith("/git/blobs"))
    .every((w) => !w.payload.content.includes("RECOVERY-TEST")));
});
