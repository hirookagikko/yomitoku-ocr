# OCR Table Extractor

OCR済みのpages/*.mdからテーブルを自動検出し、YAMLスキーマを生成して
YomiToku Extractorで構造化データ(JSON)を抽出する。

**ルールベース抽出(デフォルト)**: LLM不要、~18秒/ページ

## パラメータ

このエージェントは ocr-pipeline.md から呼ばれる。以下のパラメータが渡される:

- `output_dir`: OCR出力ディレクトリ（例: `ocr_output/書籍名/`）
- `pdf_path`: 元PDFファイルパス（Extractor入力用）
- `SKILL_DIR`: スキルルートディレクトリの絶対パス

---

## Phase 1: テーブルスキャン

```bash
python3 SKILL_DIR/scripts/scan_tables.py "{output_dir}"
```

出力JSONを確認:
- `is_table_heavy: false` → **「テーブルが少ないためスキップします」と報告して終了**
- `is_table_heavy: true` → Phase 2へ

スキャン結果をユーザーに報告:
```
テーブルスキャン完了:
- テーブルを含むページ: N ページ
- データ行合計: N 行
- テーブルグループ: N 種類
```

---

## Phase 2: スキーマ自動生成

```bash
python3 SKILL_DIR/scripts/scan_tables.py "{output_dir}" | \
  python3 SKILL_DIR/scripts/generate_schema.py "{output_dir}"
```

出力:
- `{output_dir}/_extractions/schemas/` にYAMLスキーマファイル
- `page_schema_map.json` にページ→スキーマのマッピング

生成されたスキーマを表示してユーザーに確認。

---

## Phase 3: ルールベース抽出

page_schema_map.json の `all_pages` リストから、スキーマごとに対象ページを `--pages` で指定して抽出。

```bash
mkdir -p "{output_dir}/_extractions/json"

yomitoku_extract "{pdf_path}" \
  -s "{output_dir}/_extractions/schemas/{schema_id}.yaml" \
  -o "{output_dir}/_extractions/json" \
  --pages "{ページ番号リスト}" \
  --simple \
  -d mps
```

**重要**:
- 1スキーマずつ順次実行（GPU並列は避ける）
- 失敗してもエラーを記録して次のスキーマに進む（ベストエフォート）

---

## Phase 4: 結果マージ

```bash
mkdir -p "{output_dir}/_extractions/merged"
```

各スキーマの抽出結果JSONを読み込み、同一スキーマの結果を1つのJSONにマージ。

---

## Phase 5: レポート生成

`{output_dir}/_extractions/table_report.json` にサマリーを出力。

完了フラグ:
```bash
touch "{output_dir}/.extract_complete"
```

---

## エラーハンドリング

| 状況 | 対処 |
|------|------|
| テーブルスキャンエラー | エラー報告して終了（パイプライン続行可） |
| スキーマ生成失敗 | エラー報告して終了 |
| 個別ページ抽出失敗 | エラー記録して次のページへ継続 |
| yomitoku_extractが見つからない | `uv tool install 'yomitoku[extract]'` を提案 |

**重要**: このステップの失敗はパイプライン全体を止めない。エラーがあっても報告のみ。
