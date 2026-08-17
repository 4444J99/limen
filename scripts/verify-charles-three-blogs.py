#!/usr/bin/env python3
"""Verify the Downs Style cotton → silk → cotton-versus-silk package."""

from __future__ import annotations

import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
CHARLES = ROOT / "docs" / "continuations" / "charles"
DOCX = CHARLES / "downs-style-three-new-blogs-review-copy.docx"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

PACKAGES = {
    "cotton": {
        "path": CHARLES / "cotton-summer-post.md",
        "docx": CHARLES / "downs-style-cotton-summer-charles-review.docx",
        "title": "Cotton Tops and Bottoms for Summer: What Kind Are You Actually Wearing?",
        "min_popups": 6,
        "required": [
            "Same plant, completely different personalities.",
            "cotton wins both halves only when I let it become two different fabrics",
            "Silk gets the next post",
            "https://cottonworks.com/",
            "https://supima.com/faq/",
        ],
    },
    "silk": {
        "path": CHARLES / "silk-summer-post.md",
        "docx": CHARLES / "downs-style-silk-charles-review.docx",
        "title": "Silk, Satin, and Charmeuse: What Are You Actually Buying?",
        "min_popups": 7,
        "required": [
            "Cotton made me stop trusting one word on a clothing label.",
            "Silk is the fiber. Satin is a weave.",
            "It loses the jobs that demand hard sitting",
            "https://home.nps.gov/",
            "https://www.ftc.gov/",
        ],
    },
    "comparison": {
        "path": CHARLES / "cotton-vs-silk-post.md",
        "docx": CHARLES / "downs-style-cotton-vs-silk-charles-review.docx",
        "title": "Cotton vs. Silk: Who Wins Each Part of the Wardrobe?",
        "min_popups": 9,
        "required": [
            "Cotton wins my ordinary first layer.",
            "Cotton wins ease. Silk wins the line.",
            "Sleepwear is the round I am calling a draw.",
            "cotton does the living; silk does the entrance",
            "https://pmc.ncbi.nlm.nih.gov/",
        ],
    },
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def body_from(text: str) -> str:
    match = re.search(
        r"^## Squarespace body copy\s*$\n(.*?)(?=^## )",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError("missing Squarespace body section")
    return match.group(1).strip()


def word_count(text: str) -> int:
    plain = re.sub(r"<[^>]+>", " ", text)
    return len(re.findall(r"\b[\w’'-]+\b", plain))


def normalized_text(text: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = plain.replace("**", "").replace("*", "")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", plain)).strip()


def docx_paragraphs(root: ET.Element) -> set[str]:
    paragraphs: set[str] = set()
    for paragraph in root.findall(".//w:body/w:p", NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
        if normalized := normalized_text(text):
            paragraphs.add(normalized)
    return paragraphs


def attribute(element: ET.Element, name: str) -> str | None:
    return element.get(f"{{{W_NS}}}{name}")


def verify_docx(errors: list[str], source_texts: list[str]) -> None:
    if not DOCX.exists():
        fail(errors, f"missing combined review copy {DOCX.relative_to(ROOT)}")
        return

    try:
        with ZipFile(DOCX) as archive:
            names = set(archive.namelist())
            if any(re.fullmatch(r"word/(?:header|footer)\d+\.xml", name) for name in names):
                fail(errors, "review DOCX contains header/footer parts")
            document_root = ET.fromstring(archive.read("word/document.xml"))
            styles_root = ET.fromstring(archive.read("word/styles.xml"))
            core_root = ET.fromstring(archive.read("docProps/core.xml"))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        fail(errors, f"review DOCX is not structurally valid: {exc}")
        return

    paragraphs = docx_paragraphs(document_root)
    for required in (
        "Downs Style Summer Fabric Trilogy",
        *[spec["title"] for spec in PACKAGES.values()],
    ):
        if normalized_text(required) not in paragraphs:
            fail(errors, f"review DOCX missing paragraph {required!r}")
    if not any("No website has been edited or published." in p for p in paragraphs):
        fail(errors, "review DOCX is missing the no-publish status")

    for text in source_texts:
        blocks = [
            block.strip()
            for block in re.split(r"\n\s*\n", body_from(text))
            if block.strip()
        ]
        blocks.extend(re.findall(r"^\*\*(?:Trigger|Pop-up):\*\*\s*(.+)$", text, re.MULTILINE))
        for block in blocks:
            expected = normalized_text(block)
            if expected and expected not in paragraphs:
                fail(errors, f"review DOCX missing source paragraph {expected!r}")

    if document_root.find('.//w:pStyle[@w:val="Title"]', NS) is not None:
        fail(errors, "review DOCX applies the Word Title style")

    section = document_root.find(".//w:sectPr", NS)
    if section is None:
        fail(errors, "review DOCX has no section properties")
    else:
        page_size = section.find("w:pgSz", NS)
        page_margin = section.find("w:pgMar", NS)
        if page_size is None or (attribute(page_size, "w"), attribute(page_size, "h")) != ("12240", "15840"):
            fail(errors, "review DOCX is not US Letter portrait")
        expected_margins = {
            "top": "1440",
            "right": "1440",
            "bottom": "1440",
            "left": "1440",
            "header": "708",
            "footer": "708",
        }
        if page_margin is None or any(
            attribute(page_margin, key) != value for key, value in expected_margins.items()
        ):
            fail(errors, "review DOCX page margins do not match google_docs_default")

    styles = {attribute(style, "styleId"): style for style in styles_root.findall("w:style", NS)}
    expected_styles = {
        "Normal": {"size": "22", "before": "0", "after": "160", "line": "276"},
        "Heading1": {"size": "40", "before": "400", "after": "120", "line": "276"},
        "Heading2": {"size": "32", "before": "360", "after": "120", "line": "276"},
        "Heading3": {"size": "28", "before": "320", "after": "80", "line": "276"},
    }
    for style_id, expected in expected_styles.items():
        style = styles.get(style_id)
        if style is None:
            fail(errors, f"review DOCX missing style {style_id}")
            continue
        fonts = style.find("w:rPr/w:rFonts", NS)
        size = style.find("w:rPr/w:sz", NS)
        spacing = style.find("w:pPr/w:spacing", NS)
        if fonts is None or attribute(fonts, "ascii") != "Arial" or attribute(fonts, "hAnsi") != "Arial":
            fail(errors, f"review DOCX style {style_id} does not use Arial")
        if size is None or attribute(size, "val") != expected["size"]:
            fail(errors, f"review DOCX style {style_id} has the wrong size")
        if spacing is None or any(attribute(spacing, key) != expected[key] for key in ("before", "after", "line")):
            fail(errors, f"review DOCX style {style_id} has the wrong spacing")

    dc_ns = "http://purl.org/dc/elements/1.1/"
    title = core_root.find(f"{{{dc_ns}}}title")
    if title is None or title.text != "Downs Style Summer Fabric Trilogy":
        fail(errors, "review DOCX has the wrong core title")


def verify_individual_docx(
    errors: list[str], name: str, spec: dict[str, object], source_text: str
) -> None:
    path = spec["docx"]
    if not isinstance(path, Path) or not path.exists():
        fail(errors, f"{name}: missing individual Charles review DOCX")
        return

    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            if any(re.fullmatch(r"word/(?:header|footer)\d+\.xml", item) for item in names):
                fail(errors, f"{name}: individual DOCX contains header/footer parts")
            document_root = ET.fromstring(archive.read("word/document.xml"))
            core_root = ET.fromstring(archive.read("docProps/core.xml"))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        fail(errors, f"{name}: individual DOCX is not structurally valid: {exc}")
        return

    title = spec["title"]
    if not isinstance(title, str):
        fail(errors, f"{name}: invalid title specification")
        return
    paragraphs = docx_paragraphs(document_root)
    if normalized_text(title) not in paragraphs:
        fail(errors, f"{name}: individual DOCX is missing its title")

    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n", body_from(source_text))
        if block.strip()
    ]
    blocks.extend(
        re.findall(r"^\*\*(?:Trigger|Pop-up):\*\*\s*(.+)$", source_text, re.MULTILINE)
    )
    for block in blocks:
        expected = normalized_text(block)
        if expected and expected not in paragraphs:
            fail(errors, f"{name}: individual DOCX missing source paragraph {expected!r}")

    other_titles = {
        normalized_text(other["title"])
        for other_name, other in PACKAGES.items()
        if other_name != name
    }
    if paragraphs.intersection(other_titles):
        fail(errors, f"{name}: individual DOCX contains another article")
    joined = " ".join(paragraphs)
    if re.search(r"\b(?:candle|Transcend Essentials)\b", joined, flags=re.IGNORECASE):
        fail(errors, f"{name}: individual DOCX contains queued companion copy")
    if re.search(r"(?:\*\*|```|<p\b)", joined):
        fail(errors, f"{name}: individual DOCX contains visible Markdown or HTML residue")
    if document_root.find('.//w:pStyle[@w:val="Title"]', NS) is not None:
        fail(errors, f"{name}: individual DOCX applies the Word Title style")

    dc_ns = "http://purl.org/dc/elements/1.1/"
    core_title = core_root.find(f"{{{dc_ns}}}title")
    if core_title is None or core_title.text != title:
        fail(errors, f"{name}: individual DOCX has the wrong core title")


def main() -> int:
    errors: list[str] = []
    body_counts: dict[str, int] = {}
    source_texts: list[str] = []

    for name, spec in PACKAGES.items():
        path = spec["path"]
        if not path.exists():
            fail(errors, f"{name}: missing {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        source_texts.append(text)

        for marker in (
            "# Downs Style editorial package",
            "## Page settings",
            "## Squarespace body copy",
            "## Common-error pop-ups",
            "## Placement checklist",
            "## Editorial guardrails",
            "## Fact-check notes",
            "## Sources",
        ):
            if marker not in text:
                fail(errors, f"{name}: missing section {marker}")
        if f"- **Title:** {spec['title']}" not in text:
            fail(errors, f"{name}: title mismatch")
        if text.count("**Trigger:**") < spec["min_popups"]:
            fail(errors, f"{name}: expected at least {spec['min_popups']} pop-up triggers")
        for required in spec["required"]:
            if required not in text:
                fail(errors, f"{name}: missing required text {required!r}")
        if re.search(r"\b(?:TODO|TBD|FIXME)\b", text, flags=re.IGNORECASE):
            fail(errors, f"{name}: contains an unresolved placeholder")

        try:
            body = body_from(text)
        except ValueError as exc:
            fail(errors, f"{name}: {exc}")
            continue
        count = word_count(body)
        body_counts[name] = count
        if not 600 <= count <= 1000:
            fail(errors, f"{name}: body word count {count} outside 600–1000")
        if re.search(r"https?://|\]\(", body):
            fail(errors, f"{name}: body contains an unapproved inline link")
        if re.search(r"\$\s?\d", body):
            fail(errors, f"{name}: body contains a price")

        banned_claims = (
            r"guaranteed to keep (?:you|everyone) cool",
            r"hypoallergenic",
            r"(?:improves?|protects?) (?:your )?(?:skin|hair|sleep)",
            r"(?:cotton|silk) is sustainable",
            r"works for (?:all|every) body",
        )
        for pattern in banned_claims:
            if re.search(pattern, body, flags=re.IGNORECASE):
                fail(errors, f"{name}: body matches prohibited claim {pattern!r}")

        plain_body = re.sub(r"<[^>]+>", " ", body)
        first_singular = len(re.findall(r"\b(?:I|me|my)\b", plain_body))
        first_plural = len(re.findall(r"\b(?:we|us|our)\b", plain_body, flags=re.IGNORECASE))
        if first_singular < 8 or first_singular <= first_plural:
            fail(errors, f"{name}: Charles first-person voice is not dominant")

        paragraphs = [
            re.sub(r"<[^>]+>", "", part).strip()
            for part in re.split(r"\n\s*\n", body)
            if part.strip()
        ]
        if any(word_count(paragraph) > 75 for paragraph in paragraphs):
            fail(errors, f"{name}: contains a paragraph longer than 75 words")

    index_path = CHARLES / "three-blog-package.md"
    if not index_path.exists():
        fail(errors, "missing three-blog package index")
    else:
        index = index_path.read_text(encoding="utf-8")
        for spec in PACKAGES.values():
            if spec["title"] not in index:
                fail(errors, f"package index missing {spec['title']!r}")
        if "No Squarespace page" not in index:
            fail(errors, "package index is missing the no-publish boundary")
        if "downs-style-three-new-blogs-review-copy.docx" not in index:
            fail(errors, "package index is missing the combined review copy")
        for spec in PACKAGES.values():
            docx = spec["docx"]
            if not isinstance(docx, Path) or docx.name not in index:
                fail(errors, "package index is missing an individual DOCX review copy")
        if "Charles-facing delivery is DOCX only" not in index:
            fail(errors, "package index is missing the no-Markdown delivery rule")
        if "candle-burning and Transcend Essentials stories remain queued companion drafts" not in index:
            fail(errors, "package index does not preserve the corrected scope")

    series_path = CHARLES / "summer-fabric-series.md"
    if not series_path.exists():
        fail(errors, "missing summer-fabric series index")
    else:
        series = series_path.read_text(encoding="utf-8")
        sequence = [spec["title"] for spec in PACKAGES.values()]
        positions = [series.find(title) for title in sequence]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            fail(errors, "summer-fabric series does not preserve cotton → silk → comparison order")

    if len(source_texts) == len(PACKAGES):
        verify_docx(errors, source_texts)
        for (name, spec), source_text in zip(PACKAGES.items(), source_texts, strict=True):
            verify_individual_docx(errors, name, spec, source_text)

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: Downs Style summer fabric trilogy verified")
    for name in ("cotton", "silk", "comparison"):
        print(f"  {name}: {body_counts[name]} body words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
