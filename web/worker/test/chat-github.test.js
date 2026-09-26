import assert from "node:assert/strict";
import test from "node:test";
import { ChatGithubController, validateChanges, safeChatPath, chatConfiguration } from "../src/conduct/chat-github.js";
import { MemoryConductStore, SerializedConductService } from "../src/conduct/keeper.js";
import { canonicalHash, validateSession } from "../src/conduct/schemas.js";

const sha = "a".repeat(40);
const input = () => ({session_id:"chat-test", request_id:"canary-1", repository:"4444J99/limen", base_sha:sha,
  intent:"Test", verification_profile:"python-canary", landing:"pr",
  changes:[{path:"scripts/chat-github-canary.py",expected_blob_sha:null,content:"hello"}]});
test("bounded UTF-8 changes reject unsafe paths and protected policy", () => {
  assert.deepEqual(validateChanges(input()), input());
  for (const path of ["../x", "/x", "a//b", "a/.git/config", "a/AGENTS.md", ".github/workflows/x.yml", "tasks.yaml", "x\\y"]) {
    assert.equal(safeChatPath(path), false, path);
    assert.throws(() => validateChanges({...input(),changes:[{...input().changes[0],path}]}));
  }
  assert.equal(safeChatPath("AGENTS.md", false), true);
  for (const content of ["x".repeat(262145), "\ud800", "\0"]) {
    assert.throws(() => validateChanges({...input(), changes:[{...input().changes[0],content}]}));
  }
  assert.throws(() => validateChanges({...input(), changes:[...input().changes,...input().changes]}));
  assert.throws(() => validateChanges({...input(), surprise:true}));
  assert.throws(() => chatConfiguration({}));
});

async function fixture() {
  const principal = {schema_version:"limen.conduct_principal.v1",principal_id:"chat",agent:"chatgpt",surface:"chat",roles:["conductor","observer"]};
  const env = {LIMEN_CHAT_GITHUB_TOKEN:"test-only", LIMEN_CONDUCT_PRINCIPAL_REGISTRY:JSON.stringify({
    schema_version:"limen.conduct_principal_registry.v1",principals:[{principal_id:"executor",agent:"github_actions",surface:"workflow",roles:["executor"],bearer:"test-only-bearer-long-enough-for-fixture"}]}),
    LIMEN_CHAT_GITHUB:JSON.stringify({schema_version:"limen.chat_github.v1",enabled:true,control_repository:"4444J99/limen",control_sha:sha,control_ref:"main",workflow_id:123,executor_principal_id:"executor",
      grants:[{principal_id:"chat",repository:"4444J99/limen",path_prefixes:["scripts"],profiles:["python-canary"],merge:false}]})};
  const values = new Map();
  const ctx = {storage:{get:async k=>values.get(k),put:async(k,v)=>values.set(k,structuredClone(v)),setAlarm:async()=>{}}};
  const service = new SerializedConductService(new MemoryConductStore(), {capabilitySecret:"fixture-only-capability-secret-long-enough"});
  await service.call("register", {principal,session:validateSession({session_id:"chat-test",identity:{agent:"chatgpt",surface:"chat",session_id:"chat-test"},origin:"direct",capabilities:["conduct"],human_protected:true})});
  const calls=[];
  const controller = new ChatGithubController(ctx,env,service,async(url,options)=>{
    const path=new URL(url).pathname; calls.push({path,options});
    let value;
    if(path.includes("/compare/")) value={status:"identical"};
    else if(path.endsWith("/branches/main")) value={commit:{sha},protected:true};
    else if(path.endsWith("/actions/workflows/123")) value={state:"active",path:".github/workflows/limen-chat-patch.yml"};
    else if(path.includes("/contents/")) value={content:btoa(JSON.stringify({profiles:{"python-canary":{repository:"4444J99/limen",paths:["scripts/chat-github-canary.py"],image:"python@sha256:"+"1".repeat(64)}}}))};
    else if(path.includes("/git/commits/")) value={tree:{sha}};
    else if(path.includes("/git/trees/")) value={tree:[],truncated:false};
    else value={private:false,default_branch:"main"};
    return Response.json(value);
  });
  return {controller,principal,calls,service,values};
}
test("GitHub transport does not bind native fetch to the controller", async () => {
  const f = await fixture();
  f.controller.request = async function (url, options) {
    assert.equal(this, undefined, "Workers native fetch rejects an unrelated receiver");
    assert.equal(new URL(url).hostname, "api.github.com");
    assert.equal(options.redirect, "manual");
    return Response.json({ id: 1255213941 });
  };
  assert.deepEqual(await f.controller.github("/repos/4444J99/limen"), { id: 1255213941 });
});
test("omitted read ref resolves the default branch once and pins file reads", async () => {
  const f = await fixture();
  const urls = [];
  f.controller.request = async (url, options) => {
    assert.equal(options.method, "GET");
    urls.push(url);
    const path = new URL(url).pathname;
    if (path.endsWith("/repos/4444J99/limen")) return Response.json({ private: false, default_branch: "trunk" });
    if (path.endsWith("/commits/trunk")) return Response.json({ sha, commit: { tree: { sha } } });
    assert.equal(new URL(url).searchParams.get("ref"), sha);
    return Response.json({ type: "file", encoding: "base64", size: 5, sha, content: btoa("hello") });
  };
  const query = { repository: "4444J99/limen", path: "scripts/chat-github-canary.py" };
  assert.deepEqual(await f.controller.read(f.principal, query), {
    repository: query.repository, commit: sha, path: query.path, blob_sha: sha, content: "hello",
  });
  assert.equal(urls.length, 3);
  for (const ref of [null, "", "feature/unapproved", 42]) {
    await assert.rejects(f.controller.read(f.principal, { ...query, ref }), /chat_exact_ref_required/);
  }
});
test("GitHub redirects fail closed using the Workers-supported manual mode", async () => {
  const f = await fixture();
  let requests = 0;
  f.controller.request = async (url, options) => {
    requests++;
    assert.equal(new URL(url).hostname, "api.github.com");
    assert.equal(options.redirect, "manual");
    return new Response(null, { status: 302, headers: { location: "https://untrusted.invalid/" } });
  };
  await assert.rejects(f.controller.github("/repos/4444J99/limen"), /chat_github_http_302/);
  assert.equal(requests, 1);
});
test("canonical admission and duplicate replay keep payloads out of graphs", async()=>{
  const f=await fixture();
  const first=await f.controller.submit(f.principal,input());
  assert.equal(first.phase,"prepared");
  assert.match(first.run_id,/^run-/);
  const count=f.calls.length;
  assert.deepEqual(await f.controller.submit(f.principal,input()),first);
  assert.equal(f.calls.length,count);
  await assert.rejects(f.controller.submit(f.principal,{...input(),intent:"changed"}),/chat_request_reused/);
  const graph=await f.service.call("graph",{run_id:first.run_id});
  assert.equal(JSON.stringify(graph).includes('"content":"hello"'),false);
  await assert.rejects(f.controller.submit(f.principal,{...input(),request_id:"other"}),/chat_executor_busy/);
});
test("authorization and stale blobs fail before Git writes",async()=>{
  const f=await fixture();
  await assert.rejects(f.controller.submit(f.principal,{...input(),landing:"merge"}),/chat_change_not_authorized/);
  await assert.rejects(f.controller.submit(f.principal,{...input(),changes:[{...input().changes[0],expected_blob_sha:sha}]}),/chat_old_blob_mismatch/);
  assert.equal(f.calls.some(call=>call.options.method!=="GET"),false);
});

test("Git objects dispatch once and actual run identity fences publication",async()=>{
  const f=await fixture();
  const accepted=await f.controller.submit(f.principal,input());
  let dispatches=0;
  let verified=false;
  const head="b".repeat(40);
  f.controller.request=async(url,options)=>{
    const path=new URL(url).pathname;
    if(path.endsWith("/dispatches")){dispatches++;return new Response(null,{status:204});}
    if(path.endsWith("/git/blobs")) return Response.json({sha:"c".repeat(40)});
    if(path.endsWith("/git/trees")) return Response.json({sha:"d".repeat(40)});
    if(path.endsWith("/git/commits")) return Response.json({sha:head});
    if(path.includes("/git/ref/")) return new Response(null,{status:404});
    if(path.endsWith("/branches/main")) return Response.json({commit:{sha},protected:true});
    if(path.endsWith("/actions/runs/42")) return Response.json({id:42,workflow_id:123,head_sha:sha,event:"workflow_dispatch",head_branch:"main",run_attempt:1,display_title:`chat:${accepted.run_id}`});
    if(path.endsWith("/jobs")) return Response.json({jobs:[{name:"verify",runner_id:1,conclusion:verified?"failure":"success",steps:[]}]});
    return Response.json({});
  };
  for(let i=0;i<6;i++) await f.controller.alarm();
  assert.equal(dispatches,1);
  const executor=chatConfiguration(f.controller.env).executor;
  await assert.rejects(f.controller.executorContext(f.principal,accepted.run_id,{workflow_run_id:42,run_attempt:1}),/chat_executor_required/);
  await assert.rejects(f.controller.executorContext(executor,accepted.run_id,{workflow_run_id:42,run_attempt:2}),/chat_run_identity_invalid/);
  const context=await f.controller.executorContext(executor,accepted.run_id,{workflow_run_id:42,run_attempt:1});
  assert.equal(context.head,head);
  await assert.rejects(f.controller.publish(executor,accepted.run_id,{workflow_run_id:42,run_attempt:1}),/chat_verification_unproved/);
  verified=true;
  const failed=await f.controller.failed(executor,accepted.run_id,{workflow_run_id:42,run_attempt:1});
  assert.equal(failed.phase,"failed");
  const graph=await f.service.call("graph",{run_id:accepted.run_id});
  assert.equal(graph.nodes[0].status,"failed");
  assert.equal(graph.nodes[0].attempts.length,1);
  assert.equal(graph.nodes[0].attempts[0].provider_run_id,"42");
  assert.equal(graph.nodes[0].attempts[0].status,"failed");
});

async function ready(landing="pr") {
  const f=await fixture();
  const config=JSON.parse(f.controller.env.LIMEN_CHAT_GITHUB);config.grants[0].merge=true;
  f.controller.env.LIMEN_CHAT_GITHUB=JSON.stringify(config);
  const accepted=await f.controller.submit(f.principal,{...input(),landing});
  const key=f.values.get(`chat:run:${accepted.run_id}`),record=f.values.get(key);
  record.phase="dispatched";record.head="b".repeat(40);record.entries=[{path:input().changes[0].path}];
  f.values.set(key,structuredClone(record));
  const verification={schema_version:"limen.chat_verification.v1",run_id:record.run_id,head:record.head,
    profile_digest:record.profile_digest,control_sha:sha,workflow_run_id:42,run_attempt:1,exit_code:0,
    output_sha256:"c".repeat(64),inference_provider_runs:0,sandbox_image:record.sandbox_image};
  const artifact={id:7,name:`chat-verification-${await canonicalHash(verification)}`,expired:false,
    digest:"sha256:"+"d".repeat(64),size_in_bytes:1024,workflow_run:{id:42,head_sha:sha}};
  const pr={number:3,head:{sha:record.head,ref:record.branch,repo:{full_name:record.repository}},
    base:{ref:"main",repo:{full_name:record.repository}},merged:false,merge_commit_sha:"e".repeat(40),html_url:"https://github.com/4444J99/limen/pull/3"};
  let artifactPresent=true,comparison="ahead",runStatus="in_progress",posts=0;
  f.controller.request=async(url,options)=>{
    const path=new URL(url).pathname;
    if(options.method==="POST") posts++;
    if(path.endsWith("/actions/runs/42")) return Response.json({id:42,workflow_id:123,head_sha:sha,event:"workflow_dispatch",head_branch:"main",run_attempt:1,display_title:`chat:${record.run_id}`,status:runStatus});
    if(path.endsWith("/jobs")) return Response.json({jobs:[{name:"verify",runner_id:1,conclusion:"success",steps:[{name:"Run isolated verification",conclusion:"success"}]}]});
    if(path.endsWith("/artifacts")) return Response.json({artifacts:artifactPresent?[artifact]:[]});
    if(path.includes("/git/ref/")) return Response.json({object:{sha:record.head}});
    if(path.endsWith("/pulls")) return Response.json(options.method==="GET"?[]:pr);
    if(path.endsWith("/pulls/3")) return Response.json(pr);
    if(path.includes("/compare/")) return Response.json({status:comparison});
    return Response.json({default_branch:"main"});
  };
  return {...f,record,artifact,pr,verification,executor:chatConfiguration(f.controller.env).executor,
    body:{workflow_run_id:42,run_attempt:1,pull_request:3,verification},
    hideArtifact:()=>{artifactPresent=false;},diverge:()=>{comparison="diverged";},endRun:()=>{runStatus="completed";},posts:()=>posts};
}

test("successful publication requires exact artifact and terminal replay is idempotent",async()=>{
  const f=await ready();
  await f.controller.publish(f.executor,f.record.run_id,f.body);
  assert.equal(f.posts(),1);
  const result=await f.controller.complete(f.executor,f.record.run_id,f.body);
  assert.equal(result.complete,true);
  assert.equal(result.phase,"pr_created");
  assert.deepEqual(await f.controller.complete(f.executor,f.record.run_id,f.body),result);
  const graph=await f.service.call("graph",{run_id:f.record.run_id});
  assert.equal(graph.nodes[0].attempts[0].status,"succeeded");
  assert.equal(graph.nodes[0].receipts.length,1);
  assert.equal(graph.nodes[0].receipts[0].spend.runs,1);
  assert.ok(graph.nodes[0].receipts[0].checks.some(check=>check.name==="verification-artifact"));
});

test("forged, missing, expired and foreign-run artifacts cannot publish",async()=>{
  for(const corrupt of [f=>{f.body.verification.head="0".repeat(40);},f=>f.hideArtifact(),
    f=>{f.artifact.expired=true;},f=>{f.artifact.workflow_run.id=41;},f=>{f.artifact.digest=null;},
    f=>{f.body.verification.sandbox_image="untrusted";}]) {
    const f=await ready();corrupt(f);
    await assert.rejects(f.controller.publish(f.executor,f.record.run_id,f.body),/chat_artifact/);
    assert.equal(f.posts(),0);
  }
});

test("queued is incomplete until reconciler verifies merge and default ancestry",async()=>{
  const f=await ready("merge");
  assert.equal((await f.controller.complete(f.executor,f.record.run_id,f.body)).complete,false);
  f.pr.merged=true;
  await f.controller.alarm();
  assert.equal((await f.controller.complete(f.executor,f.record.run_id,f.body)).phase,"merged");
  assert.equal(f.posts(),0); // Reconciliation never re-submits the merge.
});

test("diverged default and completed workflow without receipt never succeed",async()=>{
  const f=await ready("merge");f.pr.merged=true;f.diverge();
  await assert.rejects(f.controller.complete(f.executor,f.record.run_id,f.body),/chat_default_ancestry_unproved/);
  const other=await ready();other.endRun();
  await other.controller.executorContext(other.executor,other.record.run_id,other.body);
  await other.controller.alarm();
  const graph=await other.service.call("graph",{run_id:other.record.run_id});
  assert.equal(graph.nodes[0].status,"failed");
});

test("crash after canonical admission reuses persisted packet without a second run",async()=>{
  const f=await fixture(),call=f.service.call.bind(f.service);
  let interrupted=false;
  f.service.call=async(op,...args)=>{
    const result=await call(op,...args);
    if(op==="submit" && !interrupted){interrupted=true;throw new Error("simulated persistence interruption");}
    return result;
  };
  await assert.rejects(f.controller.submit(f.principal,input()),/simulated/);
  const key=f.values.get("chat:active"),record=f.values.get(key);
  assert.equal(record.phase,"admitting");
  await f.controller.admit(record,f.principal);
  assert.equal(record.phase,"prepared");
  const graph=await f.service.call("graph",{run_id:record.run_id});
  assert.equal(graph.nodes.length,1);
});

test("interruption before canonical success report recovers from saved exact evidence",async()=>{
  const f=await ready(),call=f.service.call.bind(f.service);
  let interrupted=false;
  f.service.call=async(op,...args)=>{
    if(op==="report" && !interrupted){interrupted=true;throw new Error("simulated report interruption");}
    return call(op,...args);
  };
  await assert.rejects(f.controller.complete(f.executor,f.record.run_id,f.body),/simulated/);
  await f.controller.alarm();
  const result=await f.controller.complete(f.executor,f.record.run_id,f.body);
  assert.equal(result.complete,true);
  const graph=await f.service.call("graph",{run_id:f.record.run_id});
  assert.equal(graph.nodes[0].receipts.length,1);
});
