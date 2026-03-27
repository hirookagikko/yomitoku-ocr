# OCR Book Processor

YomiToku OCRを使用してPDFをOCR処理し、pages/ にMarkdownを出力する。

**OCRのみ実行**: 章分割は ocr-toc.md で別途実行。

**基本オプション**: `--ignore_meta --ignore_line_break -d mps`

**追加オプション（ocr_book.shの第3引数以降で指定）**:
- `--figure` : 図版を画像として抽出（figures/配下に保存）
- `--figure_letter` : 図版内テキストも含める
- `--dpi <N>` : PDF読み込みDPI（デフォルト200、高精度には300）
- `--reading_order <mode>` : 読み順（auto/right2left/left2right/top2bottom）
- `--pages <spec>` : 処理するページ指定（例: 1-40, 41-80）。並列バッチ実行時に使用
- `-v` : 可視化画像を出力（レイアウト検出の診断用）

## パラメータ

このエージェントは ocr-pipeline.md から呼ばれる。以下のパラメータが渡される:

- `pdf_path`: 処理対象のPDFファイルパス（絶対パス）
- `output_dir`: 出力ディレクトリ（デフォルト: `ocr_output/{書籍名}/`）
- `options`: 追加オプション（--figure 等）
- `SKILL_DIR`: スキルルートディレクトリの絶対パス

---

## Phase 1: ファイル選択

パラメータが指定されている場合はそのファイル/ディレクトリを使用。
指定がない場合は対話的に選択。

### 対応入力形式

| タイプ | 例 | 説明 |
|--------|-----|------|
| PDF | `書籍名.pdf` | 単一PDFファイル |
| 画像ディレクトリ | `書籍名/` | png, jpg, jpeg, tiff を含むフォルダ |

### 処理手順

1. **入力ソースを検索**（サブフォルダ含む再帰検索）
2. **一覧を表示**（テーブル形式）
3. **ユーザーに選択を促す**（AskUserQuestion使用）

---

## Phase 2: OCR処理（バックグラウンド）

選択されたPDFをバックグラウンドでOCR処理。

### 単一PDF処理

```bash
# 基本（テキストのみ）
SKILL_DIR/scripts/ocr_book.sh "{pdf_path}" "{output_dir}"

# 図版抽出モード
SKILL_DIR/scripts/ocr_book.sh "{pdf_path}" "{output_dir}" --figure --figure_letter

# 高精度モード
SKILL_DIR/scripts/ocr_book.sh "{pdf_path}" "{output_dir}" --dpi 300 --reading_order right2left
```

### 並列バッチ処理（1つのPDFを分割）

```bash
# 160ページのPDFを4バッチに分割して並列処理
# --pages 指定時は一時ディレクトリ経由でリネームされるため衝突しない
SKILL_DIR/scripts/ocr_book.sh "{pdf}" "{output_dir}" --pages 1-40 &
SKILL_DIR/scripts/ocr_book.sh "{pdf}" "{output_dir}" --pages 41-80 &
SKILL_DIR/scripts/ocr_book.sh "{pdf}" "{output_dir}" --pages 81-120 &
SKILL_DIR/scripts/ocr_book.sh "{pdf}" "{output_dir}" --pages 121-160 &
wait
```

### デュアルモード（通常 + figure 2パス）

**いつ使うか**: 2段組+アイコン、写真入り見本、スペック表など、テキストだけでは情報が欠落する本

**手順**:

1. **通常モード**: 全ページを並列バッチでOCR（最大5並列）
2. **figureモード**: 図表が多いページ範囲を選んで順次OCR（最大1プロセス）
3. **統合**: 通常モード出力を`chapters/`に、figureモード出力を`chapters_figure/`に章分割

### 複数PDF一括処理

```bash
# 各PDFを順次処理（並列実行は避ける - GPUメモリ制約）
for pdf in "${selected_pdfs[@]}"; do
    SKILL_DIR/scripts/ocr_book.sh "$pdf" "ocr_output/$(basename "$pdf" .pdf)"
done
```

---

## 出力

`pages/` にページ単位の Markdown、`figures/` に図版（--figure時）、`.ocr_complete` フラグ。
詳細は SKILL.md の「出力構造」参照。

## サンドボックス・エラー

**SKILL.md の「サンドボックスとセットアップ」セクションを参照。**

このステップ固有のエラー:

| エラー | 対処 |
|--------|------|
| PDF 0バイト | 「Dropboxで同期してください」と通知、スキップ |
| OCR失敗 | エラーログ表示、次のPDFへ継続 |
