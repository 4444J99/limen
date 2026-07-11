#!/usr/bin/env node
import { existsSync, readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicDir = join(__dirname, "..", "public");
const privateDir = join(__dirname, "..", ".generated", "surfaces");

function readJson(dir, name) {
  return JSON.parse(readFileSync(join(dir, name), "utf8"));
}

function fail(message) {
  console.error(`surface contract failed: ${message}`);
  process.exit(1);
}

for (const name of ["tasks.json", "client-status.json", "internal-status.json", "qa-status.json", "corpus-status.json", "observatory-status.json", "owner-surface-manifest.json", "client-surface-manifest.json", "readiness.json"]) {
  if (existsSync(join(publicDir, name))) fail(`${name} must not be hosted from public/`);
}

const tasks = readJson(privateDir, "tasks.json");
const publicStatus = readJson(publicDir, "public-status.json");
const clientStatus = readJson(privateDir, "client-status.json");
const internalStatus = readJson(privateDir, "internal-status.json");
const surfaceManifest = readJson(publicDir, "surface-manifest.json");
const ownerSurfaceManifest = readJson(privateDir, "owner-surface-manifest.json");
const clientSurfaceManifest = readJson(privateDir, "client-surface-manifest.json");
const publicSurfaceManifest = readJson(publicDir, "public-surface-manifest.json");
const prStatus = readJson(publicDir, "pr-status.json");
const readiness = readJson(privateDir, "readiness.json");
const qaStatus = readJson(privateDir, "qa-status.json");
const corpusStatus = readJson(privateDir, "corpus-status.json");
const observatoryStatus = readJson(privateDir, "observatory-status.json");

if (publicStatus.surface !== "public") fail("public-status.json has wrong surface");
if (clientStatus.surface !== "client") fail("client-status.json has wrong surface");
if (internalStatus.surface !== "internal") fail("internal-status.json has wrong surface");
if (qaStatus.surface !== "qa") fail("qa-status.json has wrong surface");
if (corpusStatus.surface !== "corpus") fail("corpus-status.json has wrong surface");
if (observatoryStatus.surface !== "observatory") fail("observatory-status.json has wrong surface");
if (!["ok", "missing"].includes(observatoryStatus.status)) fail("observatory-status.json has invalid status");
const observatoryText = JSON.stringify(observatoryStatus);
if (observatoryText.includes("dispatch_log")) fail("observatory status exposes dispatch logs");
if (observatoryText.includes('"context"')) fail("observatory status exposes task context");
if (observatoryText.includes('"urls"')) fail("observatory status exposes task URLs");
if (surfaceManifest.status !== "ok") fail("surface-manifest.json has wrong status");
if (ownerSurfaceManifest.status !== "ok") fail("owner-surface-manifest.json has wrong status");
if (clientSurfaceManifest.status !== "ok") fail("client-surface-manifest.json has wrong status");
if (publicSurfaceManifest.status !== "ok") fail("public-surface-manifest.json has wrong status");
if (!["ready", "degraded", "blocked"].includes(readiness.status)) fail("readiness.json has invalid status");

const publicText = JSON.stringify(publicStatus);
const clientText = JSON.stringify(clientStatus);
const qaText = JSON.stringify(qaStatus);
const corpusText = JSON.stringify(corpusStatus);

if ("tasks" in publicStatus) fail("public status exposes tasks");
if (publicText.includes("dispatch_log")) fail("public status exposes dispatch logs");
if (publicText.includes("context")) fail("public status exposes task context");
if (publicText.includes("urls")) fail("public status exposes task URLs");
if (!Array.isArray(prStatus.repos) || prStatus.repos.length !== 0) fail("pr-status.json must expose summary only");
if (typeof prStatus.summary?.prs_with_failing_ci !== "number") fail("pr-status.json missing failing CI aggregate");
if (JSON.stringify(prStatus).includes("html_url")) fail("pr-status.json exposes PR URLs");

for (const task of tasks.tasks || []) {
  if (task.title && publicText.includes(task.title)) fail(`public status leaks task title ${task.id}`);
  if (task.context && publicText.includes(task.context)) fail(`public status leaks task context ${task.id}`);
}

if (!Array.isArray(clientStatus.summary.active_tasks)) fail("client status missing active_tasks");
for (const key of ["recover", "verify", "assign", "archive", "archived"]) {
  if (typeof clientStatus.summary.lifecycle?.[key] !== "number") fail(`client status missing lifecycle.${key}`);
}
for (const task of clientStatus.summary.active_tasks) {
  if (!task.phase || !task.next_gate) fail(`client task ${task.id || "unknown"} missing lifecycle phase or next_gate`);
}
if (clientText.includes("dispatch_log")) fail("client status exposes dispatch logs");
if (clientText.includes('"context"')) fail("client status exposes task context fields");
if (clientText.includes('"urls"')) fail("client status exposes task URL fields");
if (qaText.includes("dispatch_log")) fail("qa status exposes dispatch logs");
if (qaText.includes('"context"')) fail("qa status exposes task context fields");
if (qaText.includes('"urls"')) fail("qa status exposes task URL fields");
if (!Array.isArray(qaStatus.steering?.next_batch)) fail("qa status missing next_batch");
if (!Array.isArray(qaStatus.steering?.archive_queue)) fail("qa status missing archive_queue");
if (!Array.isArray(qaStatus.mechanisms)) fail("qa status missing mechanisms");
if (corpusText.includes('"body_preview"')) fail("corpus status exposes body previews");
if (corpusText.includes('"body_object"')) fail("corpus status exposes body object paths");
if (corpusText.includes('"private_source_path"')) fail("corpus status exposes private source paths");
if (corpusText.includes('"private_display_path"')) fail("corpus status exposes private display paths");
if (corpusText.includes("dispatch_log")) fail("corpus status exposes dispatch logs");
if (corpusStatus.privacy?.contains_raw_text !== false) fail("corpus status must declare raw text absent");
if (!corpusStatus.coverage || typeof corpusStatus.coverage.units !== "number") fail("corpus status missing coverage");
if (!Array.isArray(corpusStatus.clusters) || !Array.isArray(corpusStatus.comparisons)) fail("corpus status missing atlas arrays");
const mechanisms = Object.fromEntries((qaStatus.mechanisms || []).map((mechanism) => [mechanism.id, mechanism]));
if (mechanisms["release-stale"]?.command !== "POST /api/release-stale?hours=24&dry_run=false") fail("qa release-stale mechanism command drifted");
if (mechanisms["qa-verify"]?.command !== "POST /api/tasks/{task_id}/verify") fail("qa verify mechanism command drifted");
if (mechanisms["qa-verify"]?.mode !== "human-approved evidence gate") fail("qa verify mechanism mode drifted");
if (mechanisms["assign-next"]?.command !== "POST /api/tasks/{task_id}/assign") fail("qa assign mechanism command drifted");
if (mechanisms["archive-done"]?.command !== "POST /api/tasks/{task_id}/archive") fail("qa archive mechanism command drifted");

if (!internalStatus.summary || typeof internalStatus.summary.total !== "number") fail("internal status missing summary");
if (internalStatus.summary.total !== (tasks.tasks || []).length) fail("internal status total does not match tasks");
if (publicStatus.summary.total !== (tasks.tasks || []).length) fail("public status total does not match tasks");
if (clientStatus.summary.total !== (tasks.tasks || []).length) fail("client status total does not match tasks");
if (qaStatus.lifecycle.total !== (tasks.tasks || []).length) fail("qa status total does not match tasks");

for (const surface of ["internal", "client", "public", "qa", "corpus", "observatory"]) {
  if (!ownerSurfaceManifest.contracts?.[surface]) fail(`owner manifest missing ${surface} contract`);
}
for (const surface of ownerSurfaceManifest.surfaces || []) {
  if (!surface.route || !surface.contract || !surface.disclosure) fail(`manifest surface ${surface.id || "unknown"} is incomplete`);
  if (!surface.persona || !Array.isArray(surface.sanctioned_personas)) fail(`manifest surface ${surface.id || "unknown"} is missing persona sanctions`);
}
const surfaceById = Object.fromEntries((ownerSurfaceManifest.surfaces || []).map((surface) => [surface.id, surface]));
if (JSON.stringify(surfaceById.internal?.sanctioned_personas) !== JSON.stringify(["owner"])) fail("internal surface is not owner-only");
if (JSON.stringify(surfaceById.qa?.sanctioned_personas) !== JSON.stringify(["owner"])) fail("qa surface is not owner-only");
if (JSON.stringify(surfaceById.corpus?.sanctioned_personas) !== JSON.stringify(["owner"])) fail("corpus surface is not owner-only");
if (JSON.stringify(surfaceById.observatory?.sanctioned_personas) !== JSON.stringify(["owner"])) fail("observatory surface is not owner-only");
if (!(surfaceById.client?.sanctioned_personas || []).includes("client")) fail("client surface is not sanctioned for client");
if (!(surfaceById.public?.sanctioned_personas || []).includes("public")) fail("public surface is not sanctioned for public");
if (ownerSurfaceManifest.contracts.public.includes_tasks !== false) fail("manifest says public includes tasks");
if (ownerSurfaceManifest.contracts.public.includes_dispatch_logs !== false) fail("manifest says public includes dispatch logs");
if (ownerSurfaceManifest.contracts.client.includes_dispatch_logs !== false) fail("manifest says client includes dispatch logs");
if (!ownerSurfaceManifest.contracts.readiness?.path) fail("manifest missing readiness contract");
if (ownerSurfaceManifest.contracts.qa.includes_dispatch_logs !== false) fail("manifest says qa includes dispatch logs");
if (ownerSurfaceManifest.contracts.qa.includes_task_context !== false) fail("manifest says qa includes task context");
if (ownerSurfaceManifest.contracts.qa.includes_task_urls !== false) fail("manifest says qa includes task urls");
if (!ownerSurfaceManifest.contracts.qa.verify_endpoint) fail("manifest missing qa verification endpoint");
if (!ownerSurfaceManifest.contracts.qa.assignment_endpoint) fail("manifest missing qa assignment endpoint");
if (!ownerSurfaceManifest.contracts.qa.archive_endpoint) fail("manifest missing qa archive endpoint");
if (ownerSurfaceManifest.contracts.corpus.includes_raw_text !== false) fail("manifest says corpus includes raw text");
if (ownerSurfaceManifest.contracts.corpus.includes_private_paths !== false) fail("manifest says corpus includes private paths");

const clientManifestIds = (clientSurfaceManifest.surfaces || []).map((surface) => surface.id).sort();
const publicManifestIds = (publicSurfaceManifest.surfaces || []).map((surface) => surface.id).sort();
const defaultManifestIds = (surfaceManifest.surfaces || []).map((surface) => surface.id).sort();
const ownerManifestIds = (ownerSurfaceManifest.surfaces || []).map((surface) => surface.id).sort();
if (JSON.stringify(ownerManifestIds) !== JSON.stringify(["client", "corpus", "internal", "observatory", "public", "qa"])) fail("owner manifest missing sanctioned surfaces");
if (JSON.stringify(clientManifestIds) !== JSON.stringify(["client", "public"])) fail("client manifest exposes unsanctioned surfaces");
if (JSON.stringify(publicManifestIds) !== JSON.stringify(["public"])) fail("public manifest exposes unsanctioned surfaces");
if (JSON.stringify(defaultManifestIds) !== JSON.stringify(["public"])) fail("default surface manifest is not public-filtered");
if (clientSurfaceManifest.contracts.internal || clientSurfaceManifest.contracts.qa || clientSurfaceManifest.contracts.corpus || clientSurfaceManifest.contracts.observatory || clientSurfaceManifest.contracts.readiness) fail("client manifest exposes owner contracts");
if (publicSurfaceManifest.contracts.internal || publicSurfaceManifest.contracts.qa || publicSurfaceManifest.contracts.corpus || publicSurfaceManifest.contracts.observatory || publicSurfaceManifest.contracts.client) fail("public manifest exposes non-public contracts");
if (surfaceManifest.contracts.internal || surfaceManifest.contracts.qa || surfaceManifest.contracts.corpus || surfaceManifest.contracts.observatory || surfaceManifest.contracts.client) fail("default manifest exposes non-public contracts");
if (publicSurfaceManifest.contracts.readiness || surfaceManifest.contracts.readiness) fail("public manifest exposes readiness contract");
if (ownerSurfaceManifest.persona !== "owner") fail("owner manifest missing persona");
if (clientSurfaceManifest.persona !== "client") fail("client manifest missing persona");
if (publicSurfaceManifest.persona !== "public") fail("public manifest missing persona");
if (surfaceManifest.persona !== "public") fail("default manifest missing public persona");
if (JSON.stringify(readiness).includes("dispatch_log")) fail("readiness exposes dispatch logs");
if (!Array.isArray(readiness.next_actions)) fail("readiness missing next_actions");

console.log("Surface contracts verified");
