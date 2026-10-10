#!/usr/bin/env python3
"""
archive_arabic_to_markdown.py
=============================

Zero-dependency converter that extracts clean, properly ordered Arabic Markdown
from Internet Archive (archive.org) books.

Why this exists:
----------------
1. Standard PDF extractors (`markitdown`, `pdfminer`, `pymupdf`) extract the
   embedded OCR layer from Archive.org `*_text.pdf` files in **reversed visual
   RTL order** (e.g., `مصر` -> `رصم`).
2. Re-running OCR locally on 100MB+ scanned PDFs is slow and fails on older CPUs
   that lack `X86_V2` instructions required by NumPy 2.x / PyTorch.
3. Internet Archive already stores structured, logical-order per-page OCR output
   in `*_djvu.xml` alongside every `*_text.pdf` file. This script fetches that
   structured XML directly, removes harakat/diacritic OCR noise lines, normalizes
   Arabic presentation forms (NFKC), and outputs clean Markdown in ~2 seconds
   per volume using **only Python's standard library**.

Usage Examples:
---------------
    # Convert a single Archive.org PDF or XML URL:
    python archive_arabic_to_markdown.py --url https://ia801609.us.archive.org/23/items/alhelawy07/bn01_text.pdf

    # Convert ALL volumes in an Archive.org item automatically:
    python archive_arabic_to_markdown.py --item alhelawy07 --output-dir ./output

    # Convert specific volumes from an Archive.org item:
    python archive_arabic_to_markdown.py --item alhelawy07 --volumes bn01 bn02 bn03

Author: Open Source Contributors
License: MIT
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Optional


USER_AGENT = "ArchiveArabicToMarkdown/1.0 (https://github.com/)"


def fetch_bytes(url: str, retries: int = 3, timeout: int = 60) -> bytes:
    """Download raw bytes from a URL with automatic retry on transient errors."""
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                wait_s = attempt * 2
                print(f"  [!] Retry {attempt}/{retries} after error ({exc})... waiting {wait_s}s")
                time.sleep(wait_s)
    raise RuntimeError(f"Failed to download {url} after {retries} attempts: {last_err}")


def is_diacritic_noise_line(line: str) -> bool:
    """
    Detect isolated OCR noise lines caused by Arabic vowel marks (harakat)
    floating above a line of text.

    Returns True if the line consists primarily of 1-2 character fragments or
    Latin/symbol OCR garbage rather than actual Arabic words or footnote markers.
    """
    tokens = line.split()
    if not tokens:
        return True

    # Words containing 3 or more Arabic letters/diacritics
    real_arabic_words = re.findall(r"[\u0621-\u064A\u064B-\u065F]{3,}", line)

    # Keep numbered footnotes/references such as (١), (1), [2], etc.
    has_reference_number = bool(re.search(r"[\(\[\)\]\d\u0660-\u0669]{2,}", line))

    if not real_arabic_words and not has_reference_number:
        return True

    # Count tokens that have at most 2 base Arabic letters
    short_tokens = [
        t for t in tokens if len(re.sub(r"[^\u0621-\u064A]", "", t)) <= 2
    ]
    if (
        len(tokens) >= 4
        and len(real_arabic_words) <= 1
        and (len(short_tokens) / len(tokens)) >= 0.75
    ):
        return True

    return False


def djvu_xml_to_markdown(
    xml_bytes: bytes,
    title: str,
    keep_noise_lines: bool = False,
) -> tuple[str, int]:
    """
    Parse Archive.org DjVu XML bytes into structured Arabic Markdown.

    Args:
        xml_bytes: Raw bytes of the `*_djvu.xml` file.
        title: Top-level Markdown H1 heading for the document.
        keep_noise_lines: If True, disables diacritic noise-line filtering.

    Returns:
        Tuple of (markdown_content, number_of_non_empty_pages).
    """
    root = ET.fromstring(xml_bytes)
    page_objects = root.findall(".//OBJECT")

    md_pages: List[str] = []
    for page_idx, obj in enumerate(page_objects, start=1):
        paragraphs: List[str] = []
        for par in obj.findall(".//PARAGRAPH"):
            lines: List[str] = []
            for line_el in par.findall(".//LINE"):
                words = [
                    w.text.strip()
                    for w in line_el.findall(".//WORD")
                    if w.text and w.text.strip()
                ]
                if not words:
                    # Fallback if text is directly inside <LINE> without <WORD> tags
                    raw_line = "".join(line_el.itertext()).strip()
                    words = raw_line.split()

                line_str = unicodedata.normalize("NFKC", " ".join(words)).strip()
                if not line_str:
                    continue
                if not keep_noise_lines and is_diacritic_noise_line(line_str):
                    continue
                lines.append(line_str)

            if lines:
                paragraphs.append("\n".join(lines))

        if paragraphs:
            page_block = f"## الصفحة {page_idx}\n\n" + "\n\n".join(paragraphs)
            md_pages.append(page_block)

    full_markdown = f"# {title}\n\n" + "\n\n---\n\n".join(md_pages) + "\n"
    return full_markdown, len(md_pages)


def resolve_xml_url_from_any_archive_url(url: str) -> tuple[str, str]:
    """
    Convert any Archive.org file URL (such as `.../bn01_text.pdf` or `.../bn01.pdf`)
    into its corresponding `*_djvu.xml` URL and volume name.
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    filename = Path(path).name

    for suffix in ("_text.pdf", ".pdf", "_djvu.txt", "_hocr.html", "_djvu.xml"):
        if filename.endswith(suffix):
            vol_prefix = filename[: -len(suffix)]
            xml_path = path[: -len(filename)] + f"{vol_prefix}_djvu.xml"
            xml_url = urllib.parse.urlunparse(parsed._replace(path=xml_path))
            return xml_url, vol_prefix

    raise ValueError(
        f"Could not determine volume prefix from URL '{url}'. "
        "Expected a URL ending with _text.pdf, .pdf, or _djvu.xml."
    )


def discover_item_volumes(item_id: str) -> tuple[str, List[str]]:
    """
    Query the Internet Archive Metadata API to find the download server and
    all `*_djvu.xml` volumes available inside an Archive.org item.
    """
    meta_url = f"https://archive.org/metadata/{item_id}"
    meta = json.loads(fetch_bytes(meta_url).decode("utf-8"))

    server = meta.get("d1") or meta.get("server") or "archive.org"
    dir_path = meta.get("dir") or f"/download/{item_id}"
    base_url = f"https://{server}{dir_path}"

    volumes: List[str] = []
    for f in meta.get("files", []):
        name = f.get("name", "")
        if name.endswith("_djvu.xml"):
            volumes.append(name[: -len("_djvu.xml")])

    return base_url, sorted(volumes)


def convert_single_url(
    url: str,
    output_dir: Path,
    keep_noise_lines: bool = False,
) -> Path:
    """Download and convert a single Archive.org PDF/XML URL into Markdown."""
    xml_url, vol_name = resolve_xml_url_from_any_archive_url(url)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{vol_name}.md"

    t0 = time.time()
    print(f"[*] Fetching structured OCR XML: {xml_url}")
    xml_bytes = fetch_bytes(xml_url)

    md_text, page_count = djvu_xml_to_markdown(
        xml_bytes=xml_bytes,
        title=vol_name,
        keep_noise_lines=keep_noise_lines,
    )
    out_file.write_text(md_text, encoding="utf-8")
    elapsed = time.time() - t0
    print(f"[+] Saved '{out_file}' ({page_count} pages, {len(md_text):,} chars in {elapsed:.2f}s)")
    return out_file


def convert_item(
    item_id: str,
    output_dir: Path,
    selected_volumes: Optional[Iterable[str]] = None,
    keep_noise_lines: bool = False,
) -> List[Path]:
    """Download and convert all (or selected) volumes inside an Archive.org item."""
    print(f"[*] Querying Archive.org metadata for item: '{item_id}' ...")
    base_url, all_volumes = discover_item_volumes(item_id)

    if not all_volumes:
        raise RuntimeError(f"No *_djvu.xml files found in Archive.org item '{item_id}'.")

    if selected_volumes:
        wanted = set(selected_volumes)
        volumes = [v for v in all_volumes if v in wanted]
    else:
        volumes = all_volumes

    print(f"[*] Found {len(volumes)} volume(s) to convert: {', '.join(volumes)}")
    saved_files: List[Path] = []
    for idx, vol in enumerate(volumes, start=1):
        xml_url = f"{base_url}/{vol}_djvu.xml"
        print(f"\n--- [{idx}/{len(volumes)}] Volume: {vol} ---")
        saved = convert_single_url(
            url=xml_url,
            output_dir=output_dir,
            keep_noise_lines=keep_noise_lines,
        )
        saved_files.append(saved)

    return saved_files


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Internet Archive (archive.org) Arabic PDFs/books to clean Markdown in seconds.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-u",
        "--url",
        help="Direct Archive.org URL to a *_text.pdf, *.pdf, or *_djvu.xml file "
             "(e.g., https://ia801609.us.archive.org/23/items/alhelawy07/bn01_text.pdf)",
    )
    group.add_argument(
        "-i",
        "--item",
        help="Archive.org item identifier to convert all volumes automatically (e.g., alhelawy07)",
    )
    parser.add_argument(
        "-v",
        "--volumes",
        nargs="+",
        help="Optional list of specific volume prefixes when using --item (e.g., bn01 bn02)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("output_markdown"),
        help="Directory to save generated Markdown files (default: ./output_markdown)",
    )
    parser.add_argument(
        "--keep-noise-lines",
        action="store_true",
        help="Disable automatic filtering of floating harakat/diacritic OCR noise lines",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        if args.url:
            convert_single_url(
                url=args.url,
                output_dir=args.output_dir,
                keep_noise_lines=args.keep_noise_lines,
            )
        else:
            convert_item(
                item_id=args.item,
                output_dir=args.output_dir,
                selected_volumes=args.volumes,
                keep_noise_lines=args.keep_noise_lines,
            )
        return 0
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
