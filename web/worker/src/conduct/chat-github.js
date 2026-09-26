// Deterministic GitHub execution. Source payloads never enter public conduct graphs.
import { configuredConductPrincipals } from "./auth.js";
import { ConductError } from "./keeper.js";
import { canonicalHash, validateSession, validateWorkPacket, validateReceipt, validateExecutorAttempt } from "./schemas.js";

const SHA = /^[0-9a-f]{40}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/;
const REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const enc = new TextEncoder();
const TERMINAL = new Set(["merged", "pr_created", "failed", "blocked", "expired", "cancelled"]);
const pathUrl = path => path.split("/").map(encodeURIComponent).join("/");
const fail = (code, status = 409) => { throw new ConductError(code, status); };
const exactKeys = (value, keys) => value && typeof value === "object" && !Array.isArray(value)
  && Object.keys(value).every(key => keys.includes(key));
const covered = (path, prefixes) => prefixes.some(prefix => prefix === "." || path === prefix || path.startsWith(`${prefix}/`));

export function safeChatPath(path, mutation = true) {
  return typeof path === "string" && path.length <= 512 && !/[\\\x00-\x1f\x7f]/.test(path)
    && path.split("/").every(part => part && ![".", "..", ".git"].includes(part.toLowerCase()))
    && !path.startsWith(".limen-private/")
    && (!mutation || (!path.split("/").some(part => ["AGENTS.md", "CLAUDE.md", "GEMINI.md"].includes(part))
      && path !== "tasks.yaml" && ![".github/", "institutio/", "spec/contracts/"].some(prefix => path.startsWith(prefix))));
}

export function validateChanges(input) {
  if (!exactKeys(input, ["session_id", "request_id", "repository", "base_sha", "intent", "changes", "verification_profile", "landing"])
      || !ID.test(input.request_id || "") || !ID.test(input.session_id || "") || !REPO.test(input.repository || "")
      || !SHA.test(input.base_sha || "") || !ID.test(input.verification_profile || "")
      || !["pr", "merge"].includes(input.landing) || typeof input.intent !== "string"
      || !input.intent.trim() || input.intent.length > 1000 || !Array.isArray(input.changes)
      || input.changes.length < 1 || input.changes.length > 64) fail("chat_change_invalid", 422);
  let bytes = 0;
  const paths = new Set();
  for (const change of input.changes) {
    if (!exactKeys(change, ["path", "expected_blob_sha", "content"]) || !safeChatPath(change.path)
        || paths.has(change.path) || !(change.expected_blob_sha === null || SHA.test(change.expected_blob_sha || ""))
        || !(change.content === null || typeof change.content === "string")
        || (change.content === null && change.expected_blob_sha === null)) fail("chat_change_invalid", 422);
    if (typeof change.content === "string") {
      if (change.content.includes("\0") || !change.content.isWellFormed()) fail("chat_utf8_required", 422);
      bytes += enc.encode(change.content).length;
    }
    paths.add(change.path);
  }
  if (bytes > 256 * 1024) fail("chat_change_too_large", 413);
  return structuredClone(input);
}

export function chatConfiguration(env) {
  let config;
  try { config = JSON.parse(env.LIMEN_CHAT_GITHUB || "null"); } catch { fail("chat_configuration_invalid", 503); }
  if (config?.schema_version !== "limen.chat_github.v1" || !config.enabled
      || !REPO.test(config.control_repository || "") || !SHA.test(config.control_sha || "")
      || config.control_ref !== "main" || !Number.isSafeInteger(config.workflow_id)
      || !Array.isArray(config.grants) || !env.LIMEN_CHAT_GITHUB_TOKEN) fail("chat_not_provisioned", 503);
  const entry = configuredConductPrincipals(env).find(item => item.principal.principal_id === config.executor_principal_id);
  if (!entry || entry.principal.agent !== "github_actions" || !entry.principal.roles.includes("executor")
      || entry.principal.roles.includes("compatibility")) fail("chat_executor_not_provisioned", 503);
  return { ...config, executor: entry.principal };
}

export class ChatGithubController {
  constructor(ctx, env, service, request = fetch) {
    this.ctx = ctx; this.env = env; this.service = service; this.request = request;
    this.tail = Promise.resolve();
  }

  serial(fn) {
    const next = this.tail.then(fn);
    this.tail = next.catch(() => {});
    return next;
  }

  async github(path, method = "GET", body = undefined, missing = false) {
    const response = await this.request(`https://api.github.com${path}`, {
      method, redirect: "manual", signal: AbortSignal.timeout(10000),
      headers: { authorization: `Bearer ${this.env.LIMEN_CHAT_GITHUB_TOKEN}`, "user-agent": "limen-chat-github",
        accept: "application/vnd.github+json", "content-type": "application/json", "x-github-api-version": "2022-11-28" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (missing && response.status === 404) return null;
    if (!response.ok) { await response.body?.cancel(); fail(`chat_github_http_${response.status}`, 502); }
    if (response.status === 204) return null;
    const reader = response.body.getReader(), chunks = [];
    let size = 0;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4 * 1024 * 1024) { await reader.cancel(); fail("chat_github_response_too_large", 502); }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  grant(config, principal, repository) {
    const grant = config.grants.find(item => item.principal_id === principal.principal_id && item.repository === repository);
    if (!grant || !Array.isArray(grant.path_prefixes) || !Array.isArray(grant.profiles)
        ) fail("chat_repository_not_authorized", 403);
    return grant;
  }

  async read(principal, body) {
    const config = chatConfiguration(this.env);
    if (!exactKeys(body, ["repository", "ref", "path", "pull_request"]) || !REPO.test(body.repository || "")) fail("chat_read_invalid", 422);
    const grant = this.grant(config, principal, body.repository);
    const repo = await this.github(`/repos/${body.repository}`);
    if (repo.private) fail("chat_private_runner_unverified", 403);
    if (body.pull_request !== undefined) {
      if (!Number.isSafeInteger(body.pull_request) || body.pull_request < 1) fail("chat_read_invalid", 422);
      const pr = await this.github(`/repos/${body.repository}/pulls/${body.pull_request}`);
      return { repository: body.repository, number: pr.number, state: pr.state, head: pr.head.sha,
        base: pr.base.sha, merged: pr.merged, merge_commit_sha: pr.merge_commit_sha, url: pr.html_url };
    }
    if (typeof body.ref !== "string" || !(SHA.test(body.ref) || body.ref === repo.default_branch)) fail("chat_exact_ref_required", 422);
    const commit = await this.github(`/repos/${body.repository}/commits/${encodeURIComponent(body.ref)}`);
    if (body.path === undefined) {
      const tree = await this.github(`/repos/${body.repository}/git/trees/${commit.commit.tree.sha}?recursive=1`);
      if (tree.truncated) fail("chat_tree_truncated", 422);
      return { repository: body.repository, commit: commit.sha,
        files: tree.tree.filter(item => covered(item.path, grant.path_prefixes)).map(({ path, sha, mode, type }) => ({ path, sha, mode, type })) };
    }
    if (!safeChatPath(body.path, false) || !covered(body.path, grant.path_prefixes)) fail("chat_path_not_authorized", 403);
    const file = await this.github(`/repos/${body.repository}/contents/${pathUrl(body.path)}?ref=${commit.sha}`);
    if (file.type !== "file" || file.encoding !== "base64" || file.size > 256 * 1024) fail("chat_regular_text_required", 422);
    const bytes = Uint8Array.from(atob(file.content.replace(/\s/g, "")), char => char.charCodeAt(0));
    let content;
    try { content = new TextDecoder("utf-8", { fatal: true }).decode(bytes); } catch { fail("chat_regular_text_required", 422); }
    return { repository: body.repository, commit: commit.sha, path: body.path, blob_sha: file.sha, content };
  }

  async submit(principal, raw) {
    const input = validateChanges(raw), config = chatConfiguration(this.env);
    const grant = this.grant(config, principal, input.repository);
    if (!principal.roles.includes("conductor") || principal.agent !== "chatgpt" || principal.surface !== "chat") fail("chat_conductor_required", 403);
    if (!grant.profiles.includes(input.verification_profile) || (input.landing === "merge" && grant.merge !== true)
        || input.changes.some(change => !covered(change.path, grant.path_prefixes))) fail("chat_change_not_authorized", 403);
    const digest = await canonicalHash(input);
    const key = `chat:request:${await canonicalHash([principal.principal_id, input.request_id])}`;
    const prior = await this.ctx.storage.get(key);
    if (prior) {
      if (prior.digest !== digest) fail("chat_request_reused");
      if (!TERMINAL.has(prior.phase)) {
        await this.ctx.storage.put("chat:active", key);
        await this.ctx.storage.setAlarm(Date.now() + 1000);
      }
      return this.summary(prior);
    }
    const activeKey = await this.ctx.storage.get("chat:active");
    const active = activeKey && await this.ctx.storage.get(activeKey);
    if (active && !TERMINAL.has(active.phase)) fail("chat_executor_busy");
    const repo = await this.github(`/repos/${input.repository}`);
    if (repo.private) fail("chat_private_runner_unverified", 403);
    const ancestry=await this.github(`/repos/${input.repository}/compare/${input.base_sha}...${encodeURIComponent(repo.default_branch)}`);
    if(!["ahead","identical"].includes(ancestry.status)) fail("chat_base_not_in_default_history");
    const control = await this.github(`/repos/${config.control_repository}/branches/main`);
    const workflow = await this.github(`/repos/${config.control_repository}/actions/workflows/${config.workflow_id}`);
    if (control.commit.sha !== config.control_sha || !control.protected || workflow.state !== "active"
        || workflow.path !== ".github/workflows/limen-chat-patch.yml") fail("chat_control_not_ready", 503);
    const profiles = await this.github(`/repos/${config.control_repository}/contents/institutio/governance/chat-github-profiles.json?ref=${config.control_sha}`);
    const profileDoc = JSON.parse(atob(profiles.content.replace(/\s/g, "")));
    const profile = profileDoc.profiles?.[input.verification_profile];
    if (!profile || profile.repository !== input.repository || input.changes.some(change => !covered(change.path, profile.paths))) fail("chat_profile_unavailable", 422);
    const base = await this.github(`/repos/${input.repository}/git/commits/${input.base_sha}`);
    const tree = await this.github(`/repos/${input.repository}/git/trees/${base.tree.sha}?recursive=1`);
    if (tree.truncated) fail("chat_tree_truncated", 422);
    const treeByPath = new Map(tree.tree.map(item => [item.path, item]));
    for (const change of input.changes) {
      const old = treeByPath.get(change.path);
      if ((old?.sha ?? null) !== change.expected_blob_sha || (old && (old.type !== "blob" || !["100644", "100755"].includes(old.mode)))) fail("chat_old_blob_mismatch");
      // A parent symlink/submodule/file must not be converted into a directory.
      const parents = change.path.split("/"); parents.pop();
      while (parents.length) {
        const parent = treeByPath.get(parents.join("/"));
        if (parent && parent.type !== "tree") fail("chat_unsafe_parent", 422);
        parents.pop();
      }
    }
    const sessionId = "github-actions-chat-controller";
    await this.service.call("register", { principal: config.executor, session: validateSession({
      session_id: sessionId, identity: { agent: config.executor.agent, surface: config.executor.surface, session_id: sessionId },
      origin: "relay", capabilities: ["chat-file-changes"], transport: "github-actions", concurrency: 1,
      accepting_work: true, native_run_id: null, meter: "github-actions-minutes",
    }) });
    const capabilities = await this.service.call("capabilities");
    const session = capabilities.sessions?.find(item => item.session_id === input.session_id);
    if (!session) fail("chat_session_not_registered", 409);
    const branch = `chat/${digest.slice(0, 24)}`;
    const now = new Date(), deadline = new Date(now.getTime() + 14 * 60000).toISOString();
    const packet = await validateWorkPacket({ work_id: `chat-${digest}`, work_key: input.request_id,
      initiator: session.identity, conductor: session.identity,
      intent: { kind: "chat-file-changes", request_digest: digest },
      execution: { adapter: "chat-file-changes", owner_repository: input.repository, exact_base: input.base_sha,
        topic_branch: branch, change_digest: digest, control_sha: config.control_sha,
        verification_profile: input.verification_profile, profile_digest: await canonicalHash(profile), landing: input.landing },
      required_capabilities: ["chat-file-changes"], preferred_agent: "github_actions",
      resource_claims: [{ key: `repo/${input.repository}/write`, mode: "exclusive" }],
      predicate: `python3 scripts/chat-github-runner.py verify --profile ${input.verification_profile}`,
      receipt_target: `github:${input.repository}:pull-request:${branch}`,
      work_loan: { source_origin: "human_prompt", horizon: "present", value_case: "Execute an authorized Chat-authored change",
        owner_surface: `github:${input.repository}`, budget_cost: 1 },
      authority: { actions: ["code.write", "code.verify", "pull-request.create", ...(input.landing === "merge" ? ["pull-request.merge"] : [])],
        repositories: [input.repository.toLowerCase()], path_prefixes: input.changes.map(change => change.path),
        external_effects: ["github"], may_delegate: false },
      deadline, spend: { unit: "runs", limit: 1, reserve: 1 }, retry: { max_attempts: 1 }, effect: "write",
    });
    // Persist private input before canonical admission; no file contents enter the packet.
    for (let index = 0; index < input.changes.length; index++) {
      const text = JSON.stringify(input.changes[index]);
      for (let offset = 0; offset < text.length; offset += 12000) {
        await this.ctx.storage.put(`${key}:file:${index}:${offset / 12000}`, text.slice(offset, offset + 12000));
      }
    }
    const record = { key, digest, principal_id: principal.principal_id, repository: input.repository, base_sha: input.base_sha,
      base_tree: base.tree.sha, branch, landing: input.landing, profile: input.verification_profile,
      control_sha: config.control_sha, control_repository: config.control_repository, workflow_id: config.workflow_id,
      profile_digest: packet.execution.profile_digest, sandbox_image:profile.image, created_at: now.toISOString(), deadline, count: input.changes.length,
      modes: input.changes.map(change => treeByPath.get(change.path)?.mode || "100644"), entries: [],
      packet, run_id: null, lease: null, phase: "admitting" };
    await this.ctx.storage.put(key, record);
    await this.ctx.storage.put("chat:active", key);
    await this.ctx.storage.setAlarm(Date.now() + 1000);
    await this.admit(record, principal);
    return this.summary(record);
  }

  async admit(record, principal) {
    // The identical packet survives a crash after canonical admission but before
    // the local run index is saved. Canonical submit then returns its duplicate.
    const admitted = await this.service.call("submit", { principal, packet: record.packet });
    if (admitted.status === "busy") fail("chat_executor_busy");
    record.run_id = admitted.run_id; record.lease = admitted.lease; record.phase = "prepared";
    await this.ctx.storage.put(`chat:run:${record.run_id}`, record.key);
    await this.ctx.storage.put(record.key, record);
  }

  summary(record) {
    return { schema_version: "limen.chat_change_result.v1", run_id: record.run_id, phase: record.phase,
      repository: record.repository, head: record.head ?? null, workflow_run_id: record.workflow_run_id ?? null,
      complete: record.phase === "merged" || (record.landing === "pr" && record.phase === "pr_created"), error: record.error ?? null };
  }

  async file(record, index) {
    let text = "";
    for (let part = 0; part < 100; part++) {
      const value = await this.ctx.storage.get(`${record.key}:file:${index}:${part}`);
      if (value === undefined) break;
      text += value;
    }
    return JSON.parse(text);
  }

  async node(record) {
    const graph = await this.service.call("graph", { run_id: record.run_id });
    return graph.nodes.find(node => node.run_id === record.run_id);
  }

  async activeLease(record, principal, attemptStatus) {
    const node = await this.node(record);
    if(node.status==="stop_requested" && !["blocked","failed"].includes(attemptStatus)) fail("chat_stop_requested");
    if(attemptStatus === "running" && node.attempts?.some(attempt=>attempt.status==="succeeded")) attemptStatus="succeeded";
    const claim = await this.service.call("claim", { lease_id: node.lease.lease_id, generation: node.lease.generation, principal });
    const heartbeat=await this.service.call("heartbeat", { lease_id: node.lease.lease_id, generation: node.lease.generation,
      capability_token: claim.capability_token, principal, observed_heads: {},
      ...(attemptStatus ? {attempt: validateExecutorAttempt({
        attempt_id: `chat-${record.digest}`, run_id:record.run_id,lease_id:node.lease.lease_id,
        lease_generation:node.lease.generation,executor:node.lease.executor,adapter:"github-actions-chat",
        status:attemptStatus,submitted_at:record.created_at,updated_at:new Date().toISOString(),
        provider_run_id:record.workflow_run_id ? String(record.workflow_run_id) : null,
        provider_run_url:record.workflow_run_id ? `https://github.com/${record.control_repository}/actions/runs/${record.workflow_run_id}` : null,
        failure_class:["failed","blocked"].includes(attemptStatus)?"permanent":null,
      })} : {}) });
    if(heartbeat.status!=="active" || heartbeat.lease.lease_id!==node.lease.lease_id) fail("chat_lease_fenced");
    return { node, claim };
  }

  async alarm() {
    const key = await this.ctx.storage.get("chat:active");
    if (!key) return;
    const record = await this.ctx.storage.get(key);
    if (!record || TERMINAL.has(record.phase)) return;
    try {
      const config = chatConfiguration(this.env);
      // Re-arm before awaits: Cloudflare may interrupt at any external boundary.
      await this.ctx.storage.setAlarm(Date.now() + 30000);
      if (record.phase === "admitting") {
        const principal = configuredConductPrincipals(this.env).find(entry=>entry.principal.principal_id===record.principal_id)?.principal;
        if (!principal) fail("chat_principal_removed",403);
        await this.admit(record,principal);
      }
      const node = await this.node(record);
      if (["succeeded","failed","blocked","expired","cancelled","fenced"].includes(node.status)) {
        record.phase = node.status === "succeeded" ? record.terminal_phase || "blocked" : node.status === "fenced" ? "blocked" : node.status;
        await this.ctx.storage.put(key,record); return;
      }
      if (Date.now() >= Date.parse(record.deadline) - 15000) {
        return await this.terminate(record,config.executor,"blocked","chat_original_deadline_exhausted");
      }
      if (["dispatched","dispatch_unobserved","running","queued"].includes(record.phase)) {
        return await this.reconcile(record,config.executor);
      }
      if (config.control_sha !== record.control_sha) fail("chat_control_changed");
      await this.activeLease(record, config.executor);
      if (["prepared", "blobs"].includes(record.phase)) {
        const end = Math.min(record.count, record.entries.length + 4);
        for (let index = record.entries.length; index < end; index++) {
          const file = await this.file(record, index);
          const blob = file.content === null ? null : await this.github(`/repos/${record.repository}/git/blobs`, "POST", { content: file.content, encoding: "utf-8" });
          record.entries.push({ path: file.path, mode: record.modes[index], type: "blob", sha: blob?.sha ?? null });
          record.phase = "blobs"; await this.ctx.storage.put(key, record);
        }
        if (record.entries.length === record.count) record.phase = "commit";
      } else if (record.phase === "commit") {
        const tree = await this.github(`/repos/${record.repository}/git/trees`, "POST", { base_tree: record.base_tree, tree: record.entries });
        if (tree.sha === record.base_tree) fail("chat_no_change");
        const identity = { name: "Limen Chat", email: "noreply@users.noreply.github.com", date: record.created_at };
        const commit = await this.github(`/repos/${record.repository}/git/commits`, "POST", {
          tree: tree.sha, parents: [record.base_sha], message: `Chat change ${record.digest}`, author: identity, committer: identity,
        });
        record.head = commit.sha; record.phase = "ref";
      } else if (record.phase === "ref") {
        const prior = await this.github(`/repos/${record.repository}/git/ref/heads/${record.branch}`, "GET", undefined, true);
        if (prior && prior.object.sha !== record.head) fail("chat_branch_conflict");
        if (!prior) await this.github(`/repos/${record.repository}/git/refs`, "POST", { ref: `refs/heads/${record.branch}`, sha: record.head });
        record.phase = "dispatch";
      } else {
        const control = await this.github(`/repos/${record.control_repository}/branches/main`);
        if (control.commit.sha !== record.control_sha || !control.protected) fail("chat_control_changed");
        // The durable marker precedes the external write. An ambiguous response is never retried.
        record.phase = "dispatch_unobserved"; await this.ctx.storage.put(key, record);
        await this.activeLease(record,config.executor,"launching");
        await this.github(`/repos/${record.control_repository}/actions/workflows/${record.workflow_id}/dispatches`, "POST", {
          ref: "main", inputs: { run_id: record.run_id, control_sha: record.control_sha },
        });
        record.phase = "dispatched";
      }
      await this.ctx.storage.put(key, record);
      if (["blobs", "commit", "ref", "dispatch"].includes(record.phase)) await this.ctx.storage.setAlarm(Date.now() + 1000);
    } catch (error) {
      record.error = error instanceof ConductError ? error.message : "chat_external_outcome_unobserved";
      if(Date.now() >= Date.parse(record.deadline)) record.phase="expired";
      await this.ctx.storage.put(key, record);
      if (record.phase !== "dispatch_unobserved") {
        try { await this.terminate(record,chatConfiguration(this.env).executor,"blocked",record.error); }
        catch { /* Original alarm is still armed; canonical expiry remains authoritative. */ }
      }
    }
  }

  async reconcile(record, principal) {
    if (!record.workflow_run_id) {
      const page = await this.github(`/repos/${record.control_repository}/actions/workflows/${record.workflow_id}/runs?event=workflow_dispatch&per_page=100`);
      const runs = page.workflow_runs?.filter(run=>run.display_title===`chat:${record.run_id}`) || [];
      if (runs.length > 1) return this.terminate(record,principal,"blocked","chat_dispatch_ambiguous");
      if (!runs.length) return; // Bounded by the original deadline; never redispatch.
      record.workflow_run_id = runs[0].id; await this.ctx.storage.put(record.key,record);
    }
    const identity = {workflow_run_id:record.workflow_run_id,run_attempt:1};
    await this.executorContext(principal,record.run_id,identity);
    if (record.pull_request && record.verification) {
      return this.complete(principal,record.run_id,{...identity,pull_request:record.pull_request,verification:record.verification});
    }
    const run = await this.github(`/repos/${record.control_repository}/actions/runs/${record.workflow_run_id}`);
    if (run.status === "completed") return this.terminate(record,principal,"failed","chat_workflow_ended_without_landing_receipt");
  }

  async terminate(record, principal, outcome, detail) {
    if (!record.run_id) {
      record.phase="blocked";record.error=detail;await this.ctx.storage.put(record.key,record);return this.summary(record);
    }
    const {node,claim}=await this.activeLease(record,principal,outcome==="cancelled"?"blocked":outcome);
    const receipt=validateReceipt({receipt_id:`chat-${outcome}-${record.digest}`,run_id:record.run_id,
      lease_id:node.lease.lease_id,lease_generation:node.lease.generation,executor:node.lease.executor,
      predicate:{command:node.packet.predicate,exit_code:1,summary:detail},outcome,
      provider_identity:"github_actions",provider_run_url:record.workflow_run_id?`https://github.com/${record.control_repository}/actions/runs/${record.workflow_run_id}`:null,
      changed_paths:record.head?record.entries.map(entry=>entry.path):[],
      observed_heads_before:{[record.repository]:record.base_sha},observed_heads_after:{[record.repository]:record.head||record.base_sha},
      spend:{runs:record.workflow_run_id?1:0,inference_provider_runs:0}});
    await this.service.call("report",{lease_id:node.lease.lease_id,generation:node.lease.generation,capability_token:claim.capability_token,principal,receipt});
    record.phase=outcome;record.error=detail;await this.ctx.storage.put(record.key,record);return this.summary(record);
  }

  async executorContext(principal, runId, body) {
    const config = chatConfiguration(this.env);
    if (principal.principal_id !== config.executor.principal_id) fail("chat_executor_required", 403);
    const key = await this.ctx.storage.get(`chat:run:${runId}`), record = key && await this.ctx.storage.get(key);
    if (!record || !["dispatched", "dispatch_unobserved", "running", "queued"].includes(record.phase)) fail("chat_run_not_dispatched");
    if (!Number.isSafeInteger(body.workflow_run_id) || body.run_attempt !== 1) fail("chat_run_identity_invalid");
    const run = await this.github(`/repos/${record.control_repository}/actions/runs/${body.workflow_run_id}`);
    if (run.workflow_id !== record.workflow_id || run.head_sha !== record.control_sha || run.event !== "workflow_dispatch"
        || run.head_branch !== "main" || run.run_attempt !== 1 || run.display_title !== `chat:${record.run_id}`
        || (record.workflow_run_id && record.workflow_run_id !== run.id)) fail("chat_run_identity_mismatch");
    record.workflow_run_id = run.id;
    const { node } = await this.activeLease(record, principal,"running");
    if(record.phase !== "queued") record.phase = "running";
    await this.ctx.storage.put(key, record);
    return { run_id: record.run_id, repository: record.repository, base_sha: record.base_sha, head: record.head,
      branch: record.branch, profile: record.profile, profile_digest: record.profile_digest, landing: record.landing,
      control_sha: record.control_sha, control_repository: record.control_repository, deadline: record.deadline,
      digest: record.digest, sandbox_image:record.sandbox_image,packet: node.packet, lease: node.lease };
  }

  async verifiedContext(principal, runId, body) {
    const context = await this.executorContext(principal, runId, body);
    const jobs = await this.github(`/repos/${context.control_repository}/actions/runs/${body.workflow_run_id}/attempts/1/jobs?per_page=100`);
    const verifier = jobs.jobs?.find(job => job.name === "verify");
    if (!verifier || verifier.conclusion !== "success" || !(verifier.runner_id > 0)
        || !verifier.steps?.some(step => step.name === "Run isolated verification" && step.conclusion === "success")) fail("chat_verification_unproved");
    const verification=body.verification;
    if (!exactKeys(verification,["schema_version","run_id","head","profile_digest","control_sha","workflow_run_id","run_attempt","exit_code","output_sha256","inference_provider_runs","sandbox_image"])
        || verification.schema_version!=="limen.chat_verification.v1" || verification.run_id!==runId
        || verification.head!==context.head || verification.control_sha!==context.control_sha
        || verification.profile_digest!==context.profile_digest || verification.workflow_run_id!==body.workflow_run_id
        || verification.run_attempt!==1 || verification.exit_code!==0 || verification.inference_provider_runs!==0
        || verification.sandbox_image!==context.sandbox_image
        || !/^[0-9a-f]{64}$/.test(verification.output_sha256 || "")) fail("chat_artifact_identity_mismatch");
    const digest=await canonicalHash(verification);
    const artifacts=await this.github(`/repos/${context.control_repository}/actions/runs/${body.workflow_run_id}/artifacts?per_page=100`);
    const matches=artifacts.artifacts?.filter(item=>item.name===`chat-verification-${digest}`) || [];
    if(matches.length!==1 || matches[0].expired || !/^sha256:[0-9a-f]{64}$/.test(matches[0].digest || "")
        || matches[0].size_in_bytes>131072 || matches[0].workflow_run?.id!==body.workflow_run_id
        || matches[0].workflow_run?.head_sha!==context.control_sha) fail("chat_artifact_unproved");
    context.verification_artifact={id:matches[0].id,digest:matches[0].digest,attestation_digest:digest};
    return context;
  }

  async publish(principal, runId, body) {
    const context = await this.verifiedContext(principal, runId, body);
    const ref = await this.github(`/repos/${context.repository}/git/ref/heads/${context.branch}`);
    if (ref.object.sha !== context.head) fail("chat_pr_head_mismatch");
    const repo = await this.github(`/repos/${context.repository}`);
    const pulls = await this.github(`/repos/${context.repository}/pulls?state=all&head=${encodeURIComponent(context.repository.split("/")[0] + ":" + context.branch)}&per_page=100`);
    if (pulls.length > 1) fail("chat_pr_ambiguous");
    if (pulls.length) return pulls[0];
    // Repeated calls discover the unique deterministic branch before publication.
    return this.github(`/repos/${context.repository}/pulls`, "POST", {
      title:`Chat change ${context.digest.slice(0,12)}`,head:context.branch,base:repo.default_branch,
      body:`Chat-authored deterministic execution. Run: ${runId}. Exact head: ${context.head}.`,
    });
  }

  async complete(principal, runId, body) {
    const replay=await this.terminalReplay(principal,runId,body);
    if(replay) return replay;
    const context = await this.verifiedContext(principal, runId, body);
    const key = await this.ctx.storage.get(`chat:run:${runId}`), record = await this.ctx.storage.get(key);
    if (!Number.isSafeInteger(body.pull_request) || body.pull_request < 1) fail("chat_pr_required");
    const pr = await this.github(`/repos/${context.repository}/pulls/${body.pull_request}`);
    const repository = await this.github(`/repos/${context.repository}`);
    if (pr.head.sha !== context.head || pr.head.ref !== context.branch || pr.head.repo?.full_name !== context.repository
        || pr.base.repo?.full_name !== context.repository || pr.base.ref !== repository.default_branch) fail("chat_pr_head_mismatch");
    record.pull_request=body.pull_request;record.verification=body.verification;
    await this.ctx.storage.put(key,record);
    if (context.landing === "merge" && !pr.merged) {
      record.phase = "queued";
      await this.ctx.storage.put(key, record);
      await this.ctx.storage.setAlarm(Date.now()+30000);
      return this.summary(record);
    }
    if (pr.merged) {
      if (!SHA.test(pr.merge_commit_sha || "")) fail("chat_merge_unproved");
      const comparison = await this.github(`/repos/${context.repository}/compare/${pr.merge_commit_sha}...${encodeURIComponent(repository.default_branch)}`);
      if (!["ahead", "identical"].includes(comparison.status)) fail("chat_default_ancestry_unproved");
    }
    record.terminal_phase=pr.merged?"merged":"pr_created";
    await this.ctx.storage.put(key,record);
    const { node, claim } = await this.activeLease(record, principal,"succeeded");
    const receipt = validateReceipt({ receipt_id: `chat-${record.digest}`, run_id: runId,
      lease_id: node.lease.lease_id, lease_generation: node.lease.generation, executor: node.lease.executor,
      predicate: { command: node.packet.predicate, exit_code: 0, summary: "Exact-head isolated GitHub Actions verification" },
      outcome: "succeeded", provider_identity: "github_actions", provider_run_url: `https://github.com/${context.control_repository}/actions/runs/${body.workflow_run_id}`,
      observed_heads_before: { [context.repository]: context.base_sha }, observed_heads_after: { [context.repository]: context.head },
      changed_paths: record.entries.map(entry => entry.path), checks: [
        { name: "pull-request", status: "success", url: pr.html_url, head: context.head },
        { name: "exact-diff", status: "success", url: pr.html_url, head: record.digest },
        { name: "verification-artifact",status:"success",url:`https://github.com/${context.control_repository}/actions/runs/${body.workflow_run_id}/artifacts/${context.verification_artifact.id}`,head:context.verification_artifact.digest },
        { name: "verification-attestation",status:"success",head:context.verification_artifact.attestation_digest },
        ...(pr.merged ? [{ name: "merge", status: "success", url: pr.html_url, head: pr.merge_commit_sha }] : []),
      ], spend: { runs:1,inference_provider_runs: 0 },
    });
    await this.service.call("report", { lease_id: node.lease.lease_id, generation: node.lease.generation,
      capability_token: claim.capability_token, principal, receipt });
    record.phase = pr.merged ? "merged" : "pr_created"; await this.ctx.storage.put(key, record);
    return this.summary(record);
  }

  async failed(principal, runId, body) {
    const replay=await this.terminalReplay(principal,runId,body);
    if(replay) return replay;
    const context = await this.executorContext(principal, runId, body);
    const jobs = await this.github(`/repos/${context.control_repository}/actions/runs/${body.workflow_run_id}/attempts/1/jobs?per_page=100`);
    const failedJob = jobs.jobs?.find(job => ["prepare","verify","publish"].includes(job.name) && ["failure", "cancelled", "timed_out"].includes(job.conclusion));
    if (!failedJob) fail("chat_failure_unproved");
    const key = await this.ctx.storage.get(`chat:run:${runId}`), record = await this.ctx.storage.get(key);
    return this.terminate(record,principal,"failed",`chat_${failedJob.name}_failed`);
  }

  async terminalReplay(principal,runId,body) {
    if(principal.principal_id!==chatConfiguration(this.env).executor.principal_id) fail("chat_executor_required",403);
    const key=await this.ctx.storage.get(`chat:run:${runId}`),record=key && await this.ctx.storage.get(key);
    if(!record || !TERMINAL.has(record.phase)) return null;
    if(record.workflow_run_id!==body.workflow_run_id || body.run_attempt!==1) fail("chat_run_identity_mismatch");
    return this.summary(record);
  }
}
