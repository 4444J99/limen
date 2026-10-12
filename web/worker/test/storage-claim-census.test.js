import assert from "node:assert/strict";
import test from "node:test";
import { ConductKernel, emptyConductState } from "../src/conduct/keeper.js";

test("capabilities provide an authoritative empty census", () => {
  const kernel = new ConductKernel(emptyConductState(), { now: new Date("2026-10-12T19:00:00Z") });
  const census = kernel.capabilities().storage_claim_census;
  assert.equal(census.complete, true);
  assert.deepEqual(census.claims, []);
});

test("active local writers with missing claims fail census closed", () => {
  const kernel = new ConductKernel(emptyConductState(), { now: new Date("2026-10-12T19:00:00Z") });
  kernel.state.sessions.s = { capabilities: ["local-worktree"] };
  kernel.state.runs.r = {run_id: "r", executor_session_id: "s", packet: {effect: "write"}};
  kernel.state.leases.l = {lease_id: "l", run_id: "r", state: "active", hard_deadline: "2026-10-12T19:01:00Z"};
  assert.deepEqual(kernel.storageClaimCensus().denial_reasons, ["active_local_writer_without_claim"]);
});

test("duplicate conflicting claims never create a false complete census", () => {
  const kernel = new ConductKernel(emptyConductState(), { now: new Date("2026-10-12T19:00:00Z") });
  const claim = {claim_id: "claim", rollback_until: "2026-10-12T19:01:00Z", output_bytes: 1};
  kernel.state.runs.r = {run_id: "r", packet: {storage_envelope_claims: [claim, {...claim, output_bytes: 2}]}};
  assert.deepEqual(kernel.storageClaimCensus().denial_reasons, ["conflicting_storage_claim"]);
});
