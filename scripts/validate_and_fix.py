#!/usr/bin/env python3
"""
Chapter Validation and Auto-Fix Script

process_book.py 実行後に章分割の品質を検証し、問題があれば自動修正する。

Usage:
    python validate_and_fix.py <book_dir>

処理フロー:
1. chapters/ の品質をチェック
2. 問題検出時:
   - pages/ から目次を再解析
   - chapter_override.json を生成
   - rebuild_chapters.py を実行
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChapterInfo:
    number: str
    title: str
    start_page: int
    end_page: int


def get_chapter_files(chapters_dir: Path) -> list[Path]:
    """章ファイルを取得"""
    if not chapters_dir.exists():
        return []
    return sorted(chapters_dir.glob("*.md"))


def get_page_files(pages_dir: Path) -> list[Path]:
    """ページファイルを取得"""
    if not pages_dir.exists():
        return []
    return sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))


def extract_page_num(filename: str) -> int:
    """ファイル名からページ番号を抽出"""
    match = re.search(r'_p(\d+)\.md$', filename)
    return int(match.group(1)) if match else 0


def check_chapter_quality(book_dir: Path) -> tuple[bool, list[str]]:
    """
    章分割の品質をチェック

    Returns:
        (is_valid, issues): 問題なければTrue、問題リスト
    """
    chapters_dir = book_dir / "chapters"
    pages_dir = book_dir / "pages"

    issues = []
    chapter_files = get_chapter_files(chapters_dir)
    page_files = get_page_files(pages_dir)

    if not chapter_files:
        issues.append("No chapter files found")
        return False, issues

    total_pages = len(page_files)

    # Issue 1: 単一ファイルに全ページが入っている
    if len(chapter_files) == 1:
        file_size = chapter_files[0].stat().st_size
        # 100KB以上のファイルは問題あり（全ページ統合の可能性）
        if file_size > 100_000 and total_pages > 50:
            issues.append(f"Single file contains all content ({file_size // 1024}KB)")

    # Issue 2: 章の数が少なすぎる（総ページ数に対して）
    if total_pages > 100 and len(chapter_files) < 3:
        issues.append(f"Too few chapters ({len(chapter_files)}) for {total_pages} pages")

    # Issue 3: 章ファイルのサイズが極端に偏っている、または極小ファイルがある
    sizes = [f.stat().st_size for f in chapter_files]
    if len(sizes) > 1:
        max_size = max(sizes)
        min_size = min(sizes)
        avg_size = sum(sizes) / len(sizes)

        # 最小が500バイト未満のファイルがある（ほぼ空）
        if min_size < 500:
            tiny_files = [f.name for f in chapter_files if f.stat().st_size < 500]
            issues.append(f"Tiny chapter files: {tiny_files}")

        # 最大が平均の10倍以上
        if max_size > avg_size * 10:
            issues.append(f"Extreme size imbalance (max:{max_size//1024}KB, avg:{int(avg_size)//1024}KB)")

    # Issue 4: 章の順序がおかしい（第1章の後に第14章など）
    chapter_numbers = []
    for f in chapter_files:
        match = re.search(r'第(\d+)章', f.name)
        if match:
            chapter_numbers.append(int(match.group(1)))

    if chapter_numbers:
        # ソートして連続性をチェック
        sorted_nums = sorted(chapter_numbers)
        if sorted_nums != chapter_numbers:
            issues.append(f"Chapters out of order: {chapter_numbers}")

        # 欠番チェック
        if sorted_nums:
            expected = list(range(sorted_nums[0], sorted_nums[-1] + 1))
            missing = set(expected) - set(sorted_nums)
            if missing and len(missing) > len(sorted_nums) // 2:
                issues.append(f"Many missing chapters: {sorted(missing)}")

    # Issue 5: ファイル名が壊れている（文字化けや不完全）
    for f in chapter_files:
        name = f.stem
        # 極端に短いタイトル（数字2つ + アンダースコアのみ）
        if len(name) < 5 or name.endswith('_'):
            issues.append(f"Broken filename: {f.name}")
            break

    return len(issues) == 0, issues


def find_toc_in_pages(pages_dir: Path) -> Optional[tuple[int, str]]:
    """目次ページを検索"""
    page_files = get_page_files(pages_dir)

    toc_patterns = [
        r'^\s*#?\s*(目\s*次|もくじ|CONTENTS)',
    ]

    toc_contents = []
    toc_start = None

    for page_file in page_files[:30]:
        content = page_file.read_text(encoding='utf-8')
        page_num = extract_page_num(page_file.name)

        if toc_start is None:
            for pattern in toc_patterns:
                if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
                    toc_start = page_num
                    toc_contents.append((page_num, content))
                    break
        elif toc_start is not None:
            # 目次の続きかチェック
            has_chapter_refs = re.search(r'(第\s*\d+\s*章|はじめに|あとがき)', content)
            has_page_nums = re.search(r'\d{1,3}\s*$', content, re.MULTILINE)

            if has_chapter_refs or has_page_nums:
                toc_contents.append((page_num, content))
            else:
                break

            if len(toc_contents) >= 5:
                break

    if toc_contents:
        combined = '\n'.join(c for _, c in toc_contents)
        return toc_start, combined

    return None


def extract_chapters_from_toc(toc_content: str) -> list[ChapterInfo]:
    """目次から章情報を抽出"""
    chapters = []
    seen = set()

    lines = toc_content.split('\n')

    # 漢数字変換マップ
    kanji_nums = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
        '十一': '11', '十二': '12', '十三': '13', '十四': '14', '十五': '15',
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 第N章パターン（アラビア数字）
        match = re.search(r'(第\s*(\d+)\s*章)\s*(.+?)[\s…\.・]*(\d{1,3})\s*$', line)
        if match:
            num = match.group(2)
            if num not in seen:
                seen.add(num)
                title = f"{match.group(1)} {match.group(3).strip()}"
                chapters.append(ChapterInfo(
                    number=num,
                    title=title,
                    start_page=int(match.group(4)),
                    end_page=0
                ))
            continue

        # 第N章パターン（漢数字: 第一章〜第十五章）
        match = re.search(r'(第\s*(一|二|三|四|五|六|七|八|九|十|十一|十二|十三|十四|十五)\s*章)\s*(.+?)(\d{1,3})\s*$', line)
        if match:
            kanji = match.group(2)
            num = kanji_nums.get(kanji, kanji)
            if num not in seen:
                seen.add(num)
                title = f"{match.group(1)} {match.group(3).strip()}"
                chapters.append(ChapterInfo(
                    number=num,
                    title=title,
                    start_page=int(match.group(4)),
                    end_page=0
                ))
            continue

        # プロローグ/はじめに
        match = re.search(r'(プロローグ|はじめに|序章|序文|まえがき)\s*[^\d]*?(\d{1,3})\s*$', line)
        if match and "序" not in seen:
            seen.add("序")
            chapters.append(ChapterInfo(
                number="序",
                title=match.group(1),
                start_page=int(match.group(2)),
                end_page=0
            ))
            continue

        # エピローグ/あとがき
        match = re.search(r'(エピローグ|あとがき|おわりに)\s*[^\d]*?(\d{1,3})\s*$', line)
        if match and "後" not in seen:
            seen.add("後")
            chapters.append(ChapterInfo(
                number="後",
                title=match.group(1),
                start_page=int(match.group(2)),
                end_page=0
            ))
            continue

        # 終章
        match = re.search(r'(終\s*章)\s*(.*)(\d{1,3})\s*$', line)
        if match and "終" not in seen:
            seen.add("終")
            title = match.group(1) + (" " + match.group(2).strip() if match.group(2).strip() else "")
            chapters.append(ChapterInfo(
                number="終",
                title=title,
                start_page=int(match.group(3)),
                end_page=0
            ))

    # ページ番号でソート
    chapters.sort(key=lambda c: c.start_page)

    return chapters


def kanji_to_num(kanji: str) -> str:
    """漢数字をアラビア数字に変換"""
    kanji_map = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
        '十一': '11', '十二': '12', '十三': '13', '十四': '14', '十五': '15',
    }
    return kanji_map.get(kanji, kanji)


def find_toc_end_page(pages_dir: Path) -> int:
    """目次の終了ページを推定（本文開始位置）"""
    page_files = get_page_files(pages_dir)

    toc_started = False
    last_toc_page = 0

    for page_file in page_files[:40]:
        content = page_file.read_text(encoding='utf-8')
        page_num = extract_page_num(page_file.name)
        lines = content.split('\n')

        # 目次キーワードを検出
        if re.search(r'(目\s*次|もくじ|CONTENTS)', content, re.IGNORECASE):
            toc_started = True
            last_toc_page = page_num
            continue

        if toc_started:
            # 目次ページの特徴をチェック
            # 1. 行末にページ番号パターンが多い
            page_num_lines = sum(1 for l in lines if re.search(r'\d{1,3}\s*$', l.strip()))

            # 2. 短い行が多い（平均行長が短い）
            line_lengths = [len(l.strip()) for l in lines if l.strip()]
            avg_length = sum(line_lengths) / len(line_lengths) if line_lengths else 0

            # 3. 章パターンが複数ある（目次は章リストなので）
            chapter_refs = len(re.findall(r'第\s*[\d一二三四五六七八九十]+\s*章', content))

            # 目次の続きと判定（ページ番号パターン3つ以上、または章参照2つ以上）
            if page_num_lines >= 3 or chapter_refs >= 2:
                last_toc_page = page_num
                continue

            # 本文開始の兆候: 長い段落があり、章パターンが少ない
            has_long_paragraph = any(len(l.strip()) > 80 for l in lines)
            if has_long_paragraph and chapter_refs <= 1:
                return page_num

    # フォールバック: 目次終了後の最初のページ、または15
    return last_toc_page + 1 if last_toc_page > 0 else 15


def scan_chapters_from_pages(pages_dir: Path) -> list[ChapterInfo]:
    """
    ページファイルを直接スキャンして章見出しを検出
    目次が見つからない/解析できない場合のフォールバック

    重要: #（Markdownヘッダー）で始まる行のみを章見出しとして認識
    これにより目次ページでの誤検出を防ぐ
    """
    chapters = []
    seen = set()

    page_files = get_page_files(pages_dir)

    # 目次の終了ページを推定
    toc_end = find_toc_end_page(pages_dir)
    print(f"  TOC ends at page {toc_end}")

    # 章パターン（# で始まる見出しのみ）
    patterns = [
        # 第N章（アラビア数字）- # 必須
        (r'^#\s*(第\s*(\d+)\s*章)', 'chapter_arabic'),
        # 第一章〜第十五章（漢数字）- # 必須
        (r'^#\s*(第\s*(一|二|三|四|五|六|七|八|九|十|十一|十二|十三|十四|十五)\s*章)', 'chapter_kanji'),
        # プロローグ/はじめに - # 必須
        (r'^#\s*(プロローグ|はじめに|序章|序文|まえがき)', 'intro'),
        # 終章 - # 必須
        (r'^#\s*(終\s*章)', 'final'),
        # エピローグ/あとがき - # 必須
        (r'^#\s*(エピローグ|あとがき|おわりに)', 'outro'),
        # 参考文献 - # 必須
        (r'^#\s*(参考文献|引用文献|索引)', 'refs'),
    ]

    for page_file in page_files:
        content = page_file.read_text(encoding='utf-8')
        page_num = extract_page_num(page_file.name)

        # 最初の5行のみ検索（章見出しはページ上部）
        for line in content.split('\n')[:5]:
            line = line.strip()

            # # で始まらない行はスキップ（目次ページ対策）
            if not line.startswith('#'):
                continue

            # 目次エントリを除外: 末尾にページ番号（またはOCR誤読）がある場合
            # 例: "# 第二章 分析するo6g" (069の誤読), "# 第三章 書く131"
            # パターン: 末尾に数字/英小文字の2-4文字の組み合わせ
            if re.search(r'[a-z0-9]{2,4}\s*$', line) and not re.search(r'[ぁ-んァ-ヶ一-龥]\s*$', line):
                continue

            for pattern, ptype in patterns:
                match = re.search(pattern, line)
                if match:
                    if ptype == 'chapter_arabic':
                        num = match.group(2)
                        if num not in seen:
                            seen.add(num)
                            chapters.append(ChapterInfo(
                                number=num,
                                title=match.group(1),
                                start_page=page_num,
                                end_page=0
                            ))
                    elif ptype == 'chapter_kanji':
                        kanji_num = match.group(2)
                        num = kanji_to_num(kanji_num)
                        if num not in seen:
                            seen.add(num)
                            chapters.append(ChapterInfo(
                                number=num,
                                title=match.group(1),
                                start_page=page_num,
                                end_page=0
                            ))
                    elif ptype == 'intro' and "序" not in seen:
                        seen.add("序")
                        chapters.append(ChapterInfo(
                            number="序",
                            title=match.group(1),
                            start_page=page_num,
                            end_page=0
                        ))
                    elif ptype == 'final' and "終" not in seen:
                        seen.add("終")
                        chapters.append(ChapterInfo(
                            number="終",
                            title="終章",
                            start_page=page_num,
                            end_page=0
                        ))
                    elif ptype == 'outro' and "後" not in seen:
                        seen.add("後")
                        chapters.append(ChapterInfo(
                            number="後",
                            title=match.group(1),
                            start_page=page_num,
                            end_page=0
                        ))
                    elif ptype == 'refs' and "参" not in seen:
                        seen.add("参")
                        chapters.append(ChapterInfo(
                            number="参",
                            title=match.group(1),
                            start_page=page_num,
                            end_page=0
                        ))
                    break

    # ページ番号でソート
    chapters.sort(key=lambda c: c.start_page)

    return chapters


def calculate_end_pages(chapters: list[ChapterInfo], total_pages: int) -> list[ChapterInfo]:
    """各章の終了ページを計算"""
    for i, chapter in enumerate(chapters):
        if i + 1 < len(chapters):
            chapter.end_page = chapters[i + 1].start_page - 1
        else:
            chapter.end_page = total_pages
    return chapters


def generate_chapter_override(book_dir: Path, chapters: list[ChapterInfo], total_pages: int) -> Path:
    """chapter_override.json を生成"""
    config = {
        "book_title": book_dir.name,
        "total_pages": total_pages,
        "generated_by": "validate_and_fix.py",
        "chapters": [
            {
                "number": ch.number,
                "title": ch.title,
                "start_page": ch.start_page,
                "end_page": ch.end_page
            }
            for ch in chapters
        ]
    }

    override_path = book_dir / "chapter_override.json"
    override_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    return override_path


def run_rebuild(book_dir: Path, script_dir: Path) -> bool:
    """rebuild_chapters.py を実行"""
    rebuild_script = script_dir / "rebuild_chapters.py"

    if not rebuild_script.exists():
        print(f"  Error: rebuild_chapters.py not found at {rebuild_script}")
        return False

    result = subprocess.run(
        ["python3", str(rebuild_script), str(book_dir)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(result.stdout)
        return True
    else:
        print(f"  Error: {result.stderr}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_and_fix.py <book_dir>")
        sys.exit(1)

    book_dir = Path(sys.argv[1])
    pages_dir = book_dir / "pages"
    script_dir = Path(__file__).parent

    if not book_dir.exists():
        print(f"Error: Directory not found: {book_dir}")
        sys.exit(1)

    print(f"\n=== Validating: {book_dir.name} ===\n")

    # 1. 品質チェック
    print("[1/4] Checking chapter quality...")
    is_valid, issues = check_chapter_quality(book_dir)

    if is_valid:
        print("  ✓ Chapters look good, no fix needed")
        (book_dir / ".validation_passed").touch()
        return

    print("  Issues detected:")
    for issue in issues:
        print(f"    - {issue}")

    # 2. 章情報を再抽出
    print("\n[2/4] Re-extracting chapters...")

    total_pages = len(get_page_files(pages_dir))
    chapters = []

    # まず目次から
    toc_result = find_toc_in_pages(pages_dir)
    if toc_result:
        toc_page, toc_content = toc_result
        print(f"  Found TOC at page {toc_page}")
        chapters = extract_chapters_from_toc(toc_content)
        if chapters:
            print(f"  Extracted {len(chapters)} chapters from TOC")

    # 目次から取れなければページスキャン
    if not chapters or len(chapters) < 2:
        print("  Scanning pages for chapter headings...")
        chapters = scan_chapters_from_pages(pages_dir)
        print(f"  Found {len(chapters)} chapters from page scan")

    if not chapters:
        print("  Warning: Could not extract any chapters")
        print("  Please create chapter_override.json manually")
        sys.exit(1)

    # 終了ページを計算
    chapters = calculate_end_pages(chapters, total_pages)

    print("\n  Detected chapters:")
    for ch in chapters:
        print(f"    {ch.number}: {ch.title} (pages {ch.start_page}-{ch.end_page})")

    # 3. chapter_override.json を生成
    print("\n[3/4] Generating chapter_override.json...")
    override_path = generate_chapter_override(book_dir, chapters, total_pages)
    print(f"  Created: {override_path.name}")

    # 4. rebuild_chapters.py を実行
    print("\n[4/4] Rebuilding chapters...")
    success = run_rebuild(book_dir, script_dir)

    if success:
        print(f"\n=== Fix Complete! ===")
        (book_dir / ".validation_fixed").touch()
    else:
        print(f"\n=== Fix Failed ===")
        print(f"Manual intervention required")
        sys.exit(1)


if __name__ == "__main__":
    main()
