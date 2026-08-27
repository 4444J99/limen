#!/usr/bin/env python3
"""Bootstrap the limen[bot] GitHub App through GitHub's manifest flow.

This keeps the unavoidable human browser approval to one step, then captures the
returned App ID/private key locally without printing secrets. It writes:

The App remains private, so its creation account is derived from the exact
verification repository owner; private Apps are never routed across owners.

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
import re
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
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.repository_identity import LIMEN_REPOSITORY_IDENTITY  # noqa: E402

HOME = Path.home()
ENV_FILE = Path(os.environ.get("LIMEN_ENV", HOME / ".limen.env"))
DEFAULT_KEY_PATH = HOME / ".config" / "limen" / "limen-bot.pem"
GITHUB_API = os.environ.get("GITHUB_API", "https://api.github.com").rstrip("/")
GITHUB_WEB = os.environ.get("GITHUB_WEB", "https://github.com").rstrip("/")
_REPOSITORY_COORDINATE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def shell_value(value: str) -> str:
    return shlex.quote(value)


def write_env(keys: dict[str, str | None]) -> None:
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
        if value is not None:
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


def canonical_verification_target(candidate: str | None) -> str:
    """Resolve Limen aliases to the live coordinate and validate any explicit repo target."""
    target = candidate or LIMEN_REPOSITORY_IDENTITY.canonical_coordinate
    if LIMEN_REPOSITORY_IDENTITY.accepts(target):
        return LIMEN_REPOSITORY_IDENTITY.canonical_coordinate
    if target != target.strip() or not _REPOSITORY_COORDINATE.fullmatch(target):
        raise ValueError("verification target must be an exact OWNER/REPO coordinate")
    return target


def github_account_type(owner: str) -> str:
    """Resolve whether the exact repository owner needs the personal or organization App flow."""
    try:
        proc = subprocess.run(
            ["gh", "api", f"/users/{owner}", "--jq", ".type"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"cannot resolve GitHub account type for {owner}: {exc}") from exc
    account_type = proc.stdout.strip()
    if proc.returncode != 0 or account_type not in {"User", "Organization"}:
        detail = (proc.stderr or proc.stdout or "unexpected account type response").strip()[:160]
        raise RuntimeError(f"cannot resolve GitHub account type for {owner}: {detail}")
    return account_type


def manifest_settings_url(owner: str, account_type: str, state: str) -> str:
    """Return the GitHub manifest endpoint for the account that owns the target repository."""
    if account_type == "User":
        path = "/settings/apps/new"
    elif account_type == "Organization":
        path = f"/organizations/{owner}/settings/apps/new"
    else:
        raise ValueError(f"unsupported GitHub account type: {account_type}")
    return f"{GITHUB_WEB}{path}?state={urllib.parse.quote(state)}"


def verify_app_token(repo: str, *, quiet: bool = False) -> bool:
    proc = subprocess.run(
        ["bash", "scripts/gh-app-token.sh", "--repo", repo, "--verify-app"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    if not quiet and proc.stdout.strip():
        print(proc.stdout.strip())
    if not quiet and proc.returncode != 0 and proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0


def wait_for_repository_installation(repo: str, timeout: int, *, poll_seconds: float = 5.0) -> bool:
    """Wait until the new App can mint a token for this exact repository, never an owner-wide proxy."""
    deadline = time.monotonic() + max(0, timeout)
    while True:
        if verify_app_token(repo, quiet=True):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(poll_seconds, remaining))


def build_manifest(verification_repo: str, redirect_url: str, app_name: str) -> dict[str, Any]:
    return {
        "name": app_name,
        "url": f"{GITHUB_WEB}/{verification_repo}",
        "description": "Limen conductor machine identity for repo, PR, workflow, and CI operations.",
        "hook_attributes": {
            "url": f"{GITHUB_WEB}/{verification_repo}",
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
            action = self.server.manifest_action
            body = f"""<!doctype html>
<meta charset="utf-8">
<title>Create limen[bot]</title>
<h1>Create limen[bot]</h1>
<p>This posts the prefilled GitHub App manifest to GitHub. Confirm the app in GitHub, then install it on <code>{html.escape(self.server.install_owner)}</code> with access to the exact repository <code>{html.escape(self.server.install_repo)}</code>.</p>
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
<p>The private key was returned to the local bootstrap process. Next install the app on <code>{html.escape(self.server.install_owner)}</code> with access to the exact repository <code>{html.escape(self.server.install_repo)}</code>.</p>
<p><a href="{html.escape(install_url)}">Install {html.escape(slug)} on GitHub</a></p>
""",
        )
        threading.Thread(target=webbrowser.open, args=(install_url,), daemon=True).start()


class BootstrapServer(http.server.ThreadingHTTPServer):
    def __init__(
        self,
        addr: tuple[str, int],
        handler: type[BootstrapHandler],
        *,
        app_owner: str,
        app_owner_type: str,
        app_name: str,
        install_repo: str,
    ) -> None:
        install_owner = install_repo.split("/", 1)[0]
        if install_owner.casefold() != app_owner.casefold():
            raise ValueError("private App owner must match the exact installation repository owner")
        super().__init__(addr, handler)
        self.app_owner = app_owner
        self.app_owner_type = app_owner_type
        self.app_name = app_name
        self.install_repo = install_repo
        self.install_owner = install_owner
        self.state = secrets.token_urlsafe(24)
        host, port = self.server_address[:2]
        self.redirect_url = f"http://{host}:{port}/callback"
        self.manifest = build_manifest(install_repo, self.redirect_url, app_name)
        self.manifest_action = manifest_settings_url(app_owner, app_owner_type, self.state)
        self.done = threading.Event()
        self.error: str | None = None
        self.app_response: dict[str, Any] | None = None


def reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", default="limen-bot")
    parser.add_argument(
        "--verify-repo",
        default=None,
        help="exact OWNER/REPO used to resolve and verify the App installation token",
    )
    parser.add_argument("--key-path", type=Path, default=DEFAULT_KEY_PATH)
    parser.add_argument("--timeout", type=int, default=900, help="seconds to wait for GitHub callback")
    parser.add_argument(
        "--install-timeout",
        type=int,
        default=900,
        help="seconds to wait for an App token mint on the exact verification repository",
    )
    parser.add_argument("--no-open", action="store_true", help="print the local URL instead of opening a browser")
    args = parser.parse_args()
    try:
        verify_repo = canonical_verification_target(args.verify_repo or os.environ.get("LIMEN_GITHUB_TARGET_REPO"))
    except ValueError as exc:
        parser.error(str(exc))
    app_owner = verify_repo.split("/", 1)[0]
    try:
        app_owner_type = github_account_type(app_owner)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    port = reserve_loopback_port()
    server = BootstrapServer(
        ("127.0.0.1", port),
        BootstrapHandler,
        app_owner=app_owner,
        app_owner_type=app_owner_type,
        app_name=args.app_name,
        install_repo=verify_repo,
    )
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
    write_env(
        {
            "GITHUB_APP_ID": app_id,
            "GITHUB_APP_PRIVATE_KEY": str(args.key_path),
            "GITHUB_APP_INSTALLATION_ID": None,
            "LIMEN_GITHUB_TARGET_REPO": verify_repo,
        }
    )
    print(f"Stored App ID and private-key path in {ENV_FILE} (values hidden).")
    print(f"Private key written to {args.key_path} (chmod 600).")

    print(f"Waiting for {slug} installation on exact repository {verify_repo}...")
    if not wait_for_repository_installation(verify_repo, args.install_timeout):
        print(f"Install URL: {GITHUB_WEB}/apps/{slug}/installations/new")
        print(
            f"App is created and credentials are stored, but exact repository access to {verify_repo} was not observed yet.",
            file=sys.stderr,
        )
        return 3

    print(f"Observed {slug} on {verify_repo}; exact-repository installation token mint succeeds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
