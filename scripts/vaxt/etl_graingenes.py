#!/usr/bin/env python3
"""ETL: Scrape cold/frost tolerance QTLs from GrainGenes browse/report CGI.

Outputs CSV to data/datasets/heritage-grain/graingenes_qtl.csv.

Usage:
    python3 scripts/vaxt/etl_graingenes.py [--dry-run] [--delay 1.0]

GrainGenes has no REST API.  Data is scraped from:
  - browse.cgi?class=qtl;query=<pattern>   (list pages)
  - report.cgi?class=qtl;name=<name>;id=<id>  (detail pages)

Rate-limited to 1 req/s by default (be polite to USDA servers).
"""

import argparse
import csv
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
OUTPUT_CSV = OUTPUT_DIR / "graingenes_qtl.csv"

BASE = "https://graingenes.org/cgi-bin/GG3"
USER_AGENT = "VAV-OS/1.0 (malcolm@vav-os.com) heritage-grain-ETL"

# QTL name prefixes related to cold/frost tolerance
QTL_QUERIES = [
    "QFt*",       # Frost tolerance
    "QFr*",       # Frost/freezing resistance
    "QWs*",       # Winter survival
    "QCft*",      # Crown freezing tolerance
    "QSm*",       # Snow mold resistance
    "QLt50*",     # LT50
]

CSV_COLUMNS = [
    "qtl_name",
    "synonym",
    "species",
    "chromosome",
    "trait",
    "ontology_term",
    "lod",
    "r_squared",
    "flanking_marker_1",
    "flanking_marker_2",
    "peak_marker",
    "positive_markers",
    "parents",
    "trait_study",
    "reference",
    "graingenes_id",
    "graingenes_url",
]


def fetch(url: str, delay: float = 1.0) -> str:
    """Fetch URL with rate limiting and user-agent."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as exc:
        print(f"  WARN: {url} -> {exc}", file=sys.stderr)
        return ""
    time.sleep(delay)
    return html


# ---------------------------------------------------------------------------
# HTML parsers (stdlib only — no BeautifulSoup dependency)
# ---------------------------------------------------------------------------

class BrowseParser(HTMLParser):
    """Parse browse.cgi output to extract QTL names and IDs."""

    def __init__(self):
        super().__init__()
        self.qtls: list[dict] = []  # [{name, id, url}]
        self._in_link = False
        self._current: dict = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if "report.cgi" in href and "class=qtl" in href:
            m_name = re.search(r"name=([^;]+)", href)
            m_id = re.search(r"id=(\d+)", href)
            if m_name:
                self._current = {
                    "name": m_name.group(1),
                    "id": m_id.group(1) if m_id else "",
                    "url": href if href.startswith("http") else f"https://graingenes.org{href}",
                }
                self._in_link = True

    def handle_endtag(self, tag: str):
        if tag == "a" and self._in_link:
            self._in_link = False
            if self._current:
                self.qtls.append(self._current)
                self._current = {}

    def handle_data(self, data: str):
        pass


def parse_report_html(html: str) -> dict[str, str]:
    """Parse report.cgi HTML using regex.

    GrainGenes uses nested tables with this pattern:
      <tr class="FieldName"><td><table><tr><td><b>FieldName</b></td></tr></table>
      <td><table><tr><td ... value="VAL">...</td>
    """
    fields: dict[str, str] = {}

    # Pattern 1: <tr class="LABEL"> ... <td type="LABEL" value="VALUE">
    for m in re.finditer(
        r'<tr\s+class="([^"]+)"[^>]*>.*?'
        r'<td\s+type="[^"]*"\s+value="([^"]*)"',
        html, re.DOTALL,
    ):
        label = m.group(1).strip()
        value = m.group(2).strip()
        if label and value:
            if label in fields:
                fields[label] += "; " + value
            else:
                fields[label] = value

    # Pattern 2: <tr class="Phenotypic R2"> ... value="30.9"
    # Already covered by pattern 1

    return fields


def browse_qtls(query: str, delay: float) -> list[dict]:
    """Fetch QTL list from browse.cgi for a query pattern."""
    url = f"{BASE}/browse.cgi?class=qtl;query={query};begin=1"
    html = fetch(url, delay)
    if not html:
        return []
    parser = BrowseParser()
    parser.feed(html)
    return parser.qtls


def fetch_qtl_report(qtl: dict, delay: float) -> dict:
    """Fetch and parse a single QTL report page."""
    url = qtl["url"]
    html = fetch(url, delay)
    if not html:
        return {}

    f = parse_report_html(html)

    # Map GrainGenes field names to our CSV columns
    def get(*keys: str) -> str:
        for k in keys:
            if k in f:
                return f[k]
        return ""

    return {
        "qtl_name": qtl["name"],
        "synonym": get("Synonym"),
        "species": get("Species"),
        "chromosome": get("Chromosome"),
        "trait": get("Trait Affected", "Trait"),
        "ontology_term": get("Ontology"),
        "lod": get("LOD"),
        "r_squared": get("Phenotypic R2"),
        "flanking_marker_1": get("Flanking Marker 1"),
        "flanking_marker_2": get("Flanking Marker 2"),
        "peak_marker": get("LOD Peak Location"),
        "positive_markers": get("Positive Significant Marker"),
        "parents": get("Parent"),
        "trait_study": get("Trait Study"),
        "reference": get("Reference"),
        "graingenes_id": qtl["id"],
        "graingenes_url": url,
    }


def main():
    parser = argparse.ArgumentParser(description="ETL: GrainGenes cold tolerance QTLs")
    parser.add_argument("--dry-run", action="store_true", help="List QTLs without fetching reports")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests (default: 1.0)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: Collect QTL names from browse pages
    all_qtls: dict[str, dict] = {}  # name -> {name, id, url}
    for query in QTL_QUERIES:
        print(f"Browsing: {query}")
        qtls = browse_qtls(query, args.delay)
        for q in qtls:
            if q["name"] not in all_qtls:
                all_qtls[q["name"]] = q
        print(f"  Found {len(qtls)} QTLs ({len(all_qtls)} total unique)")

    if not all_qtls:
        print("No QTLs found. Check network connectivity.")
        sys.exit(1)

    print(f"\nTotal unique QTLs: {len(all_qtls)}")

    if args.dry_run:
        for name in sorted(all_qtls):
            print(f"  {name}")
        print(f"\nDry run — {len(all_qtls)} QTLs would be fetched. Pass without --dry-run to fetch.")
        return

    # Phase 2: Fetch individual reports
    rows: list[dict] = []
    for i, (name, qtl) in enumerate(sorted(all_qtls.items()), 1):
        print(f"  [{i}/{len(all_qtls)}] {name}")
        record = fetch_qtl_report(qtl, args.delay)
        if record:
            rows.append(record)

    # Phase 3: Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} QTL records to {OUTPUT_CSV}")

    # Summary
    species = sorted(set(r["species"] for r in rows if r.get("species")))
    traits = sorted(set(r["trait"] for r in rows if r.get("trait")))
    chroms = sorted(set(r["chromosome"] for r in rows if r.get("chromosome")))
    print(f"Species: {', '.join(species[:10])}")
    print(f"Traits: {', '.join(traits[:10])}")
    print(f"Chromosomes: {', '.join(chroms[:10])}")


if __name__ == "__main__":
    main()
