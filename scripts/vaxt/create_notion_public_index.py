#!/usr/bin/env python3
"""
Create VÄXT Public Index page in Notion.

The public index page links all external-facing content:
  - Growing guides (wheat, rye, fruit, processing, community)
  - Heritage grain recipes
  - Bread baking guide
  - Distilling guide
  - How to Use VÄXT
  - Variety profiles (created by create_notion_variety_profiles.py)
  - Seed Source Directory (Airtable shared view)

Usage:
    python3 scripts/vaxt/create_notion_public_index.py [--dry-run]

Env:
    VAXT_NOTION_TOKEN         — Notion Internal Integration Token
"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"

# Load .env
if (SCRIPT_DIR / ".env").exists():
    for line in (SCRIPT_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

NOTION_TOKEN = os.environ.get("VAXT_NOTION_TOKEN", "")
DRY_RUN = "--dry-run" in sys.argv

# Notion page IDs
KB_ROOT_PAGE_ID = "318c2b5ee82f81bb95dcd842992c3a05"
NOTION_API = "https://api.notion.com/v1"

# Page classification
PUBLIC_PAGES = [
    {"title": "How to Use VÄXT", "id": "318c2b5ee82f81e494a2eaea93ac91c2",
     "desc": "Quick-start guide to navigating the VÄXT knowledge base"},
    {"title": "Growing Heritage Wheat", "id": "318c2b5ee82f8126954ed83442249146",
     "desc": "Full lifecycle guide — from sowing to sourdough"},
    {"title": "Growing Heritage Rye", "id": "318c2b5ee82f817fb3aae46a1a180861",
     "desc": "Gateway grain for beginners — cold hardy, forgiving, flavorful"},
    {"title": "Small-Scale Grain Processing", "id": "318c2b5ee82f81f1ba8bc2910ec780d0",
     "desc": "Drying, threshing, winnowing, milling, malting, seed saving"},
    {"title": "Cold-Hardy Fruit & Berry Guide", "id": "318c2b5ee82f81268505d9fa9bc76ce2",
     "desc": "Apples, grapes, haskap, sea buckthorn, currants, arctic berries"},
    {"title": "Community Grain Projects", "id": "318c2b5ee82f8177bd35fa37cd614fe5",
     "desc": "Models, economics, seed commons, starting a local grain economy"},
    {"title": "Heritage Grain Recipes", "id": "318c2b5ee82f81e087c2c40115ea931a",
     "desc": "16 recipes by grain type with sourdough starter pairings"},
    {"title": "Heritage Grain Bread Baking Guide", "id": "318c2b5ee82f81d4b2cdde767b849a2c",
     "desc": "Milling, sourdough, Nordic bread traditions, heritage flour types"},
    {"title": "Heritage Grain Whiskey & Distilling Guide", "id": "318c2b5ee82f818a938adcc24e8f178a",
     "desc": "Malting, distillery profiles, grain-to-glass terroir"},
]

INTERNAL_PAGES = [
    {"title": "Vision", "id": "318c2b5ee82f8179822bf604665dd9a1",
     "reason": "Review before publishing — contains strategy details"},
    {"title": "Data Methodology", "id": "318c2b5ee82f81b999e8f01fd09cebbb",
     "reason": "Internal reference for data curation process"},
    {"title": "Airtable Integration", "id": "318c2b5ee82f81b6b35de33425540650",
     "reason": "Technical sync details — not public-facing"},
    {"title": "Breeder Notes", "id": "318c2b5ee82f8140a759e177015bb16f",
     "reason": "Internal meeting notes and research memos"},
    {"title": "KB Spec", "id": "318c2b5ee82f819b8f10ce991e303c55",
     "reason": "Technical specification — not public-facing"},
]

# Airtable shared view for Seed Source Directory
AIRTABLE_VARIETIES_VIEW = "https://airtable.com/appgv7zVxZnT2q9BX/tbliCpponMHAIbwru/viwKnNb6q6JdYO4t5"


def notion_request(url: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    })
    time.sleep(0.35)
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def build_public_index_blocks() -> list[dict]:
    """Build Notion block children for the public index page."""
    blocks = []

    def heading(level: int, text: str):
        types = {1: "heading_1", 2: "heading_2", 3: "heading_3"}
        blocks.append({
            "object": "block", "type": types[level],
            types[level]: {
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        })

    def paragraph(text: str):
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        })

    def mention_page(page_id: str, text: str, desc: str):
        blocks.append({
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "mention", "mention": {"page": {"id": page_id}}},
                    {"type": "text", "text": {"content": f" — {desc}"}},
                ],
            },
        })

    def divider():
        blocks.append({"object": "block", "type": "divider", "divider": {}})

    def callout(text: str, icon: str = "🌾"):
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": icon},
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        })

    # Introduction
    callout(
        "VÄXT is a heritage grain knowledge base. "
        "This page links all public-facing guides, recipes, and resources."
    )
    paragraph("")

    # Growing Guides
    heading(2, "Growing Guides")
    paragraph("Comprehensive guides for growing heritage grains, fruit, and berries in cold climates.")
    for page in PUBLIC_PAGES[:6]:  # Growing guides
        mention_page(page["id"], page["title"], page["desc"])
    divider()

    # Recipes & Processing
    heading(2, "Recipes & Processing")
    paragraph("From grain to table: recipes, baking guides, and distilling profiles.")
    for page in PUBLIC_PAGES[6:]:  # Recipes, baking, distilling
        mention_page(page["id"], page["title"], page["desc"])
    divider()

    # Variety Directory
    heading(2, "Variety Directory")
    paragraph(
        "Browse all 194+ heritage grain varieties in the VÄXT database. "
        "Each variety includes cold tolerance data, growing zones, traits, and seed sources."
    )
    blocks.append({
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": "Browse Varieties on Airtable",
                    "link": {"url": AIRTABLE_VARIETIES_VIEW},
                },
            }],
        },
    })
    blocks.append({
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": "Featured variety profiles are listed below under Field Guides"}}],
        },
    })
    divider()

    # Data Downloads
    heading(2, "Data Downloads")
    paragraph(
        "VÄXT data is available for download as CSV files under CC BY 4.0 license. "
        "See the VÄXT website Data page for download links."
    )
    divider()

    # About
    heading(2, "About VÄXT")
    paragraph(
        "VÄXT uses waste heat from genomic computing to accelerate heritage grain breeding "
        "under open-source commons licenses. The knowledge base covers varieties, climate data, "
        "breeding programs, sourdough cultures, and seed sources across Nordic and North American cold climates."
    )
    paragraph("Contact: malcolm@vav-os.com")

    return blocks


def main():
    print("VAXT Public Index Page Generator")
    if DRY_RUN:
        print("[DRY RUN MODE]\n")

    # Generate blocks
    blocks = build_public_index_blocks()
    print(f"Generated {len(blocks)} blocks for public index page\n")

    # Page classification summary
    print("Page Classification:")
    print(f"\n  PUBLIC ({len(PUBLIC_PAGES)} pages):")
    for p in PUBLIC_PAGES:
        print(f"    {p['title']}")

    print(f"\n  INTERNAL ({len(INTERNAL_PAGES)} pages):")
    for p in INTERNAL_PAGES:
        print(f"    {p['title']} — {p['reason']}")

    if DRY_RUN:
        print("\n[DRY RUN] Would create 'VÄXT Public Index' page under KB root")
        return

    if not NOTION_TOKEN:
        # Save as JSON for manual creation or MCP-based push
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / "notion_public_index.json"
        path.write_text(json.dumps({
            "title": "VÄXT Public Index",
            "parent_id": KB_ROOT_PAGE_ID,
            "blocks": blocks,
        }, indent=2))
        print(f"\nSaved to {path}")
        print("Use Claude Code Notion MCP to create this page.")
        return

    # Create via API
    print("\nCreating 'VÄXT Public Index' page...")
    body = {
        "parent": {"page_id": KB_ROOT_PAGE_ID},
        "icon": {"type": "emoji", "emoji": "🌾"},
        "properties": {
            "title": [{"text": {"content": "VÄXT Public Index"}}],
        },
        "children": blocks[:100],
    }
    result = notion_request(f"{NOTION_API}/pages", method="POST", body=body)
    print(f"  Created: {result.get('url', 'unknown')}")
    print("\nDone.")


if __name__ == "__main__":
    main()
