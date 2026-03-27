#!/usr/bin/env python3
"""
Chapter Rebuild Script - 章構成JSONから chapters/ を再生成

Usage:
    python rebuild_chapters.py <book_dir>
    python rebuild_chapters.py <book_dir> --dry-run

Input:
    <book_dir>/chapter_override.json
    <book_dir>/pages/*.md

Output:
    <book_dir>/chapters/*.md
    <book_dir>/README.md
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple


class Chapter(NamedTuple):
    number: str
    title: str
    start_page: int
    end_page: int


def extract_page_num(filename: str) -> int:
    """ファイル名からページ番号を抽出 (例: xxx_p001.md -> 1)"""
    match = re.search(r'_p(\d+)\.md$', filename)
    if match:
        return int(match.group(1))
    return 0


def generate_filename(index: int, title: str) -> str:
    """章ファイル名を生成"""
    safe_title = re.sub(r'[/\\:*?"<>|]', '', title)
    safe_title = safe_title.replace(' ', '_').replace('　', '_')
    # 長すぎるタイトルは切り詰め
    if len(safe_title) > 50:
        safe_title = safe_title[:50]
    return f"{index:02d}_{safe_title}.md"


def load_chapter_config(book_dir: Path) -> tuple[str, int, list[Chapter]]:
    """chapter_override.json を読み込み"""
    config_path = book_dir / "chapter_override.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    book_title = config.get('book_title', book_dir.name)
    total_pages = config.get('total_pages', 0)

    chapters = []
    for ch in config.get('chapters', []):
        chapters.append(Chapter(
            number=str(ch.get('number', '')),
            title=ch.get('title', ''),
            start_page=ch.get('start_page', 1),
            end_page=ch.get('end_page', total_pages)
        ))

    return book_title, total_pages, chapters


def merge_pages(pages_dir: Path, chapters_dir: Path, chapters: list[Chapter]) -> list[str]:
    """ページファイルを章ごとにマージ"""
    chapters_dir.mkdir(exist_ok=True)

    # ページファイルをマップ化
    page_files = {}
    for p in pages_dir.glob("*.md"):
        page_num = extract_page_num(p.name)
        if page_num > 0:
            page_files[page_num] = p

    created_files = []

    for i, chapter in enumerate(chapters):
        filename = generate_filename(i, chapter.title)
        output_path = chapters_dir / filename

        content_parts = [f"# {chapter.title}\n\n"]

        for page_num in range(chapter.start_page, chapter.end_page + 1):
            if page_num in page_files:
                page_content = page_files[page_num].read_text(encoding='utf-8')
                content_parts.append(f"<!-- page:{page_num} -->\n")
                content_parts.append(page_content)
                content_parts.append("\n\n")

        output_path.write_text(''.join(content_parts), encoding='utf-8')
        created_files.append(filename)
        print(f"  Created: {filename} (pages {chapter.start_page}-{chapter.end_page})")

    return created_files


def generate_readme(book_dir: Path, book_title: str, total_pages: int,
                   chapters: list[Chapter], filenames: list[str]) -> None:
    """README.md を生成"""
    readme_path = book_dir / "README.md"

    lines = [
        f"# {book_title}\n",
        "",
        "---",
        "",
        "## 目次",
        "",
        "| No. | タイトル | ファイル |",
        "|-----|---------|----------|",
    ]

    for chapter, filename in zip(chapters, filenames):
        lines.append(
            f"| {chapter.number} | [{chapter.title}](chapters/{filename}) | `{filename}` |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## OCR情報",
        "",
        f"- **処理日**: {datetime.now().strftime('%Y-%m-%d')}",
        "- **ツール**: yomitoku",
        f"- **総ページ数**: {total_pages}ページ",
        f"- **章再構築**: rebuild_chapters.py",
        "",
        "---",
        "",
        "## フォルダ構成",
        "",
        "```",
        f"{book_title}/",
        "├── README.md",
        "├── chapters/",
    ])

    for fn in filenames[:3]:
        lines.append(f"│   ├── {fn}")
    if len(filenames) > 3:
        lines.append("│   └── ...")

    lines.extend([
        "└── pages/",
        "```",
        "",
    ])

    readme_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"  Created: README.md")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    book_dir = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv

    if not book_dir.exists():
        print(f"Error: Directory not found: {book_dir}")
        sys.exit(1)

    pages_dir = book_dir / "pages"
    chapters_dir = book_dir / "chapters"

    if not pages_dir.exists():
        print(f"Error: pages/ directory not found in {book_dir}")
        sys.exit(1)

    print(f"=== Rebuilding chapters for: {book_dir.name} ===")

    try:
        book_title, total_pages, chapters = load_chapter_config(book_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"  Book: {book_title}")
    print(f"  Total pages: {total_pages}")
    print(f"  Chapters: {len(chapters)}")

    if dry_run:
        print("\n[Dry run - no files will be created]")
        for i, ch in enumerate(chapters):
            fn = generate_filename(i, ch.title)
            print(f"  Would create: {fn} (pages {ch.start_page}-{ch.end_page})")
        return

    # 既存の chapters/ をバックアップ（あれば）
    if chapters_dir.exists():
        backup_dir = book_dir / f"chapters_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        chapters_dir.rename(backup_dir)
        print(f"  Backed up existing chapters/ to {backup_dir.name}")

    print("\nMerging pages...")
    filenames = merge_pages(pages_dir, chapters_dir, chapters)

    print("\nGenerating README...")
    generate_readme(book_dir, book_title, total_pages, chapters, filenames)

    # 完了マーカー更新
    (book_dir / ".rebuild_complete").touch()

    print(f"\n=== Done! {len(chapters)} chapters created ===")


if __name__ == "__main__":
    main()
