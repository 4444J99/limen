#!/usr/bin/env python3
"""Bootstrap the limen[bot] GitHub App through GitHub's manifest flow.

This keeps the unavoidable human browser approval to one step, then captures the
returned App ID/private key locally without printing secrets. It writes:

* ~/.config/limen/limen-bot.pem       private key, chmod 600
* ~/.limen.env                        GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY path,
                                      and installation id when available

It does not commit secrets and does not print the PEM or token.
"""
from __future__ import annotations

import argparse
import html
import http.server
import json
import os
import secrets
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
ENV_FILE = Path(os.environ.get("LIMEN_ENV", HOME / ".limen.env"))
DEFAULT_KEY_PATH = HOME / ".config" / "limen" / "limen-bot.pem"
GITHUB_API = os.environ.get("GITHUB_API", "https://api.github.com").rstrip("/")
GITHUB_WEB = os.environ.get("GITHUB_WEB", "https://github.com").rstrip("/")


def shell_value(value: str) -> str:
    return shlex.quote(value)


def write_env(keys: dict[str, str]) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(mode=0o600)
    lines = ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    filtered = [
        line
        for line in lines
        if not any(line.startswith(f"{key}=") or line.startswith(f"export {key}=") for key in keys)
    ]
    for key, value in keys.items():
        filtered.append(f"export {key}={shell_value(value)}")
    tmp = ENV_FILE.with_suffix(f"{ENV_FILE.suffix}.tmp")
    tmp.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(ENV_FILE)
    ENV_FILE.chmod(0o600)


def exchange_manifest_code(code: str) -> dict[str, Any]:
    url = f"{GITHUB_API}/app-manifests/{urllib.parse.quote(code)}/conversions"
    req = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "limen-github-app-bootstrap",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub manifest conversion failed: HTTP {exc.code}: {detail}") from exc


def gh_installations(org: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["gh", "api", f"/orgs/{org}/installations"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    installs = data.get("installations", [])
    return installs if isinstance(installs, list) else []


def find_installation(org: str, slug: str) -> dict[str, Any] | None:
    for item in gh_installations(org):
        if str(item.get("app_slug") or "") == slug:
            return item
    return None


def verify_app_token() -> bool:
    proc = subprocess.run(
        ["bash", "scripts/gh-app-token.sh", "--verify-app"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0 and proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0


def build_manifest(org: str, redirect_url: str, app_name: str) -> dict[str, Any]:
    return {
        "name": app_name,
        "url": f"{GITHUB_WEB}/{org}",
        "description": "Limen conductor machine identity for repo, PR, workflow, and CI operations.",
        "hook_attributes": {
            "url": f"{GITHUB_WEB}/{org}/limen",
            "active": False,
        },
        "redirect_url": redirect_url,
        "callback_urls": [redirect_url],
        "public": False,
        "default_permissions": {
            "administration": "write",
            "contents": "write",
            "pull_requests": "write",
            "workflows": "write",
            "actions": "write",
            "issues": "write",
            "metadata": "read",
            "organization_administration": "write",
            "members": "read",
        },
    }


class BootstrapHandler(http.server.BaseHTTPRequestHandler):
    server: "BootstrapServer"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def write_html(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", "/start")
            self.end_headers()
            return
        if parsed.path == "/start":
            manifest = html.escape(json.dumps(self.server.manifest, separators=(",", ":")), quote=True)
            action = (
                f"{GITHUB_WEB}/organizations/{self.server.org}/settings/apps/new"
                f"?state={urllib.parse.quote(self.server.state)}"
            )
            body = f"""<!doctype html>
<meta charset="utf-8">
<title>Create limen[bot]</title>
<h1>Create limen[bot]</h1>
<p>This posts the prefilled GitHub App manifest to GitHub. Confirm the app in GitHub, then install it on all <code>{html.escape(self.server.org)}</code> repositories.</p>
<form id="manifest" action="{html.escape(action)}" method="post">
  <input type="hidden" name="manifest" value="{manifest}">
  <button type="submit">Create limen[bot] on GitHub</button>
</form>
<script>document.getElementById("manifest").submit()</script>
"""
            self.write_html(200, body)
            return
        if parsed.path != "/callback":
            self.write_html(404, "<h1>Not found</h1>")
            return

        params = urllib.parse.parse_qs(parsed.query)
        state = params.get("state", [""])[0]
        code = params.get("code", [""])[0]
        if state != self.server.state:
            self.server.error = "state mismatch in GitHub callback"
            self.server.done.set()
            self.write_html(400, "<h1>State mismatch</h1>")
            return
        if not code:
            self.server.error = "GitHub callback did not include a code"
            self.server.done.set()
            self.write_html(400, "<h1>Missing code</h1>")
            return

        try:
            app = exchange_manifest_code(code)
            self.server.app_response = app
            self.server.done.set()
        except Exception as exc:  # noqa: BLE001
            self.server.error = str(exc)
            self.server.done.set()
            self.write_html(500, f"<h1>Manifest conversion failed</h1><pre>{html.escape(str(exc))}</pre>")
            return

        slug = str(app.get("slug") or self.server.app_name)
        install_url = f"{GITHUB_WEB}/apps/{slug}/installations/new"
        self.write_html(
            200,
            f"""<!doctype html>
<meta charset="utf-8">
<title>limen[bot] created</title>
<h1>limen[bot] created</h1>
<p>The private key was returned to the local bootstrap process. Next install the app on <code>{html.escape(self.server.org)}</code> with access to all repositories.</p>
<p><a href="{html.escape(install_url)}">Install {html.escape(slug)} on GitHub</a></p>
""",
        )
        threading.Thread(target=webbrowser.open, args=(install_url,), daemon=True).start()


class BootstrapServer(http.server.ThreadingHTTPServer):
    def __init__(self, addr: tuple[str, int], handler: type[BootstrapHandler], *, org: str, app_name: str) -> None:
        super().__init__(addr, handler)
        self.org = org
        self.app_name = app_name
        self.state = secrets.token_urlsafe(24)
        host, port = self.server_address[:2]
        self.redirect_url = f"http://{host}:{port}/callback"
        self.manifest = build_manifest(org, self.redirect_url, app_name)
        self.done = threading.Event()
        self.error: str | None = None
        self.app_response: dict[str, Any] | None = None


def reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="organvm")
    parser.add_argument("--app-name", default="limen-bot")
    parser.add_argument("--key-path", type=Path, default=DEFAULT_KEY_PATH)
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for GitHub callback")
    parser.add_argument("--install-timeout", type=int, default=900, help="seconds to wait for org install")
    parser.add_argument("--no-open", action="store_true", help="print the local URL instead of opening a browser")
    args = parser.parse_args()

    port = reserve_loopback_port()
    server = BootstrapServer(("127.0.0.1", port), BootstrapHandler, org=args.org, app_name=args.app_name)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    start_url = f"http://127.0.0.1:{port}/start"
    print(f"Open this URL to create {args.app_name}: {start_url}")
    if not args.no_open:
        webbrowser.open(start_url)

    if not server.done.wait(args.timeout):
        server.shutdown()
        print("Timed out waiting for GitHub to redirect back with the manifest code.", file=sys.stderr)
        return 2
    server.shutdown()
    if server.error:
        print(server.error, file=sys.stderr)
        return 1
    app = server.app_response or {}
    app_id = str(app.get("id") or "")
    pem = str(app.get("pem") or "")
    slug = str(app.get("slug") or args.app_name)
    if not app_id or not pem:
        print("GitHub response did not include both app id and private key.", file=sys.stderr)
        return 1

    args.key_path.parent.mkdir(parents=True, exist_ok=True)
    args.key_path.write_text(pem, encoding="utf-8")
    args.key_path.chmod(0o600)
    write_env({"GITHUB_APP_ID": app_id, "GITHUB_APP_PRIVATE_KEY": str(args.key_path)})
    print(f"Stored App ID and private-key path in {ENV_FILE} (values hidden).")
    print(f"Private key written to {args.key_path} (chmod 600).")

    print(f"Waiting for {slug} installation on {args.org}...")
    deadline = time.time() + max(0, args.install_timeout)
    install: dict[str, Any] | None = None
    while time.time() < deadline:
        install = find_installation(args.org, slug)
        if install:
            break
        time.sleep(5)
    if not install:
        print(f"Install URL: {GITHUB_WEB}/apps/{slug}/installations/new")
        print("App is created and credentials are stored, but installation was not observed yet.", file=sys.stderr)
        return 3

    install_id = str(install.get("id") or "")
    write_env({"GITHUB_APP_INSTALLATION_ID": install_id})
    print(f"Stored installation id for {slug} on {args.org} (id hidden in output policy: name only).")

    if verify_app_token():
        return 0
    print("App exists but token verification failed; check permissions/install target.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
