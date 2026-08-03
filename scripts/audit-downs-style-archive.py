#!/usr/bin/env python3
"""Inventory Downs Style's public blog archive from its sitemap and collection pages.

The committed inventory contains metadata and content fingerprints only. Pass
``--corpus-json`` to create a temporary full-text corpus for local voice analysis; raw
article text should not be committed by this workflow.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


BASE_URL = "https://www.downsstyle.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
USER_AGENT = "DownsStyleArchiveAudit/1.0 (+https://github.com/organvm/limen)"
POST_PATH = re.compile(
    r"^/(?P<collection>[^/]+)/(?P<year>\d{4})/(?P<month>\d{1,2})/"
    r"(?P<day>\d{1,2})/(?P<slug>[^/?#]+)/?$"
)
WORD = re.compile(r"\b[\w’'-]+\b", re.UNICODE)

COLLECTION_LABELS = {
    "gifts": "Gift Inspo",
    "look-book": "Look Book",
    "masks": "Masks",
    "new-blog": "Candles",
    "new-blog-1": "Interior Design",
    "new-blog-2": "Eat",
    "skincare": "Skincare",
    "travel": "Travel",
    "workoutsdiet": "Workouts/Diet",
}


@dataclass(frozen=True)
class SitemapPost:
    url: str
    lastmod: str


@dataclass
class PostRecord:
    published_date: str
    category: str
    collection: str
    title: str
    url: str
    discovery_sources: str
    sitemap_lastmod: str
    http_status: int | None
    final_url: str
    author: str
    tags: str
    word_count: int
    body_blocks: int
    content_sha256: str
    error: str


def fetch(url: str, *, timeout: float, attempts: int = 3) -> tuple[int, str, str]:
    """Return status, final URL, and decoded response text with bounded retries."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
                return response.status, response.geturl(), body
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def canonical_post_url(url: str) -> str | None:
    """Normalize a Downs Style dated-post URL or return None."""
    parsed = urlparse(urljoin(BASE_URL, url))
    if parsed.netloc.lower() not in {"downsstyle.com", "www.downsstyle.com"}:
        return None
    match = POST_PATH.match(parsed.path)
    if not match:
        return None
    path = parsed.path.rstrip("/")
    return f"{BASE_URL}{path}"


def parse_sitemap(xml_text: str) -> list[SitemapPost]:
    root = ET.fromstring(xml_text)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    posts: list[SitemapPost] = []
    for node in root.findall("s:url", namespace):
        location = node.findtext("s:loc", default="", namespaces=namespace)
        canonical = canonical_post_url(location)
        if not canonical:
            continue
        lastmod = node.findtext("s:lastmod", default="", namespaces=namespace)
        posts.append(SitemapPost(url=canonical, lastmod=lastmod))
    return posts


def discover_posts(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        canonical = canonical_post_url(anchor["href"])
        if canonical:
            urls.add(canonical)
    return urls


def discover_collection_posts(collection: str, *, timeout: float) -> set[str]:
    """Enumerate every public item exposed by a Squarespace collection."""
    page_url = f"{BASE_URL}/{collection}?format=json"
    visited_pages: set[str] = set()
    urls: set[str] = set()
    while page_url:
        if page_url in visited_pages:
            raise RuntimeError(f"pagination cycle detected for {collection}: {page_url}")
        visited_pages.add(page_url)
        _, _, response_text = fetch(page_url, timeout=timeout)
        payload = json.loads(response_text)
        for item in payload.get("items", []):
            canonical = canonical_post_url(item.get("fullUrl", ""))
            if canonical:
                urls.add(canonical)

        next_page = payload.get("pagination", {}).get("nextPageUrl")
        if not next_page:
            page_url = ""
            continue
        page_url = urljoin(BASE_URL, next_page)
        separator = "&" if "?" in page_url else "?"
        page_url = f"{page_url}{separator}format=json"
    return urls


def fallback_date_and_collection(url: str) -> tuple[str, str]:
    match = POST_PATH.match(urlparse(url).path)
    if not match:
        return "", ""
    values = match.groupdict()
    date = f"{values['year']}-{int(values['month']):02d}-{int(values['day']):02d}"
    return date, values["collection"]


def clean_text(node: BeautifulSoup) -> str:
    text = node.get_text(" ", strip=True)
    return " ".join(text.split())


def parse_post(
    url: str,
    *,
    sources: Iterable[str],
    lastmod: str,
    timeout: float,
) -> tuple[PostRecord, str]:
    fallback_date, collection = fallback_date_and_collection(url)
    category = COLLECTION_LABELS.get(collection, collection)
    try:
        status, final_url, html = fetch(url, timeout=timeout)
        soup = BeautifulSoup(html, "html.parser")
        article = soup.select_one("article.BlogItem")
        title_node = soup.select_one("h1.BlogItem-title")
        if title_node:
            title = clean_text(title_node)
        else:
            meta_title = soup.find("meta", attrs={"property": "og:title"})
            title = meta_title.get("content", "") if meta_title else ""
            title = re.sub(r"\s+—\s+Downs Style$", "", title).strip()

        date_node = soup.select_one("time.Blog-meta-item--date[datetime]")
        published_date = date_node.get("datetime", fallback_date) if date_node else fallback_date
        author_node = soup.select_one(".Blog-meta-item--author")
        author = clean_text(author_node) if author_node else ""
        tags = sorted(
            {
                clean_text(tag)
                for tag in soup.select(".Blog-meta-item--tags .Blog-meta-item-tag")
                if clean_text(tag)
            },
            key=str.casefold,
        )

        blocks: list[str] = []
        if article:
            for unwanted in article.select("script, style, noscript, .BlogItem-share"):
                unwanted.decompose()
            for block in article.select(".sqs-block-content"):
                text = clean_text(block)
                if text:
                    blocks.append(text)
            if not blocks:
                text = clean_text(article)
                if text:
                    blocks.append(text)
        body = "\n\n".join(blocks)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""
        record = PostRecord(
            published_date=published_date,
            category=category,
            collection=collection,
            title=title,
            url=url,
            discovery_sources=";".join(sorted(set(sources))),
            sitemap_lastmod=lastmod,
            http_status=status,
            final_url=final_url,
            author=author,
            tags=";".join(tags),
            word_count=len(WORD.findall(body)),
            body_blocks=len(blocks),
            content_sha256=digest,
            error="" if article else "article element not found",
        )
        return record, body
    except Exception as exc:  # noqa: BLE001 - inventory must retain failed URLs
        record = PostRecord(
            published_date=fallback_date,
            category=category,
            collection=collection,
            title="",
            url=url,
            discovery_sources=";".join(sorted(set(sources))),
            sitemap_lastmod=lastmod,
            http_status=None,
            final_url="",
            author="",
            tags="",
            word_count=0,
            body_blocks=0,
            content_sha256="",
            error=f"{type(exc).__name__}: {exc}",
        )
        return record, ""


def write_inventory(path: Path, records: list[PostRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(records[0]).keys()) if records else list(PostRecord.__annotations__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


def write_corpus(path: Path, records_and_bodies: list[tuple[PostRecord, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "published_date": record.published_date,
            "category": record.category,
            "title": record.title,
            "url": record.url,
            "body": body,
        }
        for record, body in records_and_bodies
    ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_site_inventory(path: Path, records: list[PostRecord]) -> None:
    """Write the bounded metadata used by the browsable archive site."""
    payload = [
        {
            "publishedDate": record.published_date[:10],
            "year": record.published_date[:4],
            "category": record.category,
            "title": record.title,
            "url": record.url,
            "author": record.author,
            "wordCount": record.word_count,
        }
        for record in reversed(records)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Metadata CSV output path")
    parser.add_argument(
        "--corpus-json",
        type=Path,
        help="Optional private full-text JSON output for local analysis",
    )
    parser.add_argument(
        "--site-json",
        type=Path,
        help="Optional bounded metadata JSON for the archive website",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 8:
        raise SystemExit("--workers must be between 1 and 8")

    _, _, sitemap_xml = fetch(SITEMAP_URL, timeout=args.timeout)
    sitemap_posts = parse_sitemap(sitemap_xml)
    sources_by_url: dict[str, set[str]] = {post.url: {"sitemap"} for post in sitemap_posts}
    lastmod_by_url = {post.url: post.lastmod for post in sitemap_posts}

    collections = sorted({fallback_date_and_collection(post.url)[1] for post in sitemap_posts})
    try:
        _, _, homepage_html = fetch(BASE_URL, timeout=args.timeout)
        for url in discover_posts(homepage_html):
            sources_by_url.setdefault(url, set()).add("homepage")
    except Exception as exc:  # noqa: BLE001 - continue with other discovery rails
        print(f"warning: homepage discovery failed: {exc}")

    for collection in collections:
        source = f"collection:{collection}"
        try:
            collection_urls = discover_collection_posts(
                collection,
                timeout=args.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - continue with sitemap coverage
            print(f"warning: {source} discovery failed: {exc}")
            continue
        print(f"discovered {len(collection_urls)} posts in {source}")
        for url in collection_urls:
            sources_by_url.setdefault(url, set()).add(source)

    def audit(url: str) -> tuple[PostRecord, str]:
        return parse_post(
            url,
            sources=sources_by_url[url],
            lastmod=lastmod_by_url.get(url, ""),
            timeout=args.timeout,
        )

    audited: list[tuple[PostRecord, str]] = []
    urls = sorted(sources_by_url)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(audit, url): url for url in urls}
        for index, future in enumerate(as_completed(futures), start=1):
            audited.append(future.result())
            if index % 25 == 0 or index == len(urls):
                print(f"audited {index}/{len(urls)} posts")

    audited.sort(
        key=lambda item: (
            item[0].published_date,
            item[0].category.casefold(),
            item[0].title.casefold(),
            item[0].url,
        )
    )
    records = [record for record, _ in audited]
    write_inventory(args.output, records)
    if args.corpus_json:
        write_corpus(args.corpus_json, audited)
    if args.site_json:
        write_site_inventory(args.site_json, records)

    failures = [record for record in records if record.error or record.http_status != 200]
    sitemap_only = [
        record for record in records if record.discovery_sources == "sitemap"
    ]
    non_sitemap = [record for record in records if not record.sitemap_lastmod]
    print(f"inventory: {len(records)} posts")
    print(f"sitemap-only: {len(sitemap_only)}")
    print(f"discovered outside sitemap: {len(non_sitemap)}")
    print(f"parse/fetch failures: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
