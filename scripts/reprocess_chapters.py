#!/usr/bin/env python3
"""
reprocess_chapters.py - 全書籍の章分割を再実行

Usage:
    python reprocess_chapters.py <ocr_output_dir> [--force] [--dry-run]

Options:
    --force     既存のchapters/をバックアップして強制再処理
    --dry-run   実際には処理せず、対象書籍を表示

処理フロー:
1. 各書籍ディレクトリを走査
2. pages/の存在を確認
3. 既存chapters/をバックアップ
4. process_book.py で章分割を再実行
5. 結果をレポート出力
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


def count_chapters(book_dir: Path) -> int:
    """現在の章ファイル数をカウント"""
    chapters_dir = book_dir / "chapters"
    if not chapters_dir.exists():
        return 0
    return len(list(chapters_dir.glob("*.md")))


def count_pages(book_dir: Path) -> int:
    """ページファイル数をカウント"""
    pages_dir = book_dir / "pages"
    if not pages_dir.exists():
        return 0
    return len(list(pages_dir.glob("*.md")))


def backup_chapters(book_dir: Path) -> str:
    """既存のchapters/をバックアップ"""
    chapters_dir = book_dir / "chapters"
    if not chapters_dir.exists():
        return ""

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = book_dir / f"chapters_backup_{timestamp}"
    chapters_dir.rename(backup_dir)
    return backup_dir.name


def reprocess_book(book_dir: Path, script_dir: Path, force: bool = False, dry_run: bool = False) -> dict:
    """1冊を再処理"""
    result = {
        "book": book_dir.name,
        "status": "skipped",
        "pages": count_pages(book_dir),
        "chapters_before": count_chapters(book_dir),
        "chapters_after": 0,
        "backup": "",
        "error": ""
    }

    pages_dir = book_dir / "pages"

    if not pages_dir.exists():
        result["status"] = "error"
        result["error"] = "No pages directory"
        return result

    if dry_run:
        result["status"] = "would_process"
        return result

    # バックアップ
    if force:
        result["backup"] = backup_chapters(book_dir)

    # process_book.py を再実行
    process_script = script_dir / "process_book.py"
    try:
        process_result = subprocess.run(
            ["python3", str(process_script), str(book_dir)],
            capture_output=True,
            text=True,
            timeout=600  # 10分タイムアウト
        )

        if process_result.returncode != 0:
            result["status"] = "error"
            result["error"] = process_result.stderr[:500] if process_result.stderr else "Unknown error"
        else:
            result["status"] = "success"
            result["chapters_after"] = count_chapters(book_dir)

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = "Process timed out after 10 minutes"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    ocr_output_dir = Path(sys.argv[1])
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if not ocr_output_dir.exists():
        print(f"Error: Directory not found: {ocr_output_dir}")
        sys.exit(1)

    # スクリプトディレクトリを取得
    script_dir = Path(__file__).parent

    print(f"=== Reprocessing chapters in: {ocr_output_dir} ===")
    print(f"Options: force={force}, dry_run={dry_run}")
    print()

    # 書籍ディレクトリを収集
    book_dirs = []
    for item in sorted(ocr_output_dir.iterdir()):
        if item.is_dir() and (item / "pages").exists():
            book_dirs.append(item)

    print(f"Found {len(book_dirs)} books with pages/")
    print()

    if dry_run:
        print("=== Dry Run - Would process: ===")
        for book_dir in book_dirs:
            pages = count_pages(book_dir)
            chapters = count_chapters(book_dir)
            print(f"  {book_dir.name}: {pages} pages, {chapters} chapters")
        return

    # 処理実行
    results = []
    for i, book_dir in enumerate(book_dirs, 1):
        print(f"[{i}/{len(book_dirs)}] Processing: {book_dir.name}")
        result = reprocess_book(book_dir, script_dir, force=force, dry_run=dry_run)
        results.append(result)

        if result["status"] == "success":
            print(f"  ✓ {result['chapters_before']} -> {result['chapters_after']} chapters")
        elif result["status"] == "error":
            print(f"  ✗ Error: {result['error'][:100]}")
        print()

    # サマリー出力
    print("=" * 60)
    print("=== Summary ===")
    print()

    success = [r for r in results if r["status"] == "success"]
    errors = [r for r in results if r["status"] == "error"]
    timeouts = [r for r in results if r["status"] == "timeout"]

    print(f"Success: {len(success)}/{len(results)}")
    print(f"Errors:  {len(errors)}")
    print(f"Timeouts: {len(timeouts)}")
    print()

    # 改善された書籍
    improved = [r for r in success if r["chapters_after"] > r["chapters_before"]]
    if improved:
        print("Improved books:")
        for r in improved:
            print(f"  {r['book']}: {r['chapters_before']} -> {r['chapters_after']} chapters")
        print()

    # エラー詳細
    if errors:
        print("Error details:")
        for r in errors:
            print(f"  {r['book']}: {r['error'][:80]}")
        print()

    # 結果をJSONに保存
    report_path = ocr_output_dir / f"reprocess_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
