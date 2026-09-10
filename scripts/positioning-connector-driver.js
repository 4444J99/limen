/* ChatGPT code-mode host: pass native tools; authentication stays in its connector.
 * Run trusted code from an inspected revision. No gh impersonation or lifecycle writes.
 */
async function verifyPositioningWithConnector(tools, root, workId) {
  if (!/^PSP-P\d{2}-W\d{2}$/.test(workId) || typeof root !== "string" || !root.startsWith("/")) {
    throw new Error("Expected absolute repository root and exact PSP work ID");
  }
  const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
  let result = await tools.exec_command({
    cmd: "python3 scripts/positioning-program.py --verify-work " + quote(workId) + " --github-transport connector",
    workdir: root, tty: true, yield_time_ms: 1000, max_output_tokens: 3000,
  });
  const observations = [];
  let finalOutput = "";
  let buffer = "";
  let pending = null;
  const sessionId = result.session_id;
  try {
    // Tool yields can split a request or precede startup. Bound idle reads and pagination.
    for (let iteration = 0; iteration < 256; iteration++) {
      buffer += result.output;
      if (buffer.length > 65536) throw new Error("Connector request line exceeds size limit");
      while (buffer.includes("\n")) {
        const end = buffer.indexOf("\n");
        const line = buffer.slice(0, end).replace(/\r$/, "");
        buffer = buffer.slice(end + 1);
        if (line.startsWith("limen.github.request ")) {
          if (pending) throw new Error("Expected exactly one pending GitHub request");
          pending = JSON.parse(line.slice("limen.github.request ".length));
        } else {
          finalOutput += line + "\n";
        }
      }
      if (result.exit_code !== undefined) {
        if (pending || buffer.startsWith("limen.github.request ")) {
          throw new Error("Verifier exited with an incomplete GitHub exchange");
        }
        finalOutput += buffer;
        return {exit_code: result.exit_code, output: finalOutput.trim(), observations};
      }
      if (!sessionId || result.session_id !== sessionId) {
        throw new Error("Verifier session identity changed");
      }
      if (!pending) {
        result = await tools.write_stdin({
          session_id: sessionId, chars: "", yield_time_ms: 1000, max_output_tokens: 3000,
        });
        continue;
      }
      const request = pending;
      if (request.schema !== "limen.github_connector.v1" || request.method !== "GET" ||
          !/^[0-9a-f]{32}$/.test(request.id) ||
          !/^https:\/\/api\.github\.com\/(repos\/|repositories\/)/.test(request.url)) {
        throw new Error("Unsupported connector request");
      }
      if (observations.length >= 100) throw new Error("GitHub connector request bound exceeded");
      const fetched = await tools.mcp__codex_apps__github_fetch({url: request.url});
      const data = fetched.structuredContent?.result ?? fetched.structuredContent;
      let response = {...request, ok: false};
      if (!fetched.isError && typeof data?.content === "string") {
        response = {...request, ok: true, value: JSON.parse(data.content)};
      }
      observations.push({url: request.url, ok: response.ok, observed_at: new Date().toISOString()});
      result = await tools.write_stdin({
        session_id: sessionId, chars: JSON.stringify(response) + "\n",
        yield_time_ms: 1000, max_output_tokens: 3000,
      });
      pending = null;
    }
    throw new Error("GitHub connector exchange bound exceeded");
  } catch (error) {
    // Ctrl-D is data in raw mode. A negative JSON response ends the owned verifier.
    // An unparseable request gets a rejecting object instead of a fabricated response.
    if (sessionId && result.exit_code === undefined) {
      try {
        await tools.write_stdin({
          session_id: sessionId, chars: JSON.stringify({...pending, ok: false}) + "\n",
          yield_time_ms: 1000, max_output_tokens: 1000,
        });
      } catch {
        // Preserve the observation error if the process has already exited.
      }
    }
    throw error;
  }
}

if (typeof module !== "undefined") module.exports = {verifyPositioningWithConnector};
