const test = require("node:test");
const assert = require("node:assert/strict");
const {verifyPositioningWithConnector} = require("../positioning-connector-driver.js");

const request = {
  schema: "limen.github_connector.v1", id: "a".repeat(32), method: "GET",
  url: "https://api.github.com/repos/4444J99/limen/issues/2251/comments?per_page=100&page=1",
};
const requestLine = "limen.github.request " + JSON.stringify(request) + "\r\n";
const running = output => ({session_id: 73, output});
const finished = output => ({exit_code: 0, output});
const value = [{id: 4, created_at: "2026-09-09T16:00:00Z", body: "raw receipt"}];

function fixture(initial, onWrite, fetch = async () => ({structuredContent: {content: JSON.stringify(value)}})) {
  const writes = [];
  return {
    writes,
    tools: {
      exec_command: async args => {
        assert.equal(args.tty, true, "PTY keeps interactive stdin open");
        return initial;
      },
      write_stdin: async args => {
        assert.equal(args.session_id, 73);
        writes.push(args.chars);
        return onWrite(args, writes.length);
      },
      mcp__codex_apps__github_fetch: fetch,
    },
  };
}

test("delayed startup is polled without treating missing output as failure", async () => {
  const f = fixture(running(""), (args, count) => {
    if (count === 1) {
      assert.equal(args.chars, "");
      return running(requestLine);
    }
    assert.deepEqual(JSON.parse(args.chars).value, value);
    return finished('{"status":"pass"}\r\n');
  });
  const result = await verifyPositioningWithConnector(f.tools, "/repo", "PSP-P11-W03");
  assert.equal(result.exit_code, 0);
  assert.equal(result.observations.length, 1);
  assert.equal(result.output, '{"status":"pass"}');
});

test("fragmented CRLF request survives output chunk boundaries", async () => {
  const f = fixture(running(requestLine.slice(0, 18)), (args, count) => {
    if (count === 1) return running(requestLine.slice(18, -1));
    if (count === 2) return running(requestLine.slice(-1));
    return finished("pass\n");
  });
  const result = await verifyPositioningWithConnector(f.tools, "/repo", "PSP-P11-W03");
  assert.equal(result.output, "pass");
  assert.deepEqual(f.writes.slice(0, 2), ["", ""]);
  assert.deepEqual(JSON.parse(f.writes[2]).value, value);
});

test("connector failure sends a correlated negative reply and preserves original error", async () => {
  const original = new Error("connector unavailable");
  const f = fixture(running(requestLine), args => {
    assert.deepEqual(JSON.parse(args.chars), {...request, ok: false});
    return {exit_code: 2, output: "observation unavailable\n"};
  }, async () => { throw original; });
  await assert.rejects(verifyPositioningWithConnector(f.tools, "/repo", "PSP-P11-W03"), error => error === original);
  assert.equal(f.writes.length, 1);
});

test("cleanup failure does not mask the original connector exception", async () => {
  const original = new Error("original");
  const f = fixture(running(requestLine), async () => { throw new Error("process exited"); }, async () => { throw original; });
  await assert.rejects(verifyPositioningWithConnector(f.tools, "/repo", "PSP-P11-W03"), error => error === original);
  assert.equal(JSON.parse(f.writes[0]).ok, false);
});

test("malformed connector JSON rejects and unblocks the waiting process", async () => {
  const f = fixture(running(requestLine), () => ({exit_code: 2, output: ""}),
    async () => ({structuredContent: {content: "not json"}}));
  await assert.rejects(verifyPositioningWithConnector(f.tools, "/repo", "PSP-P11-W03"), SyntaxError);
  assert.equal(JSON.parse(f.writes[0]).ok, false);
});

test("multiple pending requests never reach the authenticated connector", async () => {
  let fetches = 0;
  const f = fixture(running(requestLine + requestLine), () => ({exit_code: 2, output: ""}), async () => { fetches++; });
  await assert.rejects(verifyPositioningWithConnector(f.tools, "/repo", "PSP-P11-W03"), /exactly one/);
  assert.equal(fetches, 0);
  assert.equal(JSON.parse(f.writes[0]).ok, false);
});

test("idle output is bounded and receives protocol cancellation", async () => {
  const f = fixture(running(""), () => running(""));
  await assert.rejects(verifyPositioningWithConnector(f.tools, "/repo", "PSP-P11-W03"), /bound exceeded/);
  assert.equal(f.writes.length, 257);
  assert.equal(JSON.parse(f.writes.at(-1)).ok, false);
});
