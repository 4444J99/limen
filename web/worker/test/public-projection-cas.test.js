import assert from "node:assert/strict";
import test from "node:test";

import { commitTaskCompatibilityEvent, publishPublicBoard } from "../src/conduct/projection.js";
import { savePrivateBoard } from "../src/conduct/private-board.js";

// The projection branch file stops being a parseable task board the moment the
// first counts-only aggregate is published (its `tasks: []` renders flow-style,
// which the surgical block parser rejects). The CAS read that anchors the next
// publication must therefore never parse it as a board — this suite pins that.

const COUNTS_ONLY_YAML = [
  "schema_version: 'limen.public_board_projection.v1'",
  "portal:",
  "  name: 'Universal Task Intake'",
  "  public_projection:",
  "    total: 2",
  "tasks: []",
  "",
].join("\n");

const ENV = {
  LIMEN_GITHUB_REPO: "organvm/limen",
  LIMEN_GITHUB_TOKEN: "test-token",
  LIMEN_GITHUB_BRANCH: "tabularius/board-projection",
  LIMEN_GITHUB_PATH: "tasks.yaml",
};

function stubGithub({ projectionYaml }) {
  const writes = [];
  const fetchImpl = async (url, { method = "GET", body } = {}) => {
    const respond = (status, payload) => new Response(
      payload === null ? null : (typeof payload === "string" ? payload : JSON.stringify(payload)),
      { status },
    );
    if (url.endsWith("/merges") && method === "POST") return respond(204, null);
    if (url.includes("/git/refs/heads/") && method === "GET") {
      return respond(200, { object: { sha: "headsha" } });
    }
    if (url.includes("/git/commits/headsha") && method === "GET") {
      return respond(200, { tree: { sha: "treesha" } });
    }
    if (url.includes("/contents/tasks.yaml") && method === "GET") {
      return respond(200, { content: Buffer.from(projectionYaml, "utf-8").toString("base64") });
    }
    if (url.endsWith("/git/blobs") && method === "POST") {
      writes.push({ kind: "blob", body: JSON.parse(body) });
      return respond(201, { sha: "blobsha" });
    }
    if (url.endsWith("/git/trees") && method === "POST") return respond(201, { sha: "newtreesha" });
    if (url.endsWith("/git/commits") && method === "POST") return respond(201, { sha: "newcommitsha" });
    if (url.includes("/git/refs/heads/") && method === "PATCH") {
      writes.push({ kind: "ref", body: JSON.parse(body) });
      return respond(200, { object: { sha: "newcommitsha" } });
    }
    throw new Error(`unexpected GitHub call in stub: ${method} ${url}`);
  };
  return { fetchImpl, writes };
}

class FakeStorage {
  constructor() { this.values = new Map(); }

  async get(key) {
    if (Array.isArray(key)) {
      return new Map(key.filter((item) => this.values.has(item)).map((item) => [item, structuredClone(this.values.get(item))]));
    }
    return structuredClone(this.values.get(key));
  }

  async put(key, value) { this.values.set(key, structuredClone(value)); }

  async delete(key) {
    for (const item of (Array.isArray(key) ? key : [key])) this.values.delete(item);
  }

  async list({ prefix } = {}) {
    return new Map([...this.values].filter(([key]) => !prefix || key.startsWith(prefix)));
  }
}

test("publishPublicBoard commits over an existing counts-only projection file", async () => {
  const { fetchImpl, writes } = stubGithub({ projectionYaml: COUNTS_ONLY_YAML });
  const result = await publishPublicBoard(ENV, {
    portal: {},
    tasks: [{ id: "PRIVATE-1", status: "open", title: "private", repo: "4444J99/private" }],
  }, { fetchImpl });
  assert.equal(result.status, "committed");
  assert.equal(result.mode, "public-aggregate");
  const blob = writes.find((entry) => entry.kind === "blob");
  assert.ok(blob, "publication wrote a blob");
  assert.equal(blob.body.content.includes("PRIVATE-1"), false);
  assert.equal(blob.body.content.includes("tasks: []"), true);
});

test("private-canonical status commit survives a counts-only projection file", async () => {
  const storage = new FakeStorage();
  await savePrivateBoard(storage, {
    portal: {},
    tasks: [{
      id: "TASK-1",
      title: "board task",
      status: "in_progress",
      target_agent: "codex",
      priority: "high",
      budget_cost: 1,
      created: "2026-08-01",
      dispatch_log: [],
    }],
  });
  const { fetchImpl } = stubGithub({ projectionYaml: COUNTS_ONLY_YAML });
  const result = await commitTaskCompatibilityEvent(ENV, {
    schema_version: "limen.task_packet_projection_event.v1",
    event_id: "conduct:test:1:compatibility",
    kind: "task.status",
    timestamp: "2026-08-15T00:00:00.000Z",
    task_id: "TASK-1",
    run_id: "run-1",
    lease_id: "lease-1",
    generation: 1,
    agent: "codex",
    session_id: "codex-session",
    intent: {
      kind: "task.status",
      task_id: "TASK-1",
      expected_status: "in_progress",
      patch: { status: "failed" },
      log: {
        agent: "codex",
        session_id: "codex-session",
        status: "failed",
        output: "stale lease released",
      },
    },
  }, { fetchImpl, storage });
  assert.equal(result.status, "committed");
  assert.equal(result.mode, "private-canonical");
  assert.equal(result.task.status, "failed");
});
