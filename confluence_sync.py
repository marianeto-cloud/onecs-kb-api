#!/usr/bin/env python3
"""
Confluence Sync Script for OneCs KB API
========================================
Connects to Confluence Cloud (nasperclassifieds.atlassian.net), downloads all
pages from the "OCP" space, classifies them by product (OLX / Standvirtual /
Imovirtual / Transversal), and saves them as markdown files in the
appropriate wiki_data/ subdirectory.

Usage:
    python3 data/onecs-kb-api/confluence_sync.py

Credentials are handled by the transparent Toqan proxy — no tokens needed.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
BASE_URL = "https://nasperclassifieds.atlassian.net"
SPACE_KEY = "OCP"
OUT_DIR = Path(__file__).parent / "wiki_data"
SYNC_LOG_PATH = Path(__file__).parent / "last_sync.json"
API_DELAY = 0.5  # seconds between API calls (rate limiting)

# Product subdirectories
PRODUCT_SUBDIRS = {
    "olx": "olx",
    "standvirtual": "standvirtual",
    "imovirtual": "imovirtual",
    "transversal": "transversal",
}

# ----------------------------------------------------------------------
# Helpers: slugify
# ----------------------------------------------------------------------
def slugify(text: str) -> str:
    """
    Convert a string to a safe filename slug.
    - Lowercase
    - Replace spaces and punctuation with hyphens
    - Remove diacritics (c -> c, a -> a, etc.)
    - Collapse multiple hyphens into one
    - Strip leading/trailing hyphens
    """
    # Normalize unicode: decompose combined characters, then strip diacritics
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase and replace non-alphanumeric runs with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_str.lower())
    return slug.strip("-")


# ----------------------------------------------------------------------
# Helpers: API calls
# ----------------------------------------------------------------------
def api_get(path: str, params: Optional[dict] = None) -> requests.Response:
    """
    Perform a GET request against the Confluence API, with a brief pause
    for rate limiting. Raises on HTTP errors (caller handles 401/403/407).
    """
    url = f"{BASE_URL}{path}"
    time.sleep(API_DELAY)
    resp = requests.get(url, params=params, timeout=30)
    return resp


def check_auth_error(resp: requests.Response) -> None:
    """Raise an exception with a clear message for auth failures."""
    if resp.status_code in (401, 403, 407):
        print(
            "ERROR: Confluence credentials not configured. "
            "Go to Settings > Integrations and add credentials for "
            "nasperclassifieds.atlassian.net"
        )
        sys.exit(1)


# ----------------------------------------------------------------------
# Helpers: Confluence API v2
# ----------------------------------------------------------------------
def fetch_space_v2() -> dict:
    """Find and return the OCP space object using API v2."""
    print("  [v2] Fetching spaces list...")
    resp = api_get("/wiki/api/v2/spaces", params={"limit": 100})
    check_auth_error(resp)

    if resp.status_code != 200:
        raise RuntimeError(f"Unexpected status {resp.status_code} listing spaces")

    data = resp.json()
    spaces = data.get("results", [])

    # Find the OCP space by key (case-insensitive)
    ocp_space = None
    for space in spaces:
        if space.get("key", "").upper() == SPACE_KEY:
            ocp_space = space
            break

    if ocp_space is None:
        # Build a helpful error with available spaces
        available = [f"{s.get('key')} ({s.get('name', '?')})" for s in spaces]
        raise RuntimeError(
            f"Space '{SPACE_KEY}' not found. Available spaces: {available}"
        )

    print(f"  [v2] Found space: {ocp_space['key']} - {ocp_space.get('name', '?')}")
    return ocp_space


def fetch_pages_v2(space_id: int) -> list[dict]:
    """Fetch all pages in a space using API v2 with cursor pagination."""
    print("  [v2] Fetching pages in space...")
    pages = []
    cursor = None
    page_num = 0

    while True:
        page_num += 1
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor

        resp = api_get(f"/wiki/api/v2/spaces/{space_id}/pages", params=params)
        check_auth_error(resp)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Unexpected status {resp.status_code} listing pages"
            )

        data = resp.json()
        batch = data.get("results", [])
        pages.extend(batch)

        # Progress indicator
        print(f"    Fetched page batch {page_num} ({len(batch)} items, "
              f"total so far: {len(pages)})")

        # Cursor-based pagination
        links = data.get("_links", {})
        next_cursor = links.get("next")
        if not next_cursor:
            break
        # Extract cursor from URL (e.g. "?cursor=abc...")
        from urllib.parse import parse_qs, urlparse
        parsed = parse_qs(urlparse(next_cursor).query)
        cursor = parsed.get("cursor", [None])[0]
        if not cursor:
            break

    return pages


def fetch_page_content_v2(page_id: int) -> str:
    """Fetch a single page's markdown body using API v2."""
    resp = api_get(
        f"/wiki/api/v2/pages/{page_id}",
        params={"body-format": "markdown"}
    )
    check_auth_error(resp)

    if resp.status_code == 404:
        raise RuntimeError(f"Page {page_id} not found")
    if resp.status_code != 200:
        raise RuntimeError(
            f"Unexpected status {resp.status_code} fetching page {page_id}"
        )

    data = resp.json()
    body = data.get("body", {})
    return body.get("markdown", {}).get("value", "")


# ----------------------------------------------------------------------
# Helpers: Confluence API v1 (fallback)
# ----------------------------------------------------------------------
def fetch_space_v1() -> dict:
    """Find and return the OCP space object using API v1."""
    print("  [v1] Fetching spaces list...")
    resp = api_get("/wiki/rest/api/space", params={"limit": 100})
    check_auth_error(resp)

    if resp.status_code != 200:
        raise RuntimeError(f"Unexpected status {resp.status_code} listing spaces")

    data = resp.json()
    spaces = data.get("results", [])

    ocp_space = None
    for space in spaces:
        if space.get("key", "").upper() == SPACE_KEY:
            ocp_space = space
            break

    if ocp_space is None:
        available = [f"{s.get('key')} ({s.get('name', '?')})" for s in spaces]
        raise RuntimeError(
            f"Space '{SPACE_KEY}' not found. Available spaces: {available}"
        )

    print(f"  [v1] Found space: {ocp_space['key']} - {ocp_space.get('name', '?')}")
    return ocp_space


def fetch_pages_v1(space_key: str) -> list[dict]:
    """Fetch all pages in a space using API v1 with start-offset pagination."""
    print("  [v1] Fetching pages in space...")
    pages = []
    start = 0
    page_num = 0

    while True:
        page_num += 1
        resp = api_get(
            f"/wiki/rest/api/space/{space_key}/content/page",
            params={"limit": 100, "start": start}
        )
        check_auth_error(resp)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Unexpected status {resp.status_code} listing pages"
            )

        data = resp.json()
        batch = data.get("results", [])
        pages.extend(batch)

        print(f"    Fetched page batch {page_num} ({len(batch)} items, "
              f"total so far: {len(pages)})")

        # Offset-based pagination
        size = data.get("size", 0)
        if size < 100:
            break
        start += 100

    return pages


def fetch_page_content_v1(page_id: int) -> str:
    """
    Fetch a single page's body using API v1.
    Returns HTML; a best-effort HTML-to-markdown conversion is applied.
    """
    resp = api_get(
        f"/wiki/rest/api/content/{page_id}",
        params={"expand": "body.storage"}
    )
    check_auth_error(resp)

    if resp.status_code == 404:
        raise RuntimeError(f"Page {page_id} not found")
    if resp.status_code != 200:
        raise RuntimeError(
            f"Unexpected status {resp.status_code} fetching page {page_id}"
        )

    data = resp.json()
    body = data.get("body", {})
    html = body.get("storage", {}).get("value", "")
    return html_to_markdown(html)


def html_to_markdown(html: str) -> str:
    """
    Best-effort HTML-to-Markdown conversion.
    Handles the most common Confluence storage format tags.
    """
    md = html

    # Paragraphs
    md = re.sub(r"<p[^>]*>", "", md)
    md = re.sub(r"</p>", "\n\n", md)

    # Headings: h1 to h6
    for i in range(1, 7):
        md = re.sub(
            rf"<h{i}([^>]*)>", rf"{'#' * i} ", md
        )
        md = re.sub(rf"</h{i}>", "\n", md)

    # Bold
    md = re.sub(r"<strong[^>]*>", "**", md)
    md = re.sub(r"</strong>", "**", md)
    md = re.sub(r"<b[^>]*>", "**", md)
    md = re.sub(r"</b>", "**", md)

    # Italic
    md = re.sub(r"<em[^>]*>", "_", md)
    md = re.sub(r"</em>", "_", md)
    md = re.sub(r"<i[^>]*>", "_", md)
    md = re.sub(r"</i>", "_", md)

    # Underline (Confluence uses ins)
    md = re.sub(r"<ins[^>]*>", "__", md)
    md = re.sub(r"</ins>", "__", md)

    # Strikethrough
    md = re.sub(r"<del[^>]*>", "~~", md)
    md = re.sub(r"</del>", "~~", md)

    # Inline code
    md = re.sub(r"<code[^>]*>", "`", md)
    md = re.sub(r"</code>", "`", md)

    # Code blocks
    md = re.sub(r"<pre[^>]*>", "```\n", md)
    md = re.sub(r"</pre>", "\n```\n", md)

    # Unordered lists
    md = re.sub(r"<ul[^>]*>", "", md)
    md = re.sub(r"</ul>", "\n", md)
    md = re.sub(r"<li[^>]*>", "- ", md)
    md = re.sub(r"</li>", "\n", md)

    # Ordered lists
    md = re.sub(r"<ol[^>]*>", "", md)
    md = re.sub(r"</ol>", "\n", md)

    # Links
    md = re.sub(
        r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>',
        r"[\2](\1)",
        md,
        flags=re.DOTALL
    )

    # Images (Confluence macro syntax)
    md = re.sub(
        r'<ac:image[^>]*>\s*<ri:url\s+ri:value="([^"]*)"[^>]*/>\s*</ac:image>',
        r"![](\1)",
        md,
        flags=re.DOTALL
    )
    md = re.sub(
        r'<img\s+src="([^"]*)"[^>]*/?>',
        r"![](\1)",
        md
    )

    # Tables (basic: one row per line, cells separated by |)
    md = re.sub(r"<table[^>]*>", "", md)
    md = re.sub(r"</table>", "\n", md)
    md = re.sub(r"<tbody[^>]*>", "", md)
    md = re.sub(r"</tbody>", "", md)
    md = re.sub(r"<thead[^>]*>", "", md)
    md = re.sub(r"</thead>", "", md)
    md = re.sub(r"<tr[^>]*>", "", md)
    md = re.sub(r"</tr>", "\n", md)
    md = re.sub(r"<th[^>]*>", "| ", md)
    md = re.sub(r"</th>", " ", md)
    md = re.sub(r"<td[^>]*>", "| ", md)
    md = re.sub(r"</td>", " ", md)

    # Blockquotes
    md = re.sub(r"<blockquote[^>]*>", "> ", md)
    md = re.sub(r"</blockquote>", "\n", md)

    # Horizontal rule
    md = re.sub(r"<hr[^>]*/?>", "\n---\n", md)

    # Line breaks
    md = re.sub(r"<br[^>]*/?>", "\n", md)

    # Strip remaining HTML tags
    md = re.sub(r"<[^>]+>", "", md)

    # Decode HTML entities
    md = md.replace("&nbsp;", " ")
    md = md.replace("&", "&")
    md = md.replace("<", "<")
    md = md.replace(">", ">")
    md = md.replace('"', '"')
    md = md.replace("&#39;", "'")

    # Collapse multiple blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


# ----------------------------------------------------------------------
# Helpers: Product classification
# ----------------------------------------------------------------------
def classify_page(page: dict, ancestor_titles: list[str] = None) -> str:
    """
    Classify a page into one of four product categories based on its title
    and ancestor titles.

    Returns one of: "olx", "standvirtual", "imovirtual", "transversal"
    """
    # Collect all titles to check (page title first, then ancestors)
    titles_to_check = []
    page_title = page.get("title", "")
    if page_title:
        titles_to_check.append(page_title)
    if ancestor_titles:
        titles_to_check.extend(ancestor_titles)

    combined = " ".join(titles_to_check).lower()

    # Check for product keywords (case-insensitive)
    if re.search(r"standvirtual|stand\s*virtual", combined):
        return "standvirtual"
    if re.search(r"imovirtual|imo\s*virtual", combined):
        return "imovirtual"
    if re.search(r"\bolx\b", combined):
        return "olx"

    # Default to transversal (cross-product content)
    return "transversal"


# ----------------------------------------------------------------------
# Helpers: File saving
# ----------------------------------------------------------------------
def save_markdown(title: str, content: str, product: str) -> Path:
    """Save a page's markdown content to the appropriate subdirectory."""
    slug = slugify(title)
    if not slug:
        slug = f"page-{int(time.time())}"

    filename = f"{slug}.md"
    product_dir = OUT_DIR / PRODUCT_SUBDIRS[product]
    product_dir.mkdir(parents=True, exist_ok=True)
    filepath = product_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(content)
        f.write("\n")

    return filepath


# ----------------------------------------------------------------------
# Main sync logic
# ----------------------------------------------------------------------
def sync() -> None:
    """Run the full Confluence to wiki_data sync."""
    print(f"Connecting to Confluence at nasperclassifieds.atlassian.net...")
    print(f"Target space: {SPACE_KEY}")
    print(f"Output directory: {OUT_DIR}")
    print()

    errors: list[dict] = []
    breakdown: dict[str, int] = {
        "olx": 0,
        "standvirtual": 0,
        "imovirtual": 0,
        "transversal": 0,
    }
    saved_files: list[dict] = []

    # ------------------------------------------------------------------
    # Step 1: Fetch the OCP space (try v2 first, fall back to v1)
    # ------------------------------------------------------------------
    space = None
    api_version = None

    try:
        space = fetch_space_v2()
        api_version = "v2"
    except Exception as exc:
        if "credentials not configured" in str(exc).lower():
            raise  # Let check_auth_error handle this
        print(f"  [v2] Failed: {exc}")
        print("  Falling back to API v1...")

    if space is None:
        try:
            space = fetch_space_v1()
            api_version = "v1"
        except Exception as exc:
            if "credentials not configured" in str(exc).lower():
                raise
            print(f"  [v1] Failed: {exc}")
            raise RuntimeError(
                f"Could not connect to Confluence using API v2 or v1. "
                f"Last error: {exc}"
            )

    space_id = space.get("id")
    space_key = space.get("key")

    # ------------------------------------------------------------------
    # Step 2: Fetch all pages in the space
    # ------------------------------------------------------------------
    print()
    try:
        if api_version == "v2":
            pages = fetch_pages_v2(space_id)
        else:
            pages = fetch_pages_v1(space_key)
    except Exception as exc:
        if "credentials not configured" in str(exc).lower():
            raise
        raise RuntimeError(f"Failed to fetch pages: {exc}")

    total_pages = len(pages)
    print(f"\n  Total pages found: {total_pages}")
    print()

    # ------------------------------------------------------------------
    # Step 3: Fetch each page content, classify, and save
    # ------------------------------------------------------------------
    for idx, page in enumerate(pages, 1):
        page_id = page.get("id")
        page_title = page.get("title", f"untitled-{page_id}")
        page_status = page.get("status", "current")

        # Skip non-current pages (deleted, archived)
        if page_status not in ("current", "draft"):
            print(f"  [{idx}/{total_pages}] Skipping '{page_title}' "
                  f"(status: {page_status})")
            continue

        print(f"  [{idx}/{total_pages}] Syncing: {page_title}...", end=" ")

        try:
            if api_version == "v2":
                content = fetch_page_content_v2(page_id)
            else:
                content = fetch_page_content_v1(page_id)
        except Exception as exc:
            msg = str(exc)
            print(f"ERROR ({msg})")
            errors.append({
                "page_id": page_id,
                "title": page_title,
                "error": msg,
            })
            continue

        # Classify by product
        product = classify_page(page)
        breakdown[product] += 1

        # Save to file
        try:
            filepath = save_markdown(page_title, content, product)
            print(f"Saved to {filepath.relative_to(OUT_DIR.parent)}")
            saved_files.append({
                "page_id": page_id,
                "title": page_title,
                "product": product,
                "filepath": str(filepath),
            })
        except Exception as exc:
            msg = str(exc)
            print(f"ERROR saving ({msg})")
            errors.append({
                "page_id": page_id,
                "title": page_title,
                "error": f"Save failed: {msg}",
            })

    # ------------------------------------------------------------------
    # Step 4: Write sync log
    # ------------------------------------------------------------------
    sync_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "api_version": api_version,
        "space_key": SPACE_KEY,
        "total_pages": total_pages,
        "pages_synced": sum(breakdown.values()),
        "breakdown_by_product": breakdown,
        "errors": errors,
        "saved_files": saved_files,
    }

    with open(SYNC_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(sync_record, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Step 5: Print summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("SYNC COMPLETE")
    print("=" * 60)
    print(f"  Total pages in space : {total_pages}")
    print(f"  Pages successfully   : {sum(breakdown.values())}")
    print(f"  Errors               : {len(errors)}")
    print()
    print("  Breakdown by product:")
    print(f"    OLX         : {breakdown['olx']}")
    print(f"    Standvirtual: {breakdown['standvirtual']}")
    print(f"    Imovirtual  : {breakdown['imovirtual']}")
    print(f"    Transversal : {breakdown['transversal']}")
    print()
    print(f"  Sync log saved to    : {SYNC_LOG_PATH}")

    if errors:
        print()
        print("  Errors:")
        for err in errors:
            print(f"    - [{err['page_id']}] {err['title']}: {err['error']}")

    print()
    if errors:
        sys.exit(1)
    else:
        sys.exit(0)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    try:
        sync()
    except Exception as exc:
        print(f"FATAL: {exc}")
        sys.exit(1)
