#!/usr/bin/env python3
"""
generate_schema.py - scan_tables.py出力からYAMLスキーマを自動生成

scan_tables.pyのJSON出力を受け取り、各テーブルグループに対して
Yomitoku Extractor用のYAMLスキーマファイルを生成する。

Usage:
    python3 scan_tables.py /path/to/ocr_output/bookname/ | python3 generate_schema.py /path/to/ocr_output/bookname/
    # OR
    python3 generate_schema.py /path/to/ocr_output/bookname/ < scan_result.json

Output:
    {output_dir}/_extractions/schemas/schema_001.yaml
    {output_dir}/_extractions/schemas/schema_002.yaml
    {output_dir}/_extractions/schemas/page_schema_map.json

    stdout: page_schema_map.json の内容
"""

import json
import re
import sys
from pathlib import Path


def sanitize_field_name(text: str) -> str:
    """テキストをYAMLフィールド名に変換"""
    # 記号をアンダースコアに変換
    name = re.sub(r'[/\s、,・\-\.\(\)（）]', '_', text)
    # 連続アンダースコアを1つに
    name = re.sub(r'_+', '_', name)
    # 先頭・末尾のアンダースコアを除去
    name = name.strip('_')
    # 空なら col_N
    if not name:
        return 'col'
    return name


def generate_yaml_schema(group: dict, schema_id: str) -> str:
    """テーブルグループからYAMLスキーマを生成"""
    header = group['header']
    col_count = group['column_count']

    lines = ['fields:']

    if col_count <= 2 and len(header) >= 1:
        # 2カラム → KV型: 最初のカラムがキー、2番目がバリュー
        lines.append(f'  - name: {schema_id}_kv')
        lines.append('    structure: kv')
        desc = header[0] if header else 'value'
        lines.append(f'    description: "{desc}"')
        lines.append('    type: string')
    else:
        # 3カラム以上 → table型
        lines.append(f'  - name: {schema_id}')
        lines.append('    structure: table')

        # テーブル全体のdescription = 最初のヘッダーセル（テーブル名的なもの）
        table_desc = header[0] if header else schema_id
        lines.append(f'    description: "{table_desc}"')
        lines.append('    columns:')

        # 2番目以降のヘッダーがカラム定義
        cols = header[1:] if len(header) > 1 else header
        if not cols:
            # ヘッダーがない場合はカラム番号で
            for i in range(col_count):
                lines.append(f'      - name: col_{i+1}')
                lines.append(f'        description: "column {i+1}"')
        else:
            for col_text in cols:
                field_name = f'col_{sanitize_field_name(col_text)}'
                lines.append(f'      - name: {field_name}')
                lines.append(f'        description: "{col_text}"')

    return '\n'.join(lines) + '\n'


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_schema.py <ocr_output_dir> < scan_result.json",
              file=sys.stderr)
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    schemas_dir = output_dir / '_extractions' / 'schemas'
    schemas_dir.mkdir(parents=True, exist_ok=True)

    # stdinからscan_tables.pyの出力を読む
    scan_data = json.load(sys.stdin)

    if not scan_data.get('is_table_heavy'):
        result = {
            'skipped': True,
            'reason': 'Not table-heavy',
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    table_groups = scan_data.get('table_groups', [])
    pages_info = scan_data.get('pages', {})

    if not table_groups:
        result = {
            'skipped': True,
            'reason': 'No table groups found',
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 各グループにスキーマを生成
    schema_files = {}
    page_schema_map = {}

    for idx, group in enumerate(table_groups):
        schema_id = f'table_{idx+1:03d}'
        schema_content = generate_yaml_schema(group, schema_id)

        schema_path = schemas_dir / f'{schema_id}.yaml'
        schema_path.write_text(schema_content, encoding='utf-8')

        schema_files[schema_id] = {
            'file': str(schema_path),
            'header': group['header'],
            'header_hash': group['header_hash'],
            'pages': group['pages'],
            'total_data_rows': group['total_data_rows'],
        }

        # ページ→スキーマのマッピング
        for page_num in group['pages']:
            page_key = str(page_num)
            if page_key not in page_schema_map:
                page_schema_map[page_key] = []
            page_schema_map[page_key].append({
                'schema_id': schema_id,
                'schema_file': str(schema_path),
            })

    # page_schema_map.json を保存
    map_path = schemas_dir / 'page_schema_map.json'
    map_data = {
        'schemas': schema_files,
        'page_to_schemas': page_schema_map,
        'all_pages': sorted(set(int(p) for p in page_schema_map.keys())),
    }
    map_path.write_text(json.dumps(map_data, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(map_data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
