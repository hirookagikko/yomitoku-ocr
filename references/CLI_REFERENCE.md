# CLI完全リファレンス

## 基本構文

```bash
yomitoku <path_data> [OPTIONS]
```

`<path_data>`: 画像ファイルまたはディレクトリパス（サブディレクトリ含む）

## 全オプション一覧

### 出力関連

| オプション | 説明 | 例 |
|------------|------|-----|
| `-f, --format` | 出力形式: `json`, `csv`, `html`, `md`, `pdf` (searchable) | `-f md` |
| `-o, --outdir` | 出力ディレクトリ(存在しない場合は作成) | `-o results` |
| `--encoding` | エンコーディング: `utf-8`, `utf-8-sig`, `shift-jis`, `euc-jp`, `cp932` | `--encoding utf-8` |
| `--combine` | 複数ページPDFの結果を1ファイルにまとめる | `--combine` |
| `--pdf_quality` | Searchable-PDF の画質プリセット `high`/`middle`/`low` (v0.12.1+) | `--pdf_quality middle` |
| `--font_path` | Searchable-PDF 用フォント (.ttf) | `--font_path /Library/Fonts/Hiragino.ttc` |

### デバイス・モデル

| オプション | 説明 | 例 |
|------------|------|-----|
| `-d, --device` | デバイス選択: `cuda`, `cpu`, `mps` | `-d mps` |
| `-l, --lite` | 軽量モデル使用(CPU推論高速化、精度やや低下) | `--lite` |
| `--tr_name` | 認識モデル名指定 (デフォルト: `parseq-large-v4_1`, v0.13.0 強化版) | `--tr_name parseq-large-v4_1` |
| `--td_name` | 検出モデル名指定 (デフォルト: `dbnetv2_1`, v0.13.0 強化版) | `--td_name dbnetv2_1` |

### 可視化

| オプション | 説明 | 例 |
|------------|------|-----|
| `-v, --vis` | 解析結果の可視化画像を出力 | `-v` |

### 図表処理

| オプション | 説明 | 例 |
|------------|------|-----|
| `--figure` | 検出した図表・画像を出力（HTML/Markdown専用） | `--figure` |
| `--figure_letter` | 図表内のテキストも出力に含める | `--figure_letter` |
| `--figure_width` | 出力する図表の幅指定 | `--figure_width 800` |
| `--figure_dir` | 図表の出力先ディレクトリ | `--figure_dir figures` |

### コンテンツ制御

| オプション | 説明 | 例 |
|------------|------|-----|
| `--ignore_line_break` | 段落テキストを連結(画像内の改行を無視) | `--ignore_line_break` |
| `--ignore_meta` | ヘッダー・フッターを出力から除外 | `--ignore_meta` |
| `--ignore_ruby` | ふりがな(ルビ)テキストを出力から除外 (v0.12.0+) | `--ignore_ruby` |
| `--ruby_threshold` | ルビ判定の bimodality 閾値(実装デフォルト **2.0**。高いほど valley split に強い bimodality を要求 = 控えめにルビ除去) | `--ruby_threshold 2.5` |
| `--reading_order` | 読み順指定: `auto`, `left2right`, `top2bottom`, `right2left` | `--reading_order auto` |
| `--enable-rec-orientation-fallback` | 認識時の回転テキストフォールバックを有効化 (v0.12.1 で既定 off) | `--enable-rec-orientation-fallback` |
| `--rec-orientation-fallback-thresh` | フォールバック信頼度閾値 (デフォルト 0.75) | `--rec-orientation-fallback-thresh 0.7` |

### PDF処理

| オプション | 説明 | 例 |
|------------|------|-----|
| `--dpi` | PDF読み込み時のDPI(デフォルト: 200) | `--dpi 300` |
| `--pages` | 処理するページ指定(1始まり) | `--pages 1,2,5-10` |

> README には `--ruby_threshold` のデフォルトが 0.5 と書かれているが、`yomitoku --help` の実装側ヘルプは **2.0** を出力する。スキルとしては実装側 (2.0) を採用する。

### 設定ファイル

| オプション | 説明 | 例 |
|------------|------|-----|
| `--td_cfg` | テキスト検出器設定ファイルパス | `--td_cfg config/td.yaml` |
| `--tr_cfg` | テキスト認識器設定ファイルパス | `--tr_cfg config/tr.yaml` |
| `--lp_cfg` | レイアウト解析器設定ファイルパス | `--lp_cfg config/lp.yaml` |
| `--tsr_cfg` | 表構造認識器設定ファイルパス | `--tsr_cfg config/tsr.yaml` |

## ユースケース別コマンド例

### 基本変換

```bash
# Apple Silicon基本
yomitoku ./document.pdf -f md -o results -d mps --lite

# NVIDIA GPU
yomitoku ./document.pdf -f md -o results -d cuda

# CPU
yomitoku ./document.pdf -f md -o results -d cpu --lite
```

### 複数ページPDF

```bash
# 各ページを個別ファイルに
yomitoku ./book.pdf -f md -o results -d mps

# 1つのMarkdownにまとめる
yomitoku ./book.pdf -f md -o results --combine -d mps
```

### 図表抽出

```bash
# 図表を抽出
yomitoku ./document.pdf -f md -o results --figure -d mps

# 図表内テキストも含める
yomitoku ./document.pdf -f md -o results --figure --figure_letter -d mps

# 図表の幅を指定
yomitoku ./document.pdf -f md -o results --figure --figure_width 800 -d mps
```

### クリーンな出力

```bash
# ヘッダー・フッター除外
yomitoku ./document.pdf -f md -o results --ignore_meta -d mps

# 改行を無視（段落を連結）
yomitoku ./document.pdf -f md -o results --ignore_line_break -d mps
```

### バッチ処理

```bash
# ディレクトリ内の全ファイル
yomitoku ./documents/ -f md -o results -d mps --lite

# 可視化付き
yomitoku ./documents/ -f md -o results -v -d mps
```

### 出力形式

```bash
# JSON出力
yomitoku ./document.pdf -f json -o results -d mps

# CSV出力
yomitoku ./document.pdf -f csv -o results -d mps

# HTML出力
yomitoku ./document.pdf -f html -o results -d mps

# 検索可能PDF出力
yomitoku ./document.pdf -f pdf -o results -d mps
```

### デバッグ・検証

```bash
# 可視化出力で解析結果を確認
yomitoku ./document.pdf -f md -o results -v -d mps

# 出力ディレクトリに可視化画像が生成される
```

---

## ルビ除去のユースケース

```bash
# 辞書スキャン書籍を高 DPI + ルビ除去で OCR (推奨)
yomitoku ./dictionary.pdf -f md -o out --dpi 300 \
  --ignore_ruby --ruby_threshold 2.0 -d mps

# ルビが残りすぎる場合は閾値を下げる
yomitoku ./book.pdf -f md -o out --ignore_ruby --ruby_threshold 1.5 -d mps

# 本文が誤削除される場合は閾値を上げる(より厳しく bimodality を要求)
yomitoku ./book.pdf -f md -o out --ignore_ruby --ruby_threshold 3.0 -d mps
```

## モデル一覧 (v0.13.0)

- 認識モデル: `parseq-large-v4_1` (v0.13.0 で精度向上)
- 検出モデル: `dbnetv2_1` (v0.13.0 で精度向上)
- 通常は `--tr_name` / `--td_name` を明示する必要なし。差し替えたいときのみ指定。

---

## yomitoku_extract(ルールベース抽出)

v0.11.0 で導入、v0.12.1 で Key 複数値マージオプション追加。YAMLスキーマ定義に基づき、LLMなしで構造化データを抽出する。

### 基本構文

```bash
yomitoku_extract <input> -s <schema.yaml> [OPTIONS]
```

`<input>`: 画像ファイル、PDFパス、またはディレクトリ

### 全オプション一覧

| オプション | 説明 | デフォルト | 例 |
|------------|------|-----------|-----|
| `-s, --schema` | 抽出スキーマファイル（YAML）**必須** | - | `-s schema.yaml` |
| `-o, --outdir` | 出力ディレクトリ | `results` | `-o output` |
| `-d, --device` | デバイス（TableSemanticParser用） | `cuda` | `-d mps` |
| `-v, --vis` | 可視化画像を出力 | - | `-v` |
| `--no-normalize` | テキスト正規化をスキップ | - | `--no-normalize` |
| `--simple` | 簡易出力（bbox/メタデータなし） | - | `--simple` |
| `--pages` | 処理ページ指定 | 全ページ | `--pages 1,2,5-10` |
| `--dpi` | PDF読み込みDPI | `200` | `--dpi 300` |
| `--encoding` | 出力エンコーディング | `utf-8` | `--encoding utf-8-sig` |

### ユースケース

```bash
# 申請書から構造化データ抽出
yomitoku_extract ./application.jpg -s application_schema.yaml -d mps

# 簡易JSON出力（名前:値のみ）
yomitoku_extract ./invoice.pdf -s invoice_schema.yaml --simple -d mps

# 特定ページのみ処理
yomitoku_extract ./document.pdf -s schema.yaml --pages 1,3 -d mps

# 正規化なしで生テキスト取得
yomitoku_extract ./form.jpg -s schema.yaml --no-normalize -d mps
```

---

## yomitoku_extract_with_llm（LLMベース抽出）

v0.11.0で追加。OpenAI互換APIを通じてLLMと連携し、柔軟な構造化データ抽出を行う。

### 基本構文

```bash
yomitoku_extract_with_llm <input> -s <schema.yaml> -m <model> [OPTIONS]
```

### 全オプション一覧

| オプション | 説明 | デフォルト | 例 |
|------------|------|-----------|-----|
| `-s, --schema` | 抽出スキーマファイル（YAML）**必須** | - | `-s schema.yaml` |
| `-m, --model` | LLMモデル名 **必須** | - | `-m mlx-community/Qwen3-4B-4bit` |
| `--api-base` | API ベースURL | `http://localhost:8000/v1` | `--api-base http://localhost:8000/v1` |
| `--api-key` | APIキー | 空文字列 | `--api-key sk-xxx` |
| `-o, --outdir` | 出力ディレクトリ | `results` | `-o output` |
| `-d, --device` | デバイス（TableSemanticParser用） | `cuda` | `-d mps` |
| `-v, --vis` | 可視化画像を出力 | - | `-v` |
| `--table-id` | 特定テーブルのみ抽出 | - | `--table-id t0` |
| `--temperature` | LLM温度パラメータ | `0.0` | `--temperature 0.1` |
| `--max-tokens` | LLM最大トークン数 | `4096` | `--max-tokens 8192` |
| `--no-normalize` | テキスト正規化をスキップ | - | `--no-normalize` |
| `--simple` | 簡易出力（bbox/メタデータなし） | - | `--simple` |
| `--prompt-only` | プロンプトを表示して終了（デバッグ用） | - | `--prompt-only` |
| `--pages` | 処理ページ指定 | 全ページ | `--pages 1,2,5-10` |
| `--dpi` | PDF読み込みDPI | `200` | `--dpi 300` |
| `--encoding` | 出力エンコーディング | `utf-8` | `--encoding utf-8-sig` |

### ユースケース

```bash
# vllm-mlxとQwen3-4Bで抽出
yomitoku_extract_with_llm ./receipt.jpg -s receipt_schema.yaml \
  -m mlx-community/Qwen3-4B-4bit \
  --api-base http://localhost:8000/v1 -d mps

# プロンプト確認（実行せず）
yomitoku_extract_with_llm ./receipt.jpg -s receipt_schema.yaml \
  -m mlx-community/Qwen3-4B-4bit --prompt-only

# 特定テーブルのみ抽出
yomitoku_extract_with_llm ./invoice.pdf -s schema.yaml \
  -m mlx-community/Qwen3-4B-4bit --table-id t0 -d mps

# 温度・トークン数調整
yomitoku_extract_with_llm ./document.pdf -s schema.yaml \
  -m mlx-community/Qwen3-4B-4bit \
  --temperature 0.1 --max-tokens 8192 -d mps
```
