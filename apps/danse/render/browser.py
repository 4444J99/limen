#!/usr/bin/env python3
"""A browser with a real GPU in it — and the assertion that it is one.

The film is 23,400 frames. Rendering all of them on a software rasteriser takes
most of a day and produces a file that looks subtly, unfixably wrong, and the
only way to find out is to watch the whole thing at the end. So every path that
opens a browser for danse comes through here, and here refuses to proceed unless
the GL renderer string names Apple's Metal backend.

Two facts this encodes, both measured rather than assumed:

  - Playwright's BUNDLED chromium is not installed on this machine, and
    `chrome-headless-shell` has no GPU at all. `channel="chrome"` — the system
    Google Chrome in /Applications — is the one that gets ANGLE Metal.
  - `--headless=new` keeps the GPU. The old headless mode does not.

    apps/danse/render/browser.py --check          # print the GL renderer and exit
    apps/danse/render/browser.py --verify         # run verify.html, print the verdict
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import socket
import socketserver
import sys
import threading
from pathlib import Path

APP = Path(__file__).resolve().parent.parent

# ANGLE on macOS reports e.g. "ANGLE (Apple, ANGLE Metal Renderer: Apple M5, …)".
# SwiftShader reports "SwiftShader" and llvmpipe reports "llvmpipe" — either means
# the frame is being drawn on the CPU.
WANTED = ("metal", "apple")

READ_RENDERER = """
() => {
  const c = document.createElement("canvas");
  const gl = c.getContext("webgl2");
  if (!gl) return { ok: false, renderer: "no webgl2 context" };
  const ext = gl.getExtension("WEBGL_debug_renderer_info");
  return {
    ok: true,
    renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
    maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE),
  };
}
"""

# Without these, headless Chrome quietly falls back to SwiftShader on a machine
# with no attached display — which is exactly the situation a background render
# runs in.
GPU_ARGS = [
    "--use-angle=metal",
    "--enable-gpu",
    "--ignore-gpu-blocklist",
    "--enable-unsafe-webgpu",
    "--disable-gpu-driver-bug-workarounds",
    # The film's plates are large and numerous; the default cache evicts them
    # mid-segment and the reads stall behind refetches.
    "--disable-dev-shm-usage",
]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):  # noqa: D102 - a render log is not an access log
        pass


@contextlib.contextmanager
def serve(root: Path = APP, port: int = 0):
    """A static server over the app directory. Port 0 picks a free one, so two
    renders running side by side never collide."""
    handler = functools.partial(_Quiet, directory=str(root))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        actual = httpd.socket.getsockname()[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{actual}"
        finally:
            httpd.shutdown()


def reachable(url: str, timeout: float = 0.4) -> bool:
    host, _, port = url.removeprefix("http://").partition(":")
    with contextlib.suppress(OSError):
        with socket.create_connection((host, int(port or 80)), timeout=timeout):
            return True
    return False


@contextlib.contextmanager
def browser(headless: bool = True, width: int = 1024, height: int = 768):
    """A page on the system Chrome, GPU asserted before anything is drawn."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        launched = p.chromium.launch(channel="chrome", headless=headless, args=GPU_ARGS)
        try:
            page = launched.new_page(viewport={"width": width, "height": height})
            gpu = page.evaluate(READ_RENDERER)
            if not gpu["ok"]:
                raise SystemExit(f"no WebGL2: {gpu['renderer']}")
            name = str(gpu["renderer"])
            if not any(w in name.lower() for w in WANTED):
                raise SystemExit(
                    f"refusing to render on {name!r}.\n"
                    "This is a software rasteriser. The film would take a day and come out wrong.\n"
                    "Check that Google Chrome is installed and that channel='chrome' resolved to it."
                )
            page.gl_renderer = name
            yield page
        finally:
            launched.close()


def run_verify(page, base: str) -> int:
    """The regression net: verify.html renders the flat state and measures it
    against the 25 July 2017 composite. Any engine change that stops the piece
    being a reproduction shows up here as a number, not as an opinion."""
    page.goto(f"{base}/verify.html", wait_until="load")
    page.wait_for_function("() => window.danseVerify !== undefined", timeout=180_000)
    r = page.evaluate("() => window.danseVerify")

    print(f"\n  renderer   {page.gl_renderer}")
    print(f"  live path  {r['live']:.2f} dB")
    print(f"  ceiling    {r['plateCeiling']:.2f} dB  (same score, same plates, numpy, no GPU)")
    print(f"  gap        {abs(r['live'] - r['plateCeiling']):.2f} dB\n")
    for run in r["runs"]:
        print(f"    {run['psnr']:>6.2f} dB   {run['label']}")
    print()
    if r["pass"]:
        print("REPRODUCTION HOLDS — the flat state is still the 2017 piece")
        return 0
    print("REPRODUCTION BROKEN — an engine change moved the flat state off the original")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="print the GL renderer and exit")
    ap.add_argument("--verify", action="store_true", help="run verify.html and report the verdict")
    ap.add_argument("--headed", action="store_true", help="show the window (debugging)")
    ap.add_argument("--base", help="use an already-running server instead of starting one")
    args = ap.parse_args()

    if not args.check and not args.verify:
        ap.error("nothing to do — pass --check or --verify")

    with contextlib.ExitStack() as stack:
        if args.base and reachable(args.base):
            base = args.base
        else:
            base = stack.enter_context(serve())
        page = stack.enter_context(browser(headless=not args.headed))

        if args.check:
            gpu = page.evaluate(READ_RENDERER)
            print(json.dumps({**gpu, "serving": base}, indent=1))
            if not args.verify:
                return 0
        return run_verify(page, base)


if __name__ == "__main__":
    sys.exit(main())
