#!/usr/bin/env node
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const appDir = join(__dirname, "..", "app");
const outDir = join(__dirname, "..", "out");

function fail(message) {
  console.error(`exported page validation failed: ${message}`);
  process.exit(1);
}

function readHtml(path) {
  return readFileSync(join(outDir, path), "utf8");
}

function readSource(path) {
  return readFileSync(join(appDir, path), "utf8");
}

function navLabels(html) {
  const nav = html.match(/<nav class="surfaceNav"[^>]*>([\s\S]*?)<\/nav>/);
  if (!nav) return [];
  return [...nav[1].matchAll(/<a [^>]*>([^<]+)<\/a>/g)].map((match) => match[1]);
}

function assertLabels(page, expected) {
  const labels = navLabels(readHtml(page));
  if (JSON.stringify(labels) !== JSON.stringify(expected)) {
    fail(`${page} nav labels ${JSON.stringify(labels)} did not match ${JSON.stringify(expected)}`);
  }
}

function assertIncludes(page, needles) {
  const html = readHtml(page);
  for (const needle of needles) {
    if (!html.includes(needle)) fail(`${page} missing ${needle}`);
  }
}

function assertNotIncludes(page, needles) {
  const html = readHtml(page);
  for (const needle of needles) {
    if (html.includes(needle)) fail(`${page} unexpectedly includes ${needle}`);
  }
}

function assertSourceNotIncludes(sourcePath, needles) {
  const source = readSource(sourcePath);
  for (const needle of needles) {
    if (source.includes(needle)) fail(`${sourcePath} unexpectedly includes ${needle}`);
  }
}

const ownerOnlyUiNeedles = [
  "../qa",
  "./qa",
  "RecoveryPanel",
  "VerifyPanel",
  "AssignmentPanel",
  "ArchivePanel",
  "/api/status",
  "/api/qa-status",
  "/api/readiness",
  "/corpus-status.json",
  "/api/tasks/",
  "/api/release-stale",
  "/api/dispatch",
  "Owner token",
  "Load QA",
  "Load internal",
];

assertLabels("index.html", ["Public"]);
assertLabels("internal.html", ["Internal", "QA", "Insights", "Corpus", "Observatory", "Client", "Public"]);
assertLabels("qa.html", ["Internal", "QA", "Insights", "Corpus", "Observatory", "Client", "Public"]);
assertLabels("corpus.html", ["Internal", "QA", "Insights", "Corpus", "Observatory", "Client", "Public"]);
assertLabels("observatory.html", ["Internal", "QA", "Insights", "Corpus", "Observatory", "Client", "Public"]);
assertLabels("client.html", ["Client", "Public"]);
assertLabels("public.html", ["Public"]);

const runtimeAttached = Boolean(process.env.NEXT_PUBLIC_API_URL);
if (runtimeAttached) {
  assertIncludes("index.html", ["Limen is tracking", "Run plan", "Unrecorded capacity"]);
  assertIncludes("internal.html", ["Owner access", "Owner token required", "Load internal"]);
  assertIncludes("client.html", ["Client token required", "Load client"]);
  assertIncludes("public.html", ["Public runtime refresh", "Unrecorded capacity", "Pull requests"]);
  assertIncludes("qa.html", ["Owner token required", "Load QA"]);
  assertIncludes("corpus.html", ["Corpus Command Center", "Prompt atlas"]);
  assertNotIncludes("client.html", ["Static snapshot only", "Build with NEXT_PUBLIC_API_URL to enable runtime refresh."]);
  assertNotIncludes("public.html", ["Static snapshot only", "Build with NEXT_PUBLIC_API_URL to enable runtime refresh."]);
} else {
  assertIncludes("index.html", ["Limen is tracking", "Run plan", "Unrecorded capacity"]);
  assertIncludes("internal.html", ["Runtime unavailable"]);
  assertIncludes("qa.html", ["Runtime unavailable"]);
  assertIncludes("corpus.html", ["Corpus Command Center", "Prompt atlas"]);
  assertIncludes("client.html", ["Runtime unavailable"]);
  assertIncludes("public.html", ["Static snapshot only", "Build with NEXT_PUBLIC_API_URL to enable runtime refresh."]);
}
assertIncludes("public.html", ["/public-surface-manifest.json"]);

assertNotIncludes("index.html", [">Internal</a>", ">QA</a>", ">Client</a>", "Client token", "Load internal", "Load QA"]);
assertNotIncludes("client.html", [">Internal</a>", ">QA</a>", ">Corpus</a>", "API verification unavailable", "API assignment unavailable", "API archive unavailable"]);
assertNotIncludes("public.html", [">Internal</a>", ">QA</a>", ">Corpus</a>", ">Client</a>", "Client token", "API verification unavailable", "API assignment unavailable", "API archive unavailable"]);
assertNotIncludes("client.html", ['href="/surface-manifest.json"']);
assertNotIncludes("public.html", ['href="/surface-manifest.json"']);
for (const page of ["index.html", "internal.html", "qa.html", "corpus.html", "observatory.html", "client.html", "public.html"]) {
  assertNotIncludes(page, ["LIMEN-015", "Propagate PR #234 completions", "dispatch_log", "/tasks.json", "/qa-status.json", "/client-status.json", "/internal-status.json", "/owner-surface-manifest.json", "/readiness.json", "/corpus-status.json", "/observatory-status.json"]);
}
assertSourceNotIncludes("lib/data.ts", [
  "tasks.json",
  "client-status.json",
  "internal-status.json",
  "qa-status.json",
  "owner-surface-manifest.json",
  "client-surface-manifest.json",
  "readiness.json",
]);
assertSourceNotIncludes("client/client-surface-client.tsx", ownerOnlyUiNeedles);
assertSourceNotIncludes("client/page.tsx", ownerOnlyUiNeedles);
assertSourceNotIncludes("public/page.tsx", [
  ...ownerOnlyUiNeedles,
  "Client token",
  "Load client",
  "/api/client-status",
]);
assertSourceNotIncludes("public-surface.tsx", [
  ...ownerOnlyUiNeedles,
  "Client token",
  "Load client",
  "/api/client-status",
]);

const qaShell = readSource("qa/qa-surface-client.tsx");
for (const panel of ["RecoveryPanel", "VerifyPanel", "AssignmentPanel", "ArchivePanel"]) {
  const pattern = new RegExp(`<${panel}[^>]*initialToken=\\{token\\}`);
  if (!pattern.test(qaShell)) {
    fail(`qa shell does not propagate owner token into ${panel}`);
  }
  const refreshPattern = new RegExp(`<${panel}[^>]*onComplete=\\{refreshAfterAction\\}`);
  if (!refreshPattern.test(qaShell)) {
    fail(`qa shell does not refresh lifecycle data after ${panel} actions`);
  }
}
for (const panelSource of ["qa/recovery-panel.tsx", "qa/verify-panel.tsx", "qa/assignment-panel.tsx", "qa/archive-panel.tsx"]) {
  if (!readSource(panelSource).includes("onComplete?.()")) {
    fail(`${panelSource} does not invoke lifecycle refresh callback after success`);
  }
}
const recoverySource = readSource("qa/recovery-panel.tsx");
if (!recoverySource.includes("releaseReady") || !recoverySource.includes("payload.candidates") || !recoverySource.includes("recoveryPreview")) {
  fail("recovery panel does not require preview candidates before release");
}
const archiveSource = readSource("qa/archive-panel.tsx");
if (!archiveSource.includes("confirmedId") || !archiveSource.includes("archiveReady") || !archiveSource.includes("Confirm closure")) {
  fail("archive panel does not require closure confirmation before archive");
}
const assignmentSource = readSource("qa/assignment-panel.tsx");
const verifySource = readSource("qa/verify-panel.tsx");
if (!assignmentSource.includes("useEffect") || !assignmentSource.includes("setAgent(selected.assignee") || !assignmentSource.includes("setPriority(selected.priority")) {
  fail("assignment panel does not reset steering intent when the selected task changes");
}
if (!verifySource.includes("useEffect") || !verifySource.includes("setStatus(\"done\")") || !verifySource.includes("setNote(\"\")")) {
  fail("verify panel does not clear verification intent when the selected task changes");
}
if (!archiveSource.includes("useEffect") || !archiveSource.includes("setConfirmedId(\"\")")) {
  fail("archive panel does not clear closure confirmation when the selected task changes");
}
if (!qaShell.includes("state.readiness.checks.map") || !qaShell.includes("state.readiness.next_actions.map")) {
  fail("qa shell does not render readiness checks and next actions");
}
if (!readSource("client/client-surface-client.tsx").includes("initialToken={token}")) {
  fail("client shell does not propagate client token into runtime refresh");
}
const clientSource = readSource("client/client-surface-client.tsx");
if (!clientSource.includes("summary.lifecycle") || !clientSource.includes("Current delivery gates")) {
  fail("client shell does not render lifecycle aggregate");
}
const dashboardSource = readSource("dashboard-client.tsx");
for (const needle of ["lifecycleGates", "getLifecycleGate", "getLifecycleGateLabel", "lifecycleBand", "gatePill"]) {
  if (!dashboardSource.includes(needle)) {
    fail(`owner dashboard does not preserve backend lifecycle gate model: missing ${needle}`);
  }
}

const corpusSource = readSource("corpus/corpus-command-center-client.tsx");
for (const needle of ['"body_preview"', '"body_object"', '"private_source_path"', "dispatch_log"]) {
  if (corpusSource.includes(needle)) {
    fail(`corpus client source unexpectedly references private field ${needle}`);
  }
}
console.log("Exported page persona/runtime checks verified");
assertLabels("insights.html", ["Internal", "QA", "Insights", "Corpus", "Observatory", "Client", "Public"]);

// Assert every exported page has a non-empty, unique <title> tag.
// This catches regressions where a route loses its per-route metadata.
const exportedPages = [
  "index.html",
  "qa.html",
  "client.html",
  "public.html",
  "internal.html",
  "insights.html",
  "corpus.html",
  "observatory.html",
];

function extractTitle(html) {
  const m = html.match(/<title>([^<]*)<\/title>/);
  return m ? m[1].trim() : "";
}

const seenTitles = new Map();
for (const page of exportedPages) {
  const html = readHtml(page);
  const title = extractTitle(html);
  if (!title) {
    fail(`${page} has an empty <title>`);
  }
  if (seenTitles.has(title)) {
    fail(`${page} has duplicate <title> "${title}" (already seen in ${seenTitles.get(title)})`);
  }
  seenTitles.set(title, page);
}
console.log(`Page title uniqueness verified: ${exportedPages.length} pages, ${seenTitles.size} unique titles`);
