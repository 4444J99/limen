import assert from "node:assert/strict";
import test from "node:test";

import {
  loadPrivateBoard,
  privateBoardStoreContract,
  publicBoardProjection,
  savePrivateBoard,
} from "../src/conduct/private-board.js";

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

test("public board projection contains aggregate counts and no task material", () => {
  const projection = publicBoardProjection({
    portal: { name: "private portal", budget: { daily: 9 } },
    tasks: [{
      id: "PRIVATE-CONTACT-1",
      title: "Named private engagement",
      repo: "4444J99/private-repo",
      context: "private context",
      predicate: "pytest -q",
      receipt_target: "git:private/repo:receipt",
      target_agent: "codex",
      status: "done",
      priority: "high",
    }],
  });

  assert.deepEqual(projection.tasks, []);
  assert.equal(projection.portal.name, "Universal Task Intake");
  assert.deepEqual(projection.portal.public_projection.by_status, { done: 1 });
  assert.equal(projection.portal.public_projection.total, 1);
  assert.equal(JSON.stringify(projection).includes("PRIVATE-CONTACT-1"), false);
  assert.equal(JSON.stringify(projection).includes("private-repo"), false);
  assert.equal(JSON.stringify(projection).includes("private context"), false);
  assert.equal(JSON.stringify(projection).includes("pytest -q"), false);
});

test("private board custody is separate from conduct state and survives reload", async () => {
  const storage = new FakeStorage();
  assert.equal(await loadPrivateBoard(storage), null);
  const board = {
    portal: { budget: { daily: 10 } },
    tasks: [{ id: "PRIVATE-1", title: "Private task", status: "open", target_agent: "codex" }],
  };
  await savePrivateBoard(storage, board);
  const loaded = await loadPrivateBoard(storage);
  assert.equal(loaded.schema_version, "limen.private_board.v1");
  assert.equal(loaded.tasks[0].title, "Private task");
  assert.equal(storage.values.has("conduct_state.v2.manifest"), false);
  assert.equal(storage.values.has(privateBoardStoreContract().manifest_key), true);
});

