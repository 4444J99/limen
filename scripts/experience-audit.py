#!/usr/bin/env python3
"""experience-audit.py — the missing sensor axis: what a VISITOR actually EXPERIENCES.

GATES score the pre-merge diff, SENSORS score the running system's own posture, but neither answers
the one question a demand funnel lives or dies on: when a real person opens the public surface, is it
reachable, fast, light, and coherent? This organ makes visitor-experience an EXECUTABLE predicate —
the seo-audit.py of the front door, one rung past "the link resolves" (link-health) into "the page is
actually a good experience."

The surface list DERIVES from the corpus links registry (never hand-listed): every deployment / page /
custom-domain link, deduped by normalized URL. The overlay (experience-surfaces.json) holds ONLY
budgets, default overrides, and skips — never URLs (garbage-in guard; URLs are owned by the registry).

Per-surface rungs (pass ⟺ X1..X7):

  X1 reachable   final HTTP status == 200 (after redirects)
  X2 ttfb        time-to-first-byte <= ttfb_ms budget (default 1500)
  X3 transfer    total bytes transferred <= max_kb budget (default 1500)
  X4 requests    request count <= max_requests budget (default 75)
  X5 images      zero broken images
  X6 console     zero console errors / pageerrors
  X7 title       <title> non-empty (== expected_title when the overlay declares one)

Largest asset {path, kb} is recorded but NEVER gates (diagnostic only).

Probe tiers (the sweep NEVER breaks the beat):
  A  Playwright sync API + pinned chromium — fresh context per surface, 25s nav cap, network totals
     for transfer bytes, per-surface try/except recording probe_error.
  B  fail-open: if playwright import/launch fails, degrade to requests-only (status, TTFB, doc size)
     and stamp "tier":"http". Only X1/X2/X3 are measurable there; X4/X5/X6 are recorded unknown and
     do not fail the http-tier surface.

No os.fork anywhere (macOS atfork doctrine) — subprocess.run only. PII-clean: public URLs + counts
only; console messages truncated 3×200 chars with query strings stripped.

Modes:
  python3 scripts/experience-audit.py --sweep                 # audit every surface -> logs/experience-audit.json
  python3 scripts/experience-audit.py --surface <id> --check  # per-surface done-predicate (exit 0 ⟺ pass)
  python3 scripts/experience-audit.py --check                 # estate posture: exit 0 ⟺ no failing surface
  python3 scripts/experience-audit.py --doctor                # offline registry/overlay parity

Env: LIMEN_EXPERIENCE_SURFACES (overlay path), LIMEN_CORPVS_ROOT (links-registry home),
LIMEN_EXPERIENCE_TIMEOUT. Test overrides: --surfaces / --links-registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.resolve()
AUDIT = ROOT / "logs" / "experience-audit.json"
HISTORY = ROOT / "logs" / "experience" / "history.jsonl"
SHOTS_DIR = ROOT / "logs" / "experience" / "shots"
OVERLAY_DEFAULT = ROOT / "experience-surfaces.json"
JUDGMENTS = ROOT / "institutio" / "observatory" / "experience-judgments.yaml"

SCHEMA = "limen.experience_audit.v1"
KEEP_KINDS = {"deployment", "page", "custom-domain"}
DEFAULT_TTFB_MS = 1500
DEFAULT_MAX_KB = 1500
DEFAULT_MAX_REQUESTS = 75
NAV_CAP_S = 25
VALID_VERDICTS = {"pass", "fail"}
SCORE_KEYS = ("layout", "typography", "coherence", "trust")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(label: str) -> str:
    return _SLUG_RE.sub("-", (label or "").strip().lower()).strip("-")


def _normalize_url(url: str) -> str:
    """Deterministic URL key for dedupe: lowercase scheme+host, strip default port, drop fragment,
    collapse a bare-root path, strip a single trailing slash on non-root paths."""
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip().lower()
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower()
    netloc = host
    if p.port and not ((scheme == "http" and p.port == 80) or (scheme == "https" and p.port == 443)):
        netloc = f"{host}:{p.port}"
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path or "/", "", p.query, ""))


def _links_registry_path(override: str | None) -> Path:
    if override:
        return Path(override)
    corpvs = os.environ.get("LIMEN_CORPVS_ROOT")
    if not corpvs:
        workspace = os.environ.get("LIMEN_WORKSPACE_ROOT") or str(Path.home() / "Workspace")
        corpvs = str(Path(workspace) / "organvm-corpvs-testamentvm")
    return Path(corpvs) / "links-registry.json"


def _overlay_path(override: str | None) -> Path:
    if override:
        return Path(override)
    env = os.environ.get("LIMEN_EXPERIENCE_SURFACES")
    return Path(env) if env else OVERLAY_DEFAULT


def load_overlay(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def derive_surfaces(registry_path: Path, overlay: dict) -> list[dict]:
    """Read the links registry from disk, then derive the surface list (see derive_surfaces_from_links).
    A missing/unparseable registry yields an empty list (fail-open: the sweep skips)."""
    try:
        reg = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        reg = {}
    return derive_surfaces_from_links(reg.get("links") or [], overlay)


def derive_surfaces_from_links(links: list[dict], overlay: dict) -> list[dict]:
    """Derive the ordered surface list from a links list, overlaid with budgets/skips.

    kind ∈ KEEP_KINDS; funding dropped; deduped by normalized URL (first-seen wins). id = slugified
    label (fallback: hostname). Overlay ``surfaces[id]`` may override budgets + expected_title;
    overlay ``skip[id]`` drops a surface entirely. Overlay NEVER contributes URLs.
    """
    defaults = overlay.get("defaults") or {}
    over = overlay.get("surfaces") or {}
    skips = overlay.get("skip") or {}
    ttfb_d = int(defaults.get("ttfb_ms", DEFAULT_TTFB_MS))
    kb_d = int(defaults.get("max_kb", DEFAULT_MAX_KB))
    req_d = int(defaults.get("max_requests", DEFAULT_MAX_REQUESTS))

    seen_urls: set[str] = set()
    seen_ids: dict[str, int] = {}
    surfaces: list[dict] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        if link.get("kind") not in KEEP_KINDS:
            continue
        url = str(link.get("url") or "").strip()
        if not url:
            continue
        norm = _normalize_url(url)
        if norm in seen_urls:
            continue
        seen_urls.add(norm)
        label = str(link.get("label") or "")
        sid = _slugify(label) or (urlparse(url).hostname or "surface").lower().replace(".", "-")
        # disambiguate colliding ids deterministically
        if sid in seen_ids:
            seen_ids[sid] += 1
            sid = f"{sid}-{seen_ids[sid]}"
        else:
            seen_ids[sid] = 0
        if sid in skips:
            continue
        ov = over.get(sid) or {}
        surfaces.append(
            {
                "id": sid,
                "url": url,
                "kind": link.get("kind"),
                "label": label,
                "ttfb_ms": int(ov.get("ttfb_ms", ttfb_d)),
                "max_kb": int(ov.get("max_kb", kb_d)),
                "max_requests": int(ov.get("max_requests", req_d)),
                "expected_title": ov.get("expected_title"),
            }
        )
    return surfaces


# --------------------------------------------------------------------------- scoring


def _score_rungs(result: dict, surface: dict) -> dict[str, bool | None]:
    """X1..X7 from a probe result. http-tier leaves X4/X5/X6 as None (unknown, non-gating)."""
    tier = result.get("tier")
    status = result.get("status")
    ttfb = result.get("ttfb_ms")
    kb = result.get("transfer_kb")
    reqs = result.get("requests")
    broken = result.get("broken_images")
    console = result.get("console_errors")
    title = result.get("title")

    x1 = status == 200
    x2 = isinstance(ttfb, (int, float)) and ttfb <= surface["ttfb_ms"]
    x3 = isinstance(kb, (int, float)) and kb <= surface["max_kb"]
    if tier == "http":
        x4: bool | None = None
        x5: bool | None = None
        x6: bool | None = None
    else:
        x4 = isinstance(reqs, int) and reqs <= surface["max_requests"]
        x5 = broken == 0
        x6 = console == 0
    expected = surface.get("expected_title")
    title_nonempty = bool((title or "").strip())
    if expected:
        x7 = title_nonempty and (title or "").strip() == str(expected).strip()
    else:
        x7 = title_nonempty
    return {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5, "X6": x6, "X7": x7}


def _passes(rungs: dict[str, bool | None]) -> bool:
    """pass ⟺ every gating rung is True. A None rung (http-tier unknown) does not fail the surface,
    but X1/X2/X3/X7 must be measurable and True on every tier."""
    for key in ("X1", "X2", "X3", "X7"):
        if rungs.get(key) is not True:
            return False
    for key in ("X4", "X5", "X6"):
        if rungs.get(key) is False:
            return False
    return True


# --------------------------------------------------------------------------- probes (tier B: http)


def _strip_qs(url: str) -> str:
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return url


def _truncate_console(messages: list[str]) -> list[str]:
    """PII-clean: strip query strings, cap at 3 messages of 200 chars each."""
    out: list[str] = []
    for msg in messages[:3]:
        cleaned = re.sub(r"\?[^\s]*", "", str(msg))
        out.append(cleaned[:200])
    return out


def _probe_http(surface: dict, timeout_s: int) -> dict:
    """Tier B fail-open: requests-only. status (after redirects), TTFB, doc size. Never raises."""
    result: dict = {"tier": "http", "id": surface["id"], "url": surface["url"]}
    try:
        import requests
    except Exception as exc:  # pragma: no cover - requests is a declared test dep
        result["probe_error"] = f"requests unavailable: {exc}"
        return result
    try:
        start = time.monotonic()
        resp = requests.get(
            surface["url"],
            timeout=min(timeout_s, 20),
            allow_redirects=True,
            headers={"User-Agent": "limen-experience-audit/1.0"},
            stream=True,
        )
        ttfb_ms = int((time.monotonic() - start) * 1000)
        body = resp.content  # forces the full read for a transfer estimate
        result["status"] = resp.status_code
        result["ttfb_ms"] = ttfb_ms
        result["transfer_kb"] = round(len(body) / 1024, 1)
        m = re.search(r"<title[^>]*>(.*?)</title>", body.decode("utf-8", "replace"), re.I | re.S)
        result["title"] = m.group(1).strip() if m else ""
        result["largest_asset"] = {"path": _strip_qs(surface["url"]), "kb": result["transfer_kb"]}
    except Exception as exc:
        result["probe_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return result


# --------------------------------------------------------------------------- probes (tier A: playwright)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _probe_playwright(surfaces: list[dict], timeout_s: int) -> list[dict] | None:
    """Tier A: one browser, fresh context per surface. Returns None if playwright can't import/launch
    (caller degrades to tier B). Per-surface try/except records probe_error; a single surface failure
    never aborts the sweep."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    results: list[dict] = []
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=True)
            except Exception:
                return None
            try:
                for surface in surfaces:
                    results.append(_probe_one_playwright(browser, surface, timeout_s))
            finally:
                browser.close()
    except Exception:
        return None
    return results


def _probe_one_playwright(browser, surface: dict, timeout_s: int) -> dict:
    result: dict = {"tier": "playwright", "id": surface["id"], "url": surface["url"]}
    context = None
    try:
        context = browser.new_context(user_agent="limen-experience-audit/1.0")
        page = context.new_page()

        console_errors = [0]
        console_messages: list[str] = []
        request_count = [0]
        transfer_bytes = [0]
        assets: list[tuple[str, int]] = []

        def _on_console(msg):
            try:
                if msg.type == "error":
                    console_errors[0] += 1
                    console_messages.append(msg.text)
            except Exception:
                pass

        def _on_pageerror(exc):
            console_errors[0] += 1
            console_messages.append(str(exc))

        def _on_request(_req):
            request_count[0] += 1

        def _on_response(resp):
            try:
                clen = resp.headers.get("content-length")
                n = int(clen) if clen and clen.isdigit() else 0
                transfer_bytes[0] += n
                if n:
                    assets.append((_strip_qs(resp.url), n))
            except Exception:
                pass

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)
        page.on("request", _on_request)
        page.on("response", _on_response)

        start = time.monotonic()
        response = page.goto(surface["url"], wait_until="load", timeout=min(NAV_CAP_S, timeout_s) * 1000)
        ttfb_ms = int((time.monotonic() - start) * 1000)

        try:
            page.wait_for_timeout(500)
        except Exception:
            pass

        status = response.status if response else None
        title = ""
        try:
            title = (page.title() or "").strip()
        except Exception:
            pass

        try:
            broken = page.evaluate(
                "() => Array.from(document.images).filter(im => im.complete && im.naturalWidth === 0).length"
            )
        except Exception:
            broken = 0

        # capture screenshot (best-effort; never gates)
        shot_sha = None
        shot_path = SHOTS_DIR / f"{surface['id']}.png"
        try:
            SHOTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot_path), full_page=False)
            shot_sha = hashlib.sha256(shot_path.read_bytes()).hexdigest()
        except Exception:
            shot_sha = None

        transfer_kb = round(transfer_bytes[0] / 1024, 1)
        if assets:
            path, nbytes = max(assets, key=lambda a: a[1])
            largest = {"path": path, "kb": round(nbytes / 1024, 1)}
        else:
            largest = {"path": _strip_qs(surface["url"]), "kb": transfer_kb}

        result.update(
            {
                "status": status,
                "ttfb_ms": ttfb_ms,
                "transfer_kb": transfer_kb,
                "requests": request_count[0],
                "broken_images": broken,
                "console_errors": console_errors[0],
                "console_messages": _truncate_console(console_messages),
                "title": title,
                "largest_asset": largest,
                "screenshot_sha256": shot_sha,
                "captured_at": _now_iso(),
            }
        )
    except Exception as exc:
        result["probe_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
    return result


# --------------------------------------------------------------------------- sweep / build artifact


def run_probes(surfaces: list[dict], timeout_s: int) -> tuple[str, list[dict]]:
    """Return (tier, results). Prefer playwright; degrade to http fail-open."""
    pw_results = _probe_playwright(surfaces, timeout_s)
    if pw_results is not None:
        return "playwright", pw_results
    return "http", [_probe_http(s, timeout_s) for s in surfaces]


def _p50(values: list[int]) -> int | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return int((s[mid - 1] + s[mid]) / 2)


def build_artifact(surfaces: list[dict], tier: str, results: list[dict]) -> dict:
    by_id = {r["id"]: r for r in results}
    out_surfaces: dict[str, dict] = {}
    failing: list[str] = []
    ttfbs: list[int] = []
    max_transfer = 0.0
    for surface in surfaces:
        r = by_id.get(surface["id"], {"tier": tier, "id": surface["id"], "url": surface["url"]})
        rungs = _score_rungs(r, surface)
        ok = _passes(rungs) and not r.get("probe_error")
        if not ok:
            failing.append(surface["id"])
        if isinstance(r.get("ttfb_ms"), (int, float)):
            ttfbs.append(int(r["ttfb_ms"]))
        if isinstance(r.get("transfer_kb"), (int, float)):
            max_transfer = max(max_transfer, float(r["transfer_kb"]))
        out_surfaces[surface["id"]] = {
            "url": surface["url"],
            "kind": surface["kind"],
            "tier": r.get("tier", tier),
            "budgets": {
                "ttfb_ms": surface["ttfb_ms"],
                "max_kb": surface["max_kb"],
                "max_requests": surface["max_requests"],
            },
            "rungs": rungs,
            "pass": ok,
            "status": r.get("status"),
            "ttfb_ms": r.get("ttfb_ms"),
            "transfer_kb": r.get("transfer_kb"),
            "requests": r.get("requests"),
            "broken_images": r.get("broken_images"),
            "console_errors": r.get("console_errors"),
            "console_messages": r.get("console_messages"),
            "title": r.get("title"),
            "largest_asset": r.get("largest_asset"),
            "screenshot_sha256": r.get("screenshot_sha256"),
            "captured_at": r.get("captured_at"),
            "probe_error": r.get("probe_error"),
        }
    body = {
        "schema": SCHEMA,
        "generated_at": _now_iso(),
        "tier": tier,
        "audited": len(surfaces),
        "passing": len(surfaces) - len(failing),
        "failing": sorted(failing),
        "p50_ttfb_ms": _p50(ttfbs),
        "max_transfer_kb": round(max_transfer, 1),
        "surfaces": dict(sorted(out_surfaces.items())),
    }
    return body


def _append_history(body: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "ts": body["generated_at"],
        "tier": body["tier"],
        "audited": body["audited"],
        "passing": body["passing"],
        "failing_ids": body["failing"],
        "p50_ttfb_ms": body["p50_ttfb_ms"],
        "max_transfer_kb": body["max_transfer_kb"],
    }
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, sort_keys=True) + "\n")


def cmd_sweep(surfaces_path: str | None, registry_path: str | None) -> int:
    overlay = load_overlay(_overlay_path(surfaces_path))
    surfaces = derive_surfaces(_links_registry_path(registry_path), overlay)
    if not surfaces:
        print("[experience-audit] no surfaces derived from the links registry (skip)")
        return 0
    timeout_s = int(os.environ.get("LIMEN_EXPERIENCE_TIMEOUT", "900"))
    tier, results = run_probes(surfaces, timeout_s)
    body = build_artifact(surfaces, tier, results)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    _append_history(body)
    print(
        f"[experience-audit] swept {body['audited']} surfaces [tier={tier}]: "
        f"{body['passing']} pass, {len(body['failing'])} fail -> {AUDIT.relative_to(ROOT)}"
    )
    if body["failing"]:
        print("   failing: " + ", ".join(body["failing"][:12]))
    return 0


def cmd_check() -> int:
    try:
        body = json.loads(AUDIT.read_text(encoding="utf-8"))
    except Exception:
        print("[experience-audit] no sweep artifact yet — run --sweep first (skip)")
        return 0
    failing = body.get("failing") or []
    if failing:
        print(
            f"[experience-audit] {len(failing)}/{body.get('audited')} surfaces below visitor-experience budget "
            f"[tier={body.get('tier')}]"
        )
        for sid in failing[:10]:
            print(f"   {sid}")
        return 1
    print(f"[experience-audit] all {body.get('audited')} surfaces meet their visitor-experience budget")
    return 0


def cmd_check_surface(sid: str) -> int:
    try:
        body = json.loads(AUDIT.read_text(encoding="utf-8"))
    except Exception:
        print(f"[experience-audit] {sid}: no sweep artifact yet — run --sweep first")
        return 1
    entry = (body.get("surfaces") or {}).get(sid)
    if entry is None:
        print(f"[experience-audit] {sid}: not in the last sweep — check the id or re-sweep")
        return 1
    rungs = entry.get("rungs") or {}
    misses = sorted(k for k, v in rungs.items() if v is False)
    ok = bool(entry.get("pass"))
    print(
        f"[experience-audit] {sid}: {'PASS' if ok else 'FAIL'}" + (f" — failing {', '.join(misses)}" if misses else "")
    )
    return 0 if ok else 1


# --------------------------------------------------------------------------- doctor (offline, det)


def cmd_doctor(surfaces_path: str | None, registry_path: str | None) -> int:
    fails: list[str] = []
    overlay_file = _overlay_path(surfaces_path)
    overlay: dict = {}
    try:
        overlay = json.loads(overlay_file.read_text(encoding="utf-8")) if overlay_file.exists() else {}
    except Exception as exc:
        print(f"[experience-audit] doctor: overlay unparseable ({exc})")
        return 1

    # The overlay PUBLISHES: it must carry no URLs and no secrets. Scan the CONFIG values only,
    # never the documentation keys (any key starting with '_', e.g. _doc, which legitimately explains
    # the no-URL / no-secret rule in prose).
    def _config_strings(obj) -> list[str]:
        out: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and k.startswith("_"):
                    continue  # documentation key — not config
                if isinstance(k, str):
                    out.append(k)
                out.extend(_config_strings(v))
        elif isinstance(obj, list):
            for item in obj:
                out.extend(_config_strings(item))
        elif isinstance(obj, str):
            out.append(obj)
        return out

    config_blob = " ".join(_config_strings(overlay))
    if re.search(r"https?://", config_blob):
        fails.append("overlay: a config value contains a URL — URLs are owned by the links registry, not the overlay")
    for tok in ("token", "secret", "api_key", "apikey", "password", "bearer"):
        if re.search(tok, config_blob, re.I):
            fails.append(
                f"overlay: a config value contains a '{tok}' token — the overlay publishes; never put secrets here"
            )

    defaults = overlay.get("defaults") or {}
    for key in ("ttfb_ms", "max_kb", "max_requests"):
        if key in defaults:
            try:
                if int(defaults[key]) <= 0:
                    fails.append(f"overlay.defaults.{key}: must be a positive integer")
            except (TypeError, ValueError):
                fails.append(f"overlay.defaults.{key}: must be a positive integer")

    # every overlay surface/skip key must resolve to a derived id (garbage-in guard). Validate keys
    # against the surfaces derived WITHOUT skips so a skip key still resolves.
    base_surfaces = derive_surfaces(_links_registry_path(registry_path), {"defaults": defaults})
    base_ids = {s["id"] for s in base_surfaces}
    for sid, spec in (overlay.get("surfaces") or {}).items():
        if sid not in base_ids:
            fails.append(f"overlay.surfaces['{sid}']: does not resolve to any derived surface id")
        if isinstance(spec, dict):
            for key in ("ttfb_ms", "max_kb", "max_requests"):
                if key in spec:
                    try:
                        if int(spec[key]) <= 0:
                            fails.append(f"overlay.surfaces['{sid}'].{key}: must be a positive integer")
                    except (TypeError, ValueError):
                        fails.append(f"overlay.surfaces['{sid}'].{key}: must be a positive integer")
    for sid in overlay.get("skip") or {}:
        if sid not in base_ids:
            fails.append(f"overlay.skip['{sid}']: does not resolve to any derived surface id")

    # judgment register parity
    reg: dict = {}
    if JUDGMENTS.exists():
        try:
            reg = yaml.safe_load(JUDGMENTS.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            print(f"[experience-audit] doctor: experience-judgments.yaml unparseable ({exc})")
            return 1
        if "schema_version" not in reg:
            fails.append("experience-judgments.yaml: missing schema_version")
        for sid, rows in (reg.get("judgments") or {}).items():
            row_list = rows if isinstance(rows, list) else [rows]
            for i, row in enumerate(row_list):
                where = f"judgment '{sid}'[{i}]"
                if not isinstance(row, dict):
                    fails.append(f"{where}: not a mapping")
                    continue
                verdict = row.get("verdict")
                if verdict not in VALID_VERDICTS:
                    fails.append(f"{where}: verdict {verdict!r} not in {sorted(VALID_VERDICTS)}")
                scores = row.get("scores") or {}
                for k in SCORE_KEYS:
                    if k in scores:
                        try:
                            v = int(scores[k])
                            if not (0 <= v <= 5):
                                raise ValueError
                        except (TypeError, ValueError):
                            fails.append(f"{where}: score '{k}' must be an integer 0-5")

    if fails:
        print(f"[experience-audit] doctor: {len(fails)} registry/overlay defect(s):")
        for f in fails:
            print(f"   {f}")
        return 1

    hint = ""
    try:
        import playwright  # noqa: F401
    except Exception:
        hint = " (advisory: playwright not installed — sweeps degrade to the http tier, which is legal)"
    print(f"[experience-audit] doctor: overlay + judgment registry parity green{hint}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Visitor-experience standard as a predicate (experience-v1).")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--surface")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--surfaces", help="overlay path override (tests)")
    ap.add_argument("--links-registry", dest="links_registry", help="links-registry.json path override (tests)")
    args = ap.parse_args(argv)

    if args.doctor:
        return cmd_doctor(args.surfaces, args.links_registry)
    if args.sweep:
        return cmd_sweep(args.surfaces, args.links_registry)
    if args.surface and args.check:
        return cmd_check_surface(args.surface)
    if args.check:
        return cmd_check()
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
