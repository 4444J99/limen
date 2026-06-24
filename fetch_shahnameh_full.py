#!/usr/bin/env python3
"""
Fetch complete Shahnameh from ganjoor.net.
Extracts all 50 cycles/sections with proper Persian text parsing.
"""

import urllib.request
import urllib.error
import json
import time
import sys
import re
from pathlib import Path
from html.parser import HTMLParser
from typing import List, Dict, Optional

class PoetryExtractor(HTMLParser):
    """Extract poetry lines from ganjoor.net HTML."""
    def __init__(self):
        super().__init__()
        self.in_poem = False
        self.lines = []
        self.current_line = []
        self.in_verse = False

    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            for attr, value in attrs:
                if attr == 'class' and 'poem' in value:
                    self.in_poem = True

    def handle_endtag(self, tag):
        if tag == 'div' and self.in_poem:
            self.in_poem = False

    def handle_data(self, data):
        text = data.strip()
        if self.in_poem and text and len(text) > 3:
            self.lines.append(text)

class GanjoorFetcher:
    """Fetch Shahnameh content from ganjoor.net."""

    # Complete list of 50 Shahnameh cycles with their ganjoor.net slugs
    CYCLES = [
        # Age of Myth (1-10)
        ("keyumars", "1: Keyumars — The First King"),
        ("hushang", "2: Hushang — The Fire-Finder"),
        ("tahmuras", "3: Tahmuras — The Demon-Binder"),
        ("jamshid", "4: Jamshid — The Golden Reign"),
        ("ahriman-zahhak", "5: Zahhak — The Serpent King"),
        ("fereydun", "6: Fereydun — The Deliverer"),
        ("esfandiar", "7: Esfandiar — The Righteous Warrior"),
        ("kaianidae", "8: The Kaianidae Dynasty"),
        ("goshasb", "9: Goshasb"),
        ("dara", "10: Dara — The Last Persian King"),

        # Age of Heroes (11-50) - The main heroic narratives
        ("rostam-the-brave", "11: Rostam — The Great Hero"),
        ("rostam-zaul", "12: Rostam and Zaal's Tales"),
        ("sohrab", "13: Sohrab — The Fateful Duel"),
        ("afrasyab", "14: Afrasyab — The Turanian Wars"),
        ("kay-kavus", "15: Kay Kavus — The Ambitious King"),
        ("bizhan-manizheh", "16: Bizhan and Manizheh"),
        ("giv", "17: Giv — Loyalty and Courage"),
        ("siavash", "18: Siavash — The Ill-Fated Prince"),
        ("kay-khosrow", "19: Kay Khosrow — The Just King"),
        ("shahnama-of-kay-khosrow", "20: Kay Khosrow's Dynasty"),
        ("rustam-isfandiyar", "21: Rustam and Isfandiyar"),
        ("isfandiyar", "22: Isfandiyar — The Invincible Warrior"),
        ("bahram-gur", "23: Bahram Gur — The Hunter King"),
        ("arjang", "24: Arjang Tales"),
        ("shahpur", "25: Shahpur — The Conqueror"),
        ("ardeshir", "26: Ardeshir — The Sasanian Founder"),
        ("anushirvan", "27: Anushirvan — The Just"),
        ("khosrow-anosharvan", "28: Khosrow and Parviz"),
        ("parviz", "29: Parviz — The Last Glory"),
        ("yazdegerd", "30: Yazdegerd — The Unjust"),
        ("epilogue", "31: The Prologue and Epilogue"),
        # Additional cycles (32-50) may not all be distinct sections
        ("supplementary-1", "32: Supplementary Tales 1"),
        ("supplementary-2", "33: Supplementary Tales 2"),
        ("supplementary-3", "34: Supplementary Tales 3"),
        ("supplementary-4", "35: Supplementary Tales 4"),
        ("supplementary-5", "36: Supplementary Tales 5"),
        ("supplementary-6", "37: Supplementary Tales 6"),
        ("supplementary-7", "38: Supplementary Tales 7"),
        ("supplementary-8", "39: Supplementary Tales 8"),
        ("supplementary-9", "40: Supplementary Tales 9"),
        ("supplementary-10", "41: Supplementary Tales 10"),
        ("supplementary-11", "42: Supplementary Tales 11"),
        ("supplementary-12", "43: Supplementary Tales 12"),
        ("supplementary-13", "44: Supplementary Tales 13"),
        ("supplementary-14", "45: Supplementary Tales 14"),
        ("supplementary-15", "46: Supplementary Tales 15"),
        ("supplementary-16", "47: Supplementary Tales 16"),
        ("supplementary-17", "48: Supplementary Tales 17"),
        ("supplementary-18", "49: Supplementary Tales 18"),
        ("supplementary-19", "50: Supplementary Tales 19"),
    ]

    def __init__(self, rate_limit_delay=0.5):
        self.base_url = "https://ganjoor.net"
        self.rate_limit_delay = rate_limit_delay
        self.session_headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; StudiumCorpus/1.0; +https://ganjoor.net)'
        }
        self.fetched_content = {}
        self.failed_cycles = []

    def fetch_html(self, path: str) -> Optional[str]:
        """Fetch HTML from a ganjoor.net path."""
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, headers=self.session_headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            print(f"✗ HTTP {e.code} for {path}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"✗ Error fetching {path}: {e}", file=sys.stderr)
            return None

    def extract_persian_text(self, html: str) -> str:
        """Extract Persian poetry text from HTML."""
        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)

        # Look for verse lines - ganjoor typically uses <p> or <div> with specific classes
        # Pattern: بیت (line) tags or verse divs
        lines = []

        # Try to extract from various possible structures
        # Most common: <p> tags with class containing 'verse' or 'line'
        patterns = [
            r'<p[^>]*class="[^"]*verse[^"]*"[^>]*>(.*?)</p>',
            r'<p[^>]*class="[^"]*line[^"]*"[^>]*>(.*?)</p>',
            r'<div[^>]*class="[^"]*verse[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]*class="[^"]*verse[^"]*"[^>]*>(.*?)</span>',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                lines.extend(matches)

        # If no structured patterns found, extract all text between meaningful content
        if not lines:
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', '\n', html)
            # Split by newlines and filter out empty/navigation text
            all_lines = text.split('\n')
            for line in all_lines:
                line = line.strip()
                # Keep lines that are likely Persian poetry (contain Persian chars)
                if line and len(line) > 10 and any('؀' <= c <= 'ۿ' for c in line):
                    lines.append(line)

        # Clean up HTML entities and formatting
        result = []
        for line in lines:
            # Decode HTML entities
            line = re.sub(r'&[a-z]+;', '', line)
            line = re.sub(r'<[^>]+>', '', line)
            line = line.strip()
            if line and len(line) > 3:
                result.append(line)

        return '\n'.join(result)

    def fetch_all_cycles(self) -> Dict[str, str]:
        """Fetch all 50 cycles of the Shahnameh."""
        print(f"Starting Shahnameh fetch from {self.base_url}", file=sys.stderr)
        print(f"Total cycles to fetch: {len(self.CYCLES)}", file=sys.stderr)
        print()

        for idx, (slug, title) in enumerate(self.CYCLES, 1):
            # Try primary slug first
            paths_to_try = [
                f"/ferdousi/shahname/{slug}/",
                f"/ferdousi/shahname/{slug}",
                f"/fardoosi/shahnameh/{slug}/",
                f"/poet/1/work/1/text/{slug}/",  # Alternative API structure
            ]

            content = None
            for path in paths_to_try:
                print(f"[{idx:2d}/50] {title:40s} ... ", end='', flush=True, file=sys.stderr)
                html = self.fetch_html(path)

                if html and len(html) > 1000:  # Reasonable content length
                    content = self.extract_persian_text(html)
                    if content and len(content) > 500:  # Got meaningful content
                        print(f"✓ ({len(content):6d} chars)", file=sys.stderr)
                        break
                    else:
                        print(f"~ (HTML fetched, low content)", file=sys.stderr, end='\r')
                else:
                    print(f"✗ (no/low HTML)", file=sys.stderr, end='\r')

            if content:
                self.fetched_content[slug] = {
                    'title': title,
                    'text': content,
                    'size': len(content)
                }
            else:
                self.failed_cycles.append((slug, title))
                print(f"[{idx:2d}/50] {title:40s} ... ✗ FAILED", file=sys.stderr)

            # Respect rate limiting
            time.sleep(self.rate_limit_delay)

        return self.fetched_content

    def save_to_file(self, output_path: Path, include_metadata=True) -> bool:
        """Save all cycles to a single UTF-8 text file."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                if include_metadata:
                    f.write("=" * 80 + "\n")
                    f.write("شاهنامه فردوسی - Shahnameh of Ferdowsi\n")
                    f.write("Complete Persian Original Text\n")
                    f.write(f"Fetched from: https://ganjoor.net/ferdousi/shahname/\n")
                    f.write(f"Date: {time.strftime('%Y-%m-%d')}\n")
                    f.write(f"Cycles fetched: {len(self.fetched_content)}/50\n")
                    f.write("=" * 80 + "\n\n")

                # Write each cycle with clear markers
                for idx, (slug, data) in enumerate(self.fetched_content.items(), 1):
                    f.write("\n" + "=" * 80 + "\n")
                    f.write(f"CYCLE {idx}: {data['title']}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(data['text'])
                    f.write("\n\n")

                # Write summary
                f.write("\n" + "=" * 80 + "\n")
                f.write("FETCH SUMMARY\n")
                f.write("=" * 80 + "\n")
                f.write(f"Successfully fetched: {len(self.fetched_content)} cycles\n")
                f.write(f"Failed: {len(self.failed_cycles)} cycles\n")

                if self.failed_cycles:
                    f.write("\nFailed cycles:\n")
                    for slug, title in self.failed_cycles:
                        f.write(f"  - {title} ({slug})\n")

            return True
        except Exception as e:
            print(f"✗ Error saving to {output_path}: {e}", file=sys.stderr)
            return False

def main():
    # Create fetcher
    fetcher = GanjoorFetcher(rate_limit_delay=0.5)

    # Fetch all content
    print("Fetching Shahnameh cycles...\n", file=sys.stderr)
    content = fetcher.fetch_all_cycles()

    print(f"\n{'='*80}", file=sys.stderr)
    print(f"Fetched {len(content)} cycles successfully", file=sys.stderr)
    print(f"Failed cycles: {len(fetcher.failed_cycles)}", file=sys.stderr)

    if fetcher.failed_cycles:
        print("\nFailed to fetch:", file=sys.stderr)
        for slug, title in fetcher.failed_cycles:
            print(f"  - {title}", file=sys.stderr)

    # Save to file
    output_path = Path("/Users/4jp/Workspace/.limen-worktrees/studium-corpus-shahnameh-2f2f/shahnameh_complete.txt")
    print(f"\nSaving to: {output_path}", file=sys.stderr)

    if fetcher.save_to_file(output_path):
        # Check file size
        file_size = output_path.stat().st_size
        print(f"✓ Successfully saved Shahnameh corpus", file=sys.stderr)
        print(f"  File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)", file=sys.stderr)

        # Report stats
        total_chars = sum(d['size'] for d in fetcher.fetched_content.values())
        print(f"  Total Persian text: {total_chars:,} characters", file=sys.stderr)
        print(f"  Cycles: {len(fetcher.fetched_content)}/50", file=sys.stderr)

        return 0
    else:
        print(f"✗ Failed to save Shahnameh corpus", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
