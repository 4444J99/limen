import assert from "node:assert/strict";
import test from "node:test";
import { ChatGithubController, validateChanges, safeChatPath, chatConfiguration } from "../src/conduct/chat-github.js";
import { MemoryConductStore, SerializedConductService } from "../src/conduct/keeper.js";
import { validateSession } from "../src/conduct/schemas.js";

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
    if(path.endsWith("/branches/main")) value={commit:{sha},protected:true};
    else if(path.endsWith("/actions/workflows/123")) value={state:"active",path:".github/workflows/limen-chat-patch.yml"};
    else if(path.includes("/contents/")) value={content:btoa(JSON.stringify({profiles:{"python-canary":{repository:"4444J99/limen",paths:["scripts/chat-github-canary.py"]}}}))};
    else if(path.includes("/git/commits/")) value={tree:{sha}};
    else if(path.includes("/git/trees/")) value={tree:[],truncated:false};
    else value={private:false,default_branch:"main"};
    return Response.json(value);
  });
  return {controller,principal,calls,service,values};
}
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
});
