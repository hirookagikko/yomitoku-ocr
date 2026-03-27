#!/usr/bin/env python3
"""
scan_tables.py - Markdownテーブルスキャナー

pages/*.md を高速スキャンし、テーブル位置・ヘッダー・密度をJSON出力。
ocr-workerパイプラインでテーブルリッチ判定に使用。

Usage:
    python3 scan_tables.py /path/to/ocr_output/bookname/

Output (stdout): JSON
    {
        "is_table_heavy": true,
        "pages_with_tables": 12,
        "total_data_rows": 85,
        "table_groups": [...],
        "pages": {...}
    }

判定基準:
    - テーブルを含むページが 5ページ以上 → テーブルリッチ
    - OR テーブルデータ行の合計が 20行以上 → テーブルリッチ
"""

import json
import hashlib
import re
import sys
from pathlib import Path


def extract_page_number(filename: str) -> int:
    """ファイル名からページ番号を抽出。例: _書籍名_p43.md → 43"""
    m = re.search(r'_p(\d+)\.md$', filename)
    return int(m.group(1)) if m else 0


def is_separator_line(line: str) -> bool:
    """Markdownテーブルのセパレータ行か判定。例: |-|-|-| or |---|---|"""
    stripped = line.strip()
    if not stripped.startswith('|') or not stripped.endswith('|'):
        return False
    cells = stripped.strip('|').split('|')
    return all(re.match(r'^[\s\-:]+$', c) for c in cells)


def is_table_line(line: str) -> bool:
    """Markdownテーブル行か判定。|...|...|"""
    stripped = line.strip()
    return (stripped.startswith('|') and stripped.endswith('|')
            and stripped.count('|') >= 3)


def header_hash(header_cells: list[str]) -> str:
    """ヘッダーセルのハッシュ値を生成（同一テーブル判定用）"""
    normalized = '|'.join(c.strip() for c in header_cells)
    return hashlib.md5(normalized.encode()).hexdigest()[:8]


def scan_page(filepath: Path) -> dict:
    """1ページのMarkdownをスキャンし、テーブル情報を返す"""
    text = filepath.read_text(encoding='utf-8')
    lines = text.split('\n')

    tables = []
    current_table_lines = []
    in_table = False

    for i, line in enumerate(lines):
        if is_table_line(line):
            if not in_table:
                in_table = True
                current_table_lines = []
            current_table_lines.append((i, line))
        else:
            if in_table and current_table_lines:
                tables.append(current_table_lines)
                current_table_lines = []
            in_table = False

    # 最後のテーブルを回収
    if in_table and current_table_lines:
        tables.append(current_table_lines)

    result_tables = []
    total_data_rows = 0

    for table_lines in tables:
        header_line = None
        separator_idx = None
        data_rows = []

        for idx, (line_no, line_text) in enumerate(table_lines):
            if is_separator_line(line_text):
                separator_idx = idx
                # セパレータの直前がヘッダー
                if idx > 0:
                    header_line = table_lines[idx - 1][1]
                break

        if separator_idx is None:
            # セパレータなし → ヘッダーなしテーブル（データ行のみ）
            data_rows = [l[1] for l in table_lines]
            header_cells = []
        else:
            header_cells = [c.strip() for c in
                            header_line.strip().strip('|').split('|')] if header_line else []
            # セパレータ以降がデータ行
            data_rows = [l[1] for l in table_lines[separator_idx + 1:]]

        # 空ヘッダーセルを除去
        header_cells = [c for c in header_cells if c]

        total_data_rows += len(data_rows)

        h_hash = header_hash(header_cells) if header_cells else None

        result_tables.append({
            'header': header_cells,
            'header_hash': h_hash,
            'data_row_count': len(data_rows),
            'column_count': max(
                (line.strip().strip('|').count('|') + 1
                 for _, line in table_lines),
                default=0
            ),
            'start_line': table_lines[0][0] + 1,
        })

    return {
        'has_tables': len(result_tables) > 0,
        'table_count': len(result_tables),
        'data_row_count': total_data_rows,
        'tables': result_tables,
    }


def group_tables(all_pages: dict) -> list[dict]:
    """同一ヘッダーのテーブルをグループ化"""
    groups = {}

    for page_num, page_info in all_pages.items():
        for table in page_info['tables']:
            h_hash = table.get('header_hash')
            if not h_hash:
                continue

            if h_hash not in groups:
                groups[h_hash] = {
                    'header_hash': h_hash,
                    'header': table['header'],
                    'column_count': table['column_count'],
                    'pages': [],
                    'total_data_rows': 0,
                }

            groups[h_hash]['pages'].append(int(page_num))
            groups[h_hash]['total_data_rows'] += table['data_row_count']

    # ページをソート
    for g in groups.values():
        g['pages'].sort()

    return sorted(groups.values(), key=lambda g: g['total_data_rows'], reverse=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scan_tables.py <ocr_output_dir>", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    pages_dir = output_dir / 'pages'

    if not pages_dir.exists():
        print(json.dumps({
            'error': f'pages/ directory not found: {pages_dir}',
            'is_table_heavy': False,
        }))
        sys.exit(1)

    md_files = sorted(pages_dir.glob('*.md'), key=lambda f: extract_page_number(f.name))

    if not md_files:
        print(json.dumps({
            'error': 'No .md files found in pages/',
            'is_table_heavy': False,
        }))
        sys.exit(1)

    all_pages = {}
    pages_with_tables = 0
    total_data_rows = 0

    for md_file in md_files:
        page_num = extract_page_number(md_file.name)
        if page_num == 0:
            continue

        page_info = scan_page(md_file)
        if page_info['has_tables']:
            pages_with_tables += 1
            total_data_rows += page_info['data_row_count']
            all_pages[str(page_num)] = page_info

    table_groups = group_tables(all_pages)

    is_table_heavy = pages_with_tables >= 5 or total_data_rows >= 20

    result = {
        'is_table_heavy': is_table_heavy,
        'total_pages_scanned': len(md_files),
        'pages_with_tables': pages_with_tables,
        'total_data_rows': total_data_rows,
        'table_groups': table_groups,
        'pages': {k: {
            'table_count': v['table_count'],
            'data_row_count': v['data_row_count'],
            'headers': [t['header'] for t in v['tables'] if t['header']],
        } for k, v in all_pages.items()},
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
