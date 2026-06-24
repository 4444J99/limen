# ianva — the gated flips (his-hand)

Everything buildable is built and verified locally. What remains is irreversible or touches your
machine/installation, so it waits for an explicit "go." Each is one command. In rough order:

### 1. Point your local agents at ianva  (cures disease B)
Writes the `ianva` entry into the 7 agent configs. **Backs up every file first; idempotent; dry-run
by default.** This is the "all agent config files" deliverable.
```bash
cd ianva && export PYTHONPATH="$PWD/src"
python3 -m ianva.cli up                       # start the gateway (first run downloads MCPHub via npx)
python3 -m ianva.cli install-configs          # preview (writes nothing)
python3 -m ianva.cli install-configs --apply  # apply
```
Reversible: restore any `*.ianva-bak.<timestamp>` file, or `claude mcp remove --scope user ianva`.

### 2. Populate the upstream registry  (so ianva has servers to front)
`doctor` shows `~/.agents/mcp/servers.json` missing → 0 upstreams. Either run the fleet's existing
`build-mcp-registry.py` (its first real consumer is now ianva) or copy `upstreams.example.json` to
`~/.config/ianva/upstreams.json` and edit. Remote OAuth upstreams get `"oauth": true`.

### 3. Stand up the cloud face  (cures disease A — the claude.ai connector prompts)
Only this stops the `/doctor` Sentry-style prompts. Needs a public URL — and a **bearer first**,
because a public unauthenticated gateway is an open proxy to every upstream's credentials.
```bash
ianva bearer --new                            # generate a bearer, then store it:
bash ~/Workspace/limen/scripts/set-credential.sh IANVA_BEARER_TOKEN
ianva up                                       # restart so the gateway ENFORCES the bearer
bash scripts/ianva-tunnel.sh                  # refuses to expose unless /mcp returns 401 unauth'd
# stable URL:  cloudflared tunnel login   (one-time, his-hand)  then  scripts/ianva-tunnel.sh --named ianva
```
Then set `gateway.public_url` in `ianva.toml` to `<url>/mcp`, and in **claude.ai → add a custom
connector** at that URL, entering the bearer in the connector's auth/header settings. It replaces the
per-service connectors. The tunnel script will refuse to expose an endpoint that answers `/mcp`
without auth, so you can't accidentally publish it open.

### 4. Keep it alive across reboots  (launchd)
```bash
cp deploy/com.ianva.gateway.plist ~/Library/LaunchAgents/
sed -i '' "s#__IANVA_DIR__#$PWD#g" ~/Library/LaunchAgents/com.ianva.gateway.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ianva.gateway.plist
```

### 5. Close disease C properly  (the fleet credential race)
`doctor` shows `LIMEN_CLAUDE_AUTH_TOKEN` / `LIMEN_CLAUDE_API_KEY` unset. Give the fleet its own
stable credential so ~30 `claude -p` stop fighting over the Keychain:
```bash
claude setup-token                                        # subscription-billed, stable
bash /Users/4jp/Workspace/limen/scripts/set-credential.sh LIMEN_CLAUDE_AUTH_TOKEN   # silent prompt
bash /Users/4jp/Workspace/limen/scripts/claude-fleet-auth-probe.sh                  # verify free + Keychain intact
```
This is the un-merged `fix/claude-credential-race` work; merging that branch is the durable fix, and
the 39 stale `Claude Code-credentials-<hex>` Keychain forks can then be pruned.

### 6. Land the code
Branch `worktree-ianva-doorway` is staged (not pushed, not merged). Open a PR / merge to limen `main`
when you want ianva to ship to the fleet.
