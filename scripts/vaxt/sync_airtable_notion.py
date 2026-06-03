#!/usr/bin/env python3
"""
VÄXT Airtable → Notion sync script.

Reads stats from Airtable (or from airtable_stats.json) and updates
the Notion VÄXT Knowledge Base "Airtable Integration" page with live
table counts, direct links, and last-synced timestamp.

Usage:
  python3 scripts/vaxt/sync_airtable_notion.py
  python3 scripts/vaxt/sync_airtable_notion.py --dry-run
  python3 scripts/vaxt/sync_airtable_notion.py --from-file  # Use cached airtable_stats.json

Env vars (from scripts/vaxt/.env):
  VAXT_AIRTABLE_PAT        — Airtable Personal Access Token
  VAXT_AIRTABLE_BASE_ID    — Airtable Base ID
  VAXT_NOTION_TOKEN         — Notion Internal Integration Token
  VAXT_NOTION_KB_PAGE_ID    — Notion VAXT KB root page ID
  VAXT_OUTPUT_DIR            — Output directory for cached stats

Prerequisites:
  pip install requests  (or use urllib — this script uses urllib for zero deps)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent.parent

# Load .env
env_path = SCRIPT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

AIRTABLE_PAT = os.environ.get("VAXT_AIRTABLE_PAT", "")
BASE_ID = os.environ.get("VAXT_AIRTABLE_BASE_ID", "appgv7zVxZnT2q9BX")
NOTION_TOKEN = os.environ.get("VAXT_NOTION_TOKEN", "")
NOTION_KB_PAGE_ID = os.environ.get("VAXT_NOTION_KB_PAGE_ID", "318c2b5ee82f81bb95dcd842992c3a05")
OUTPUT_DIR = Path(os.environ.get("VAXT_OUTPUT_DIR", WORKSPACE / "data" / "datasets" / "heritage-grain"))

# Notion page IDs (hardcoded — these are stable)
NOTION_INTEGRATION_PAGE_ID = "318c2b5ee82f81b6b35de33425540650"

AIRTABLE_API = "https://api.airtable.com/v0"
NOTION_API = "https://api.notion.com/v1"


def airtable_get(url: str) -> dict:
    req = Request(url, headers={
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json",
    })
    time.sleep(0.25)
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def notion_patch(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = Request(url, data=data, method="PATCH", headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    })
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def fetch_airtable_stats() -> dict:
    """Fetch live stats from Airtable API."""
    print("  Fetching Airtable metadata...")
    tables_data = airtable_get(f"{AIRTABLE_API}/meta/bases/{BASE_ID}/tables")
    tables = tables_data.get("tables", [])

    stats = {
        "base_id": BASE_ID,
        "base_url": f"https://airtable.com/{BASE_ID}",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tables": {},
    }

    for t in tables:
        # Minimal fetch to count records
        records = []
        url = f"{AIRTABLE_API}/{BASE_ID}/{t['id']}?fields[]=__placeholder__"
        while url:
            data = airtable_get(url)
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if offset:
                base_url = url.split("&offset=")[0]
                url = f"{base_url}&offset={offset}"
            else:
                url = None

        stats["tables"][t["name"]] = {
            "id": t["id"],
            "url": f"https://airtable.com/{BASE_ID}/{t['id']}",
            "fields": len(t.get("fields", [])),
            "records": len(records),
        }
        print(f"    {t['name']}: {len(records)} records")

    stats["total_records"] = sum(t["records"] for t in stats["tables"].values())
    stats["total_tables"] = len(stats["tables"])
    return stats


def load_cached_stats() -> dict:
    """Load stats from cached airtable_stats.json."""
    path = OUTPUT_DIR / "airtable_stats.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run export_airtable_varieties.py first or omit --from-file.", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def build_notion_content(stats: dict) -> str:
    """Build the updated Notion page content in enhanced markdown."""
    base_url = stats["base_url"]
    synced_at = stats["exported_at"]
    total_records = stats["total_records"]
    total_tables = stats["total_tables"]

    # Build table rows
    table_rows = ""
    for name, info in sorted(stats["tables"].items()):
        table_rows += f"""<tr>
<td>[{name}]({info['url']})</td>
<td>{info['records']}</td>
<td>{info['fields']}</td>
</tr>\n"""

    content = f"""::: callout {{icon="🔗" color="blue"}}
\t**Live Integration** · Last synced: {synced_at} · {total_tables} tables · {total_records} total records
:::
**Purpose:** How the VÄXT Notion KB complements the VÄXT Airtable base — and how they stay linked.
---
## Division of Labor
<table header-row="true">
<tr>
<td>System</td>
<td>Holds</td>
<td>Purpose</td>
<td>URL</td>
</tr>
<tr>
<td>**Airtable**</td>
<td>Varieties, Programs, Markers, Sites, Starters, GRIN, Wild Relatives, Disease Resistance, Climate Zones, Rootstock</td>
<td>Structured data: curated records for website export and breeding research</td>
<td>[Open Base]({base_url})</td>
</tr>
<tr>
<td>**Notion**</td>
<td>Vision, methodology, field guides, breeder notes, strategy memos</td>
<td>Narrative content: long-form docs, collaboration, strategy</td>
<td><mention-page url="https://www.notion.so/{NOTION_KB_PAGE_ID}">VÄXT Knowledge Base</mention-page></td>
</tr>
<tr>
<td>**DuckDB**</td>
<td>ETL outputs (FAOSTAT, T3, GBIF, Eurostat, GHCN, SoilGrids, photoperiod)</td>
<td>Heavy analytics: bulk data too large for Airtable</td>
<td>`data/datasets/heritage-grain/heritage-grain.duckdb`</td>
</tr>
</table>
**Rule:** Each piece of data lives in exactly one system. No duplication.
- Curated, human-editable data → **Airtable**
- Narrative, long-form content → **Notion**
- Bulk ETL & analytics → **DuckDB**
---
## Airtable Tables (Live)
<table fit-page-width="true" header-row="true">
<tr>
<td>Table</td>
<td>Records</td>
<td>Fields</td>
</tr>
{table_rows}</table>
**Base URL:** [{base_url}]({base_url})
---
## Quick Links by Topic
<table header-row="true">
<tr>
<td>Notion Page</td>
<td>Airtable Table(s)</td>
<td>Why</td>
</tr>
<tr>
<td><mention-page url="https://www.notion.so/318c2b5ee82f818eb883d6906aea9750">Field Guides</mention-page></td>
<td>Cold Tolerance Markers, Disease Resistance</td>
<td>Guides reference specific markers and resistance data</td>
</tr>
<tr>
<td><mention-page url="https://www.notion.so/318c2b5ee82f81b999e8f01fd09cebbb">Data Methodology</mention-page></td>
<td>All tables</td>
<td>Methodology describes how each table is curated</td>
</tr>
<tr>
<td><mention-page url="https://www.notion.so/318c2b5ee82f8179822bf604665dd9a1">Vision</mention-page></td>
<td>Breeding Programs, Field Trial Sites</td>
<td>Vision references the US–Nordic institutional network</td>
</tr>
<tr>
<td><mention-page url="https://www.notion.so/318c2b5ee82f8140a759e177015bb16f">Breeder Notes</mention-page></td>
<td>Varieties, Phenotype Records</td>
<td>Notes reference specific varieties and trial data</td>
</tr>
</table>
---
## Data Flow
```mermaid
graph LR
    A["Airtable<br>(curated data)"] -->|export_airtable_varieties.py| B["varieties.json"]
    B --> C["VÄXT Website"]
    D["Notion<br>(narrative)"] -->|build-time| C
    E["DuckDB<br>(ETL bulk)"] -->|load_heritage_grain.py| F["Analytics"]
    A -->|sync_airtable_notion.py| G["Notion Stats<br>(this page)"]
```
---
## Sync Pipeline
<table header-row="true">
<tr>
<td>Script</td>
<td>Direction</td>
<td>What It Does</td>
<td>Command</td>
</tr>
<tr>
<td>`export_airtable_varieties.py`</td>
<td>Airtable → JSON</td>
<td>Exports featured varieties to `varieties.json` for website</td>
<td>`python3 scripts/vaxt/export_airtable_varieties.py`</td>
</tr>
<tr>
<td>`sync_airtable_notion.py`</td>
<td>Airtable → Notion</td>
<td>Updates this page with live table counts and links</td>
<td>`python3 scripts/vaxt/sync_airtable_notion.py`</td>
</tr>
<tr>
<td>`vaxt_runner.py`</td>
<td>APIs → DuckDB</td>
<td>Runs all ETL sources and loads into DuckDB</td>
<td>`python3 scripts/vaxt/vaxt_runner.py`</td>
</tr>
</table>
---
## Embedding Airtable in Notion
To embed a live Airtable view in any Notion page:
1. Open the Airtable view you want to embed
2. Click **Share view** → Copy the shared view link
3. In Notion, type `/embed` and paste the shared view URL
4. The Airtable view will render inline (read-only)
**Shared view URL for Varieties:** Create one from [this view](https://airtable.com/{BASE_ID}/tbliCpponMHAIbwru/viwKnNb6q6JdYO4t5)
---
## Airtable → Notion Link-Back Fields
To add Notion links inside Airtable records:
1. Add a **URL** field called `Notion Link` to any Airtable table
2. Paste the relevant Notion page URL (e.g., a breeder note or field guide)
3. This creates bidirectional navigation: Airtable → Notion and Notion → Airtable
---
## Related
- Airtable schema: `docs/AIRTABLE_DESIGN.md`
- Notion KB spec: `docs/NOTION-KB-SPEC.md`
- Export script: `scripts/vaxt/export_airtable_varieties.py`
- Sync script: `scripts/vaxt/sync_airtable_notion.py`
- Env template: `scripts/vaxt/.env.example`
<empty-block/>
*Last synced: {synced_at}*"""

    return content


def main():
    parser = argparse.ArgumentParser(description="Sync VAXT Airtable stats → Notion KB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without writing")
    parser.add_argument("--from-file", action="store_true", help="Use cached airtable_stats.json instead of live API")
    args = parser.parse_args()

    print("VAXT Airtable → Notion Sync")
    print(f"  Base: {BASE_ID}")
    print(f"  Notion KB: {NOTION_KB_PAGE_ID}")
    print()

    # Get stats
    if args.from_file:
        print("Loading cached stats...")
        stats = load_cached_stats()
        print(f"  From: {OUTPUT_DIR / 'airtable_stats.json'}")
        print(f"  Cached at: {stats['exported_at']}")
    else:
        if not AIRTABLE_PAT:
            print("ERROR: VAXT_AIRTABLE_PAT not set. See scripts/vaxt/.env.example", file=sys.stderr)
            sys.exit(1)
        print("Fetching live Airtable stats...")
        stats = fetch_airtable_stats()
        # Cache the stats
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = OUTPUT_DIR / "airtable_stats.json"
        cache_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        print(f"  Cached to: {cache_path}")

    print(f"\n  {stats['total_tables']} tables, {stats['total_records']} total records")
    print()

    # Build Notion content
    content = build_notion_content(stats)

    if args.dry_run:
        print("[DRY RUN] Would update Notion page:")
        print(f"  Page: Airtable Integration ({NOTION_INTEGRATION_PAGE_ID})")
        print(f"  Content length: {len(content)} chars")
        print()
        preview = content[:500]
        print("  Preview:")
        for line in preview.splitlines():
            print(f"    {line}")
        print("    ...")
        return

    if not NOTION_TOKEN:
        print("NOTE: VAXT_NOTION_TOKEN not set. Skipping Notion API update.")
        print("  The content has been generated. To update Notion manually:")
        print(f"  1. Open https://www.notion.so/{NOTION_INTEGRATION_PAGE_ID}")
        print("  2. Replace the page content with the generated markdown")
        print()
        # Save content to file for manual use
        content_path = OUTPUT_DIR / "notion_integration_content.md"
        content_path.write_text(content)
        print(f"  Content saved to: {content_path}")
        return

    # Update via Notion API
    print(f"Updating Notion page: Airtable Integration ({NOTION_INTEGRATION_PAGE_ID})...")
    # Note: Direct Notion API update would go here.
    # For now, save content for MCP-based update (which is what we use in Claude Code).
    content_path = OUTPUT_DIR / "notion_integration_content.md"
    content_path.write_text(content)
    print(f"  Content saved to: {content_path}")
    print("  Use Claude Code MCP to push this to Notion (notion-update-page).")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
