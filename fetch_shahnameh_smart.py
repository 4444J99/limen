#!/usr/bin/env python3
"""
Fetch complete Shahnameh from ganjoor.net by discovering actual URLs.
Since the exact slug structure is unclear, we discover URLs from the main page.
"""

import urllib.request
import urllib.error
import json
import time
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

class GanjoorFetcher:
    """Fetch Shahnameh content from ganjoor.net."""

    def __init__(self, rate_limit_delay=0.5):
        self.base_url = "https://ganjoor.net"
        self.rate_limit_delay = rate_limit_delay
        self.session_headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; StudiumCorpus/1.0; +https://ganjoor.net)'
        }
        self.fetched_content = {}
        self.failed_cycles = []
        self.discovered_urls = {}

    def fetch_html(self, path: str) -> Optional[str]:
        """Fetch HTML from a ganjoor.net path."""
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, headers=self.session_headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            return None
        except Exception as e:
            return None

    def discover_shahnameh_urls(self) -> Dict[str, str]:
        """Discover all Shahnameh cycle URLs from the main page."""
        print("Discovering Shahnameh URLs from ganjoor.net...", file=sys.stderr)

        html = self.fetch_html("/ferdousi/shahname/")
        if not html:
            print("✗ Failed to fetch main Shahnameh page", file=sys.stderr)
            return {}

        # Look for links to individual cycles
        # Pattern: href="/ferdousi/shahname/something"
        pattern = r'href="(/ferdousi/shahname/[^"]+)"'
        matches = re.findall(pattern, html)

        # Filter for unique paths and remove trailing slashes
        urls = {}
        for path in set(matches):
            path = path.rstrip('/')
            # Skip the main page and admin paths
            if path == '/ferdousi/shahname' or 'admin' in path.lower():
                continue

            # Extract the slug (last part of path)
            slug = path.split('/')[-1]
            urls[slug] = path

        print(f"✓ Discovered {len(urls)} potential cycles", file=sys.stderr)
        return urls

    def extract_persian_text(self, html: str) -> str:
        """Extract Persian poetry text from HTML."""
        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)

        # Remove common HTML navigation and UI elements
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL)
        html = re.sub(r'<form[^>]*>.*?</form>', '', html, flags=re.DOTALL)

        lines = []

        # Try to extract from verse containers
        # ganjoor.net typically uses semantic HTML for poetry
        patterns = [
            r'<p[^>]*>((?:[^\n]|[\n])*?)</p>',  # Paragraph tags
            r'<span[^>]*class="[^"]*verse[^"]*"[^>]*>(.*?)</span>',
            r'<div[^>]*class="[^"]*verse[^"]*"[^>]*>(.*?)</div>',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html)
            lines.extend(matches)

        # Clean up HTML entities and tags
        result = []
        for line in lines:
            # Remove HTML tags
            line = re.sub(r'<[^>]+>', '', line)
            # Decode common HTML entities
            line = line.replace('&nbsp;', ' ')
            line = line.replace('&lt;', '<')
            line = line.replace('&gt;', '>')
            line = line.replace('&amp;', '&')
            line = line.replace('&quot;', '"')
            line = line.strip()

            # Keep lines that are likely Persian poetry (contain Persian chars)
            # Persian Unicode range: U+0600 to U+06FF
            if line and len(line) > 5 and any('؀' <= c <= 'ۿ' for c in line):
                result.append(line)

        return '\n'.join(result)

    def fetch_all_cycles(self) -> Dict[str, str]:
        """Fetch all cycles of the Shahnameh."""
        # First discover URLs
        discovered = self.discover_shahnameh_urls()
        if not discovered:
            print("✗ No URLs discovered", file=sys.stderr)
            return {}

        print(f"\nFetching {len(discovered)} cycles...\n", file=sys.stderr)

        for idx, (slug, path) in enumerate(sorted(discovered.items()), 1):
            print(f"[{idx:2d}/{len(discovered)}] {slug:30s} ... ", end='', flush=True, file=sys.stderr)

            html = self.fetch_html(path)
            if html and len(html) > 1000:
                content = self.extract_persian_text(html)
                if content and len(content) > 500:
                    print(f"✓ ({len(content):6d} chars)", file=sys.stderr)
                    self.fetched_content[slug] = {
                        'title': slug.replace('-', ' ').title(),
                        'text': content,
                        'size': len(content),
                        'url': path
                    }
                else:
                    print("✗ (low content)", file=sys.stderr)
                    self.failed_cycles.append((slug, path))
            else:
                print("✗ (fetch failed)", file=sys.stderr)
                self.failed_cycles.append((slug, path))

            time.sleep(self.rate_limit_delay)

        return self.fetched_content

    def save_to_file(self, output_path: Path) -> bool:
        """Save all cycles to a UTF-8 text file."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("شاهنامه فردوسی\n")
                f.write("Shahnameh of Ferdowsi - Complete Persian Original Text\n")
                f.write(f"Source: https://ganjoor.net/ferdousi/shahname/\n")
                f.write(f"Fetched: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Cycles: {len(self.fetched_content)} fetched\n")
                f.write("=" * 80 + "\n\n")

                # Write each cycle
                for idx, (slug, data) in enumerate(sorted(self.fetched_content.items()), 1):
                    f.write("\n" + "=" * 80 + "\n")
                    f.write(f"CYCLE: {data['title'].upper()}\n")
                    f.write(f"URL: {self.base_url}{data['url']}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(data['text'])
                    f.write("\n\n")

            return True
        except Exception as e:
            print(f"✗ Error saving to {output_path}: {e}", file=sys.stderr)
            return False

def main():
    fetcher = GanjoorFetcher(rate_limit_delay=0.5)

    # Fetch all cycles
    content = fetcher.fetch_all_cycles()

    print(f"\n{'='*80}", file=sys.stderr)
    print(f"Fetched {len(content)} cycles successfully", file=sys.stderr)
    print(f"Failed: {len(fetcher.failed_cycles)} cycles", file=sys.stderr)

    if not content:
        print("✗ No content fetched", file=sys.stderr)
        return 1

    # Save to file
    output_path = Path("/Users/4jp/Workspace/.limen-worktrees/studium-corpus-shahnameh-2f2f/shahnameh_discovered.txt")
    print(f"\nSaving to: {output_path}", file=sys.stderr)

    if fetcher.save_to_file(output_path):
        file_size = output_path.stat().st_size
        print(f"✓ Successfully saved Shahnameh corpus", file=sys.stderr)
        print(f"  File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)", file=sys.stderr)

        total_chars = sum(d['size'] for d in fetcher.fetched_content.values())
        print(f"  Total text: {total_chars:,} characters", file=sys.stderr)

        # List all discovered cycles
        print(f"\n  Cycles fetched:", file=sys.stderr)
        for idx, slug in enumerate(sorted(fetcher.fetched_content.keys()), 1):
            print(f"    {idx:2d}. {slug}", file=sys.stderr)

        return 0
    else:
        print(f"✗ Failed to save", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
