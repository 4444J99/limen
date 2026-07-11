"""Deterministic README / communication-surface feature extraction.

Turns a repo's README markdown + metadata into a structured feature record: the
concrete things that separate a legible project from an illegible one (a named user,
a one-line install, a demo above the fold, a copy-paste command, …). Every helper is a
**pure function** over its inputs — no network, no LLM, no clock — so ``extract`` twice
on the same input yields a byte-identical dict (the determinism property the doctor
asserts). The optional LLM enrichment is a recorded phase-2 residual; v1 is regex/string
only, which keeps the whole research loop hermetically testable.
"""

from __future__ import annotations

import re

# The first ~1200 chars are the "above the fold" region a visitor sees first.
_FOLD = 1200

_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|<img\b[^>]*src=[\"']([^\"']+)[\"']", re.IGNORECASE)
_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)

_INSTALL_CMD_RE = re.compile(
    r"\b(pip install|npm install|npm i|pnpm add|yarn add|brew install|cargo install|go install|"
    r"uv add|uvx|npx|docker run|docker pull|curl\s|wget\s|git clone)\b",
    re.IGNORECASE,
)
_USER_RE = re.compile(
    r"\b(for developers|for teams|for engineers|for researchers|for designers|for anyone who|"
    r"built for|designed for|developers who|teams who|people who|for AI agents|for agents)\b",
    re.IGNORECASE,
)
_PROBLEM_RE = re.compile(
    r"\b(problem|pain|tired of|struggle|frustrat|without having to|no more|stop\s+\w+ing|avoid the)\b",
    re.IGNORECASE,
)
_OUTCOME_RE = re.compile(
    r"\b(so you can|in (?:one|1|a single) (?:click|command|line|step)|instantly|in seconds|"
    r"get \w+ (?:in|fast)|automatically|without)\b",
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(
    r"\b(vs\.?|versus|compared to|alternative to|unlike|instead of)\b|\|\s*(feature|comparison)",
    re.IGNORECASE,
)
_API_RE = re.compile(r"\b(import |from \w+ import|require\(|curl |fetch\(|await |def |class |function )\b")
_HEDGE_RE = re.compile(
    r"\b(maybe|perhaps|might|possibly|somewhat|various|etc\.?|and more|among others|"
    r"a variety of|flexible|powerful|robust|seamless|cutting-edge|revolutionary)\b",
    re.IGNORECASE,
)
_USECASE_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*(use cases?|examples?|what you can|recipes?)", re.IGNORECASE | re.MULTILINE
)
_FUNDING_RE = re.compile(
    r"(sponsor|ko-fi|patreon|opencollective|buy me a coffee|/pricing|paddle|stripe)", re.IGNORECASE
)


def _norm(md: str) -> str:
    return md or ""


def first_sentence(md: str) -> str | None:
    """The first meaningful sentence — the project's one-line promise (or None)."""
    for line in _norm(md).splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "!", "<", "|", ">", "-", "*", "```", "[!")):
            continue
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)  # unwrap links → text
        s = re.sub(r"[*_`]", "", s).strip()
        if len(s) < 8:
            continue
        m = re.search(r"(.+?[.!?])(\s|$)", s)
        return (m.group(1) if m else s).strip()[:280]
    return None


def _fold(md: str) -> str:
    return _norm(md)[:_FOLD]


def names_user(md: str) -> bool:
    return bool(_USER_RE.search(_norm(md)))


def names_problem(md: str) -> bool:
    return bool(_PROBLEM_RE.search(_norm(md)))


def names_outcome(md: str) -> bool:
    return bool(_OUTCOME_RE.search(_norm(md)))


def steps_to_install(md: str) -> int | None:
    """Count of distinct install/run commands before the first one appears in a fence.
    Fewer is better; None when no install path is shown at all."""
    fences = [(m.start(), m.group(2)) for m in _FENCE_RE.finditer(_norm(md))]
    count = 0
    for _pos, body in fences:
        for _ln in body.splitlines():
            if _INSTALL_CMD_RE.search(_ln):
                count += 1
    return count or None


def steps_to_first_result(md: str) -> int | None:
    """Distinct commands (fenced lines) up to and including the first non-install code line —
    a proxy for 'how many keystrokes before something happens'. None when no runnable code."""
    for m in _FENCE_RE.finditer(_norm(md)):
        lines = [ln for ln in m.group(2).splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if lines:
            return len(lines)
    return None


def demo_above_fold(md: str) -> bool:
    """An image/gif/asciinema/video visible in the first screen."""
    fold = _fold(md)
    return bool(_IMG_RE.search(fold)) or "asciinema" in fold.lower() or "<video" in fold.lower()


def _count_images(md: str) -> tuple[int, int]:
    imgs = gifs = 0
    for m in _IMG_RE.finditer(_norm(md)):
        url = (m.group(1) or m.group(2) or "").lower()
        imgs += 1
        if url.endswith(".gif") or "gif" in url:
            gifs += 1
    return imgs, gifs


def has_copy_paste_command(md: str) -> bool:
    """A shell fence near the top the visitor can paste."""
    for m in _FENCE_RE.finditer(_fold(md) + "\n"):
        lang = (m.group(1) or "").strip().lower()
        if lang in ("sh", "bash", "shell", "console", "zsh", "") and _INSTALL_CMD_RE.search(m.group(2)):
            return True
    return False


def has_api_example(md: str) -> bool:
    for m in _FENCE_RE.finditer(_norm(md)):
        if _API_RE.search(m.group(2)):
            return True
    return False


def lists_use_cases(md: str) -> int:
    """Number of use-case/example headings — a rough count of demonstrated applications."""
    return len(_USECASE_HEADING_RE.findall(_norm(md)))


def has_comparison(md: str) -> bool:
    return bool(_COMPARISON_RE.search(_norm(md)))


def funding_path(md: str, repo_meta: dict) -> str | None:
    m = _FUNDING_RE.search(_norm(md))
    if m:
        return m.group(1).lower()
    # repo funding metadata (GitHub surfaces this via .github/FUNDING.yml → repo has no direct field,
    # but a homepage that is a pricing/app URL is a weak funding signal)
    home = (repo_meta or {}).get("homepage") or ""
    if isinstance(home, str) and re.search(r"pricing|/app|\.app\b", home, re.IGNORECASE):
        return "homepage-commercial"
    return None


def license_named(repo_meta: dict) -> str | None:
    lic = (repo_meta or {}).get("license")
    if isinstance(lic, dict):
        return lic.get("spdx_id") or lic.get("key")
    return lic if isinstance(lic, str) else None


def ambiguity_score(md: str) -> float:
    """0..1 density of hedge/jargon words per 100 words — higher is worse (less legible)."""
    words = re.findall(r"[A-Za-z']+", _norm(md))
    if not words:
        return 0.0
    hedges = len(_HEDGE_RE.findall(_norm(md)))
    return round(min(1.0, hedges / (len(words) / 100.0) / 10.0), 3)


def extract(readme_md: str, repo_meta: dict | None = None) -> dict:
    """The full feature record. Deterministic: same inputs → identical dict."""
    repo_meta = repo_meta or {}
    screenshots, gifs = _count_images(readme_md)
    return {
        "first_sentence": first_sentence(readme_md),
        "names_user": names_user(readme_md),
        "names_problem": names_problem(readme_md),
        "names_outcome": names_outcome(readme_md),
        "steps_to_install": steps_to_install(readme_md),
        "steps_to_first_result": steps_to_first_result(readme_md),
        "demo_above_fold": demo_above_fold(readme_md),
        "screenshots": screenshots,
        "gifs": gifs,
        "copy_paste_command": has_copy_paste_command(readme_md),
        "api_example": has_api_example(readme_md),
        "use_cases": lists_use_cases(readme_md),
        "comparison": has_comparison(readme_md),
        "license": license_named(repo_meta),
        "funding_path": funding_path(readme_md, repo_meta),
        "ambiguity": ambiguity_score(readme_md),
    }


# The boolean/int feature keys a mechanism can be built from (the ones a winner can "have"
# and a control can "lack"). Excludes free-text/score fields (first_sentence, license, ambiguity).
BINARY_FEATURES = (
    "names_user",
    "names_problem",
    "names_outcome",
    "demo_above_fold",
    "copy_paste_command",
    "api_example",
    "comparison",
)
