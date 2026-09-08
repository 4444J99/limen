import assert from "node:assert/strict";
import test from "node:test";
import { recoverProjectionBranch, publishPublicBoard } from "../src/conduct/projection.js";

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
