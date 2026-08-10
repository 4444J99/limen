import { ChunkedDurableStateStore } from "./durable-store.js";

export const PRIVATE_BOARD_SCHEMA = "limen.private_board.v1";
export const PRIVATE_BOARD_MANIFEST_KEY = "private_board.v1.manifest";
export const PRIVATE_BOARD_LEGACY_KEY = "private_board.v1.legacy";
export const PRIVATE_BOARD_CHUNK_PREFIX = "private_board.v1.chunk.";

const PRIVATE_BOARD_STORE_OPTIONS = Object.freeze({
  schema_version: "limen.private_board_chunks.v1",
  manifest_key: PRIVATE_BOARD_MANIFEST_KEY,
  legacy_key: PRIVATE_BOARD_LEGACY_KEY,
  chunk_prefix: PRIVATE_BOARD_CHUNK_PREFIX,
  liveness_enabled: false,
});

function clone(value) {
  return structuredClone(value);
}

function taskRows(board) {
  return Array.isArray(board?.tasks) ? board.tasks.filter((task) => task && typeof task === "object") : [];
}

function countBy(rows, key) {
  return rows.reduce((counts, row) => {
    const value = String(row?.[key] || "unknown");
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
}

export function validatePrivateBoard(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("private board must be an object");
  }
  if (!Array.isArray(value.tasks)) {
    throw new Error("private board must contain a tasks array");
  }
  return value;
}

export function privateBoardStore(storage) {
  return new ChunkedDurableStateStore(storage, () => ({
    schema_version: PRIVATE_BOARD_SCHEMA,
    portal: {},
    tasks: [],
  }), PRIVATE_BOARD_STORE_OPTIONS);
}

export async function loadPrivateBoard(storage) {
  const manifest = await storage.get(PRIVATE_BOARD_MANIFEST_KEY);
  const legacy = manifest == null ? await storage.get(PRIVATE_BOARD_LEGACY_KEY) : null;
  if (manifest == null && legacy == null) return null;
  const board = validatePrivateBoard(await privateBoardStore(storage).load());
  if (board.schema_version !== PRIVATE_BOARD_SCHEMA) {
    throw new Error("private board has an unsupported schema version");
  }
  return clone(board);
}

export async function savePrivateBoard(storage, board) {
  const value = clone(validatePrivateBoard({
    ...board,
    schema_version: PRIVATE_BOARD_SCHEMA,
  }));
  await privateBoardStore(storage).save(value);
  return value;
}

/**
 * Build the only board representation allowed on the public GitHub surface.
 *
 * The public file intentionally has no task rows. Exact IDs, titles, repos,
 * predicates, receipts, dispatch history, and assignment data remain in the
 * authenticated Durable Object. Counts are sufficient for public health and
 * progress surfaces; dispatch never consumes this projection.
 */
export function publicBoardProjection(board, now = new Date().toISOString()) {
  const rows = taskRows(board);
  const byStatus = countBy(rows, "status");
  const completed = (byStatus.done || 0) + (byStatus.archived || 0);
  return {
    schema_version: "limen.public_board_projection.v1",
    portal: {
      name: "Universal Task Intake",
      description: "Aggregate operational health; authenticated board details are private.",
      public_projection: {
        schema_version: "limen.public_board_projection.v1",
        generated_at: now,
        total: rows.length,
        completed,
        active: (byStatus.dispatched || 0) + (byStatus.in_progress || 0),
        completion_rate: Number((completed / Math.max(1, rows.length)).toFixed(3)),
        by_status: byStatus,
        by_priority: countBy(rows, "priority"),
      },
    },
    tasks: [],
  };
}

export function privateBoardStoreContract() {
  return clone(PRIVATE_BOARD_STORE_OPTIONS);
}

