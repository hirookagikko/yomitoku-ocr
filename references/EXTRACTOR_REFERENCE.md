# Extractor リファレンス（v0.11.0 ベータ）

文書画像/PDFからYAMLスキーマ定義に基づいて構造化データ(JSON)を抽出する機能。

## 方式の選択

| 方式 | コマンド | LLM必要 | 速度 | 向いている文書 |
|------|---------|---------|------|---------------|
| ルールベース | `yomitoku_extract` | 不要 | 高速 | 申請書・帳票・固定レイアウト |
| LLMベース | `yomitoku_extract_with_llm` | 必要 | 中速 | 名刺・レシート・請求書・不定形 |

**判断基準:**
- レイアウトが固定で項目位置が予測可能 → ルールベース
- 文書形式が多様、または自然言語での判断が必要 → LLMベース
- **推奨ワークフロー**: まずLLMベースでプロトタイプ → 抽出パターン確認後、ルールベースに移行

## YAMLスキーマ書式

### 基本構造

```yaml
fields:
  - name: field_name          # フィールド名（出力JSONのキー）【必須】
    structure: kv              # kv（キー・バリュー）or table 【必須】
    description: "検索テキスト" # ページ内のラベル文字列とマッチング【必須】
    type: string               # 省略可。string/number/date/alphanumeric/hiragana/katakana
    normalize: phone_jp        # 省略可。正規化ルール名（文字列）
    regex: "\\d{3}-\\d{4}"    # 省略可。正規表現パターン（scalarのみ）
    cell_id: "c12"             # 省略可。OCRセルIDの直接指定
    bbox: [450, 120, 700, 160] # 省略可。バウンディングボックス [x1, y1, x2, y2]
```

### フィールド位置指定の優先順位

ルールベース抽出では以下の順で値を探索する:

| 優先度 | 方式 | 説明 | 用途 |
|:---:|------|------|------|
| 1 | `cell_id` | OCR解析のセルIDを直接指定（例: `c12`） | 位置が確定している場合 |
| 2 | `bbox` | バウンディングボックス座標 `[x1, y1, x2, y2]`（50%以上重複でマッチ） | 固定レイアウトの座標指定 |
| 3 | `description` | **ページ内のテキストを検索**してマッチング | 一般的な抽出（デフォルト） |
| 4 | `regex` | 正規表現パターンマッチ（scalarフィールドのみ） | 電話番号・日付など |

> **重要**: `description`は人間向けの説明文ではなく、**OCRされたページ内のラベル文字列と照合するための検索テキスト**。
> 例: 請求書の「合計金額」を抽出するなら `description: "合計金額"` とページ内の実テキストを指定する。

### KVフィールドの検索シーケンス（ルールベース）

descriptionを使う場合、以下の順序で値を探索:

1. KV項目のキーテキストと部分一致検索
2. セル内テキストとの部分一致検索
3. 段落テキストとの部分一致検索
4. regexパターンで全要素を横断検索
5. いずれも見つからない場合 → 空文字列を返す

### KV（キー・バリュー）フィールド

単一の値を抽出するフィールド。

```yaml
fields:
  # descriptionでラベル検索（一般的）
  - name: company_name
    structure: kv
    description: "会社名"       # ← ページ内に「会社名」というラベルが必要
    type: string

  # cell_idで直接指定（--prompt-onlyで事前にID確認）
  - name: total
    structure: kv
    cell_id: "c15"
    type: number
    normalize: numeric

  # bboxで座標指定（固定レイアウト向け）
  - name: date
    structure: kv
    bbox: [450, 50, 700, 90]
    type: date
    normalize: date_jp

  # regexで正規表現マッチ
  - name: phone_number
    structure: kv
    description: "電話番号"
    type: string
    normalize: phone_jp
    regex: "\\d{2,4}-?\\d{2,4}-?\\d{4}"

  - name: postal_code
    structure: kv
    description: "郵便番号"
    type: string
    normalize: postal_code_jp
    regex: "\\d{3}-?\\d{4}"
```

### テーブルフィールド

表形式のデータを抽出するフィールド。カラムヘッダーをdescription/cell_id/bboxでマッチングし、対応する行データを抽出。

```yaml
fields:
  - name: invoice_items
    structure: table
    description: "請求明細テーブル"
    columns:
      - name: item_name
        description: "品目"        # ← テーブルヘッダーの「品目」を検索
        type: string
      - name: quantity
        description: "数量"
        type: number
        normalize: numeric
      - name: unit_price
        description: "単価"
        type: number
        normalize: numeric
      - name: amount
        description: "金額"
        type: number
        normalize: numeric
```

### フィールドタイプ

| type | 説明 | 例 |
|------|------|-----|
| `string` | テキスト（デフォルト） | "山田太郎" |
| `number` | 数値 | 12345 |
| `date` | 日付 | "2024-01-15" |
| `alphanumeric` | 英数字のみ | "ABC123" |
| `hiragana` | ひらがな | "やまだたろう" |
| `katakana` | カタカナ | "ヤマダタロウ" |

## 正規化ルール一覧

| ルール名 | 説明 | 入力例 | 出力例 |
|----------|------|--------|--------|
| `phone_jp` | 日本の電話番号フォーマット | "０３ー１２３４ー５６７８" | "03-1234-5678" |
| `postal_code_jp` | 日本の郵便番号 | "１２３ー４５６７" | "123-4567" |
| `date_jp` | 日本語日付→ISO形式 | "令和6年1月15日" | "2024-01-15" |
| `date_yyyymmdd` | 年月日→ISO形式 | "2024年01月15日" | "2024-01-15" |
| `time_jp` | 日本語時刻 | "１４時３０分" | "14:30" |
| `time_hms` | 時分秒 | "14時30分00秒" | "14:30:00" |
| `numeric` | 数値のみ抽出 | "1,234円" | "1234" |
| `alphanumeric` | 英数字のみ | "ABC-123" | "ABC123" |
| `strip_spaces` | 空白除去 | "山 田  太 郎" | "山田太郎" |
| `hiragana` | カタカナ→ひらがな | "ヤマダ" | "やまだ" |
| `katakana` | ひらがな→カタカナ | "やまだ" | "ヤマダ" |
| `fullwidth_to_halfwidth` | 全角→半角変換 | "１２３ＡＢＣ" | "123ABC" |

> 日本語の和暦日付（令和/R・平成/H・昭和/S・大正/T・明治/M）に対応。

## CLI オプション一覧

### ルールベース: `yomitoku_extract`

```bash
yomitoku_extract <input> -s schema.yaml [options]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `-s/--schema` | YAMLスキーマファイル【必須】 | - |
| `-o/--outdir` | 出力ディレクトリ | `results` |
| `-d/--device` | `cuda` / `cpu` / `mps` | `cuda` |
| `-v/--vis` | 可視化画像を生成 | off |
| `--simple` | メタデータなし簡易出力 | off |
| `--pages` | 処理ページ指定（例: `1,3-5`） | 全ページ |

### LLMベース: `yomitoku_extract_with_llm`

```bash
yomitoku_extract_with_llm <input> -s schema.yaml -m <model_name> [options]
```

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `-s/--schema` | YAMLスキーマファイル【必須】 | - |
| `-m/--model` | LLMモデル名【必須】 | - |
| `--api-base` | LLMサーバーURL | `http://localhost:8000/v1` |
| `--temperature` | 生成温度 | `0.0` |
| `--max-tokens` | 最大トークン数 | `4096` |
| `--prompt-only` | プロンプト確認のみ（実行なし） | off |
| `-o/--outdir` | 出力ディレクトリ | `results` |
| `-d/--device` | `cuda` / `cpu` / `mps` | `cuda` |
| `-v/--vis` | 可視化画像を生成 | off |
| `--simple` | メタデータなし簡易出力 | off |
| `--pages` | 処理ページ指定（例: `1,3-5`） | 全ページ |

## LLM推論環境セットアップ

### 公式推奨: vLLM + Qwen3-4B-AWQ（CUDA環境）

```bash
pip install "yomitoku[extract]"

vllm serve Qwen/Qwen3-4B-AWQ \
  --host 0.0.0.0 --port 8000 \
  --quantization awq --dtype float16 \
  --max-model-len 8192 --gpu-memory-utilization 0.5
```

### 推奨モデル

| モデル | VRAM | 備考 |
|--------|------|------|
| **Qwen/Qwen3-4B-AWQ** | ~8GB | AWQ量子化。低VRAM+高精度。推奨 |
| Qwen/Qwen3-4B | ~15GB | 非量子化。最高精度 |
| Qwen/Qwen3-1.7B | 5-7GB | 軽量。精度は限定的 |

> 全モデル Apache 2.0 ライセンス（商用利用可）

### Apple Silicon（MPS）環境

Apple SiliconではCUDA版vLLMが使えないため、代替手段を使用:

#### 方式1: Ollama（推奨・安定）

```bash
brew install ollama
brew services start ollama
ollama pull qwen3:4b

yomitoku_extract_with_llm input.jpg -s schema.yaml \
  -m qwen3:4b \
  --api-base http://localhost:11434/v1 -d mps
```

#### 方式2: vllm-mlx

```bash
uv tool install git+https://github.com/waybarrios/vllm-mlx.git
vllm-mlx serve mlx-community/Qwen3-4B-4bit --port 8100
```

> **既知の問題（2026-02時点）**: vllm-mlx + Qwen3 の組み合わせで、モデル出力が
> `tool_calls`として誤パースされ `content: null` になる場合がある。
> この問題が発生する場合は Ollama を使用すること。
>
> **ポート競合**: ComfyUI等がポート8000を使用している場合は `--port 8100` を指定し、
> `--api-base http://localhost:8100/v1` に合わせて変更する。

### メモリ見積もり（M2 Pro 32GB）

| コンポーネント | メモリ使用量 |
|---------------|-----------|
| Qwen3-4B (4bit) | ~3GB |
| Yomitoku OCR (MPS) | ~4-6GB |
| 同時利用合計 | ~7-9GB（十分余裕あり） |

## 出力形式

### 通常出力（デフォルト）

KVフィールド:
```json
{
  "name": "company_name",
  "value": "株式会社サンプル",
  "raw_text": "株式会社 サンプル",
  "confidence": "high",
  "source": "kv",
  "cell_ids": ["c43"],
  "bboxes": [[450, 120, 700, 160]]
}
```

テーブルフィールド: `records`配列に行ごとのセルメタデータ付き。

### 簡易出力（--simple）

`{フィールド名: 値}` のシンプルなJSON:

```json
{
  "company_name": "株式会社サンプル",
  "phone_number": "03-1234-5678",
  "items": [
    {"description": "商品A", "quantity": 10, "unit_price": 1000, "amount": 10000}
  ]
}
```

> `--simple` でも正規化(normalize)は適用される。

### 可視化ファイル（--vis）

| ファイル | 内容 |
|---------|------|
| `*_layout.jpg` | レイアウト解析結果 |
| `*_ocr.jpg` | OCR認識結果 |
| `*_extract_vis.jpg` | 抽出フィールドのハイライト（confidence別の濃淡） |

## デバッグ

```bash
# 1. まず --prompt-only でOCR結果とセルIDを確認
yomitoku_extract_with_llm input.jpg -s schema.yaml -m MODEL --prompt-only -d mps

# 2. 可視化でレイアウト検出状況を確認
yomitoku_extract input.jpg -s schema.yaml -v -d mps

# 3. セルIDが分かったらスキーマに cell_id を追加して精度向上
```

## 完全なスキーマ例

### 請求書スキーマ

```yaml
fields:
  - name: invoice_number
    structure: kv
    description: "請求書番号"
    type: alphanumeric

  - name: invoice_date
    structure: kv
    description: "請求日"
    type: date
    normalize: date_jp

  - name: company_name
    structure: kv
    description: "請求先"
    type: string

  - name: total_amount
    structure: kv
    description: "合計金額"
    type: number
    normalize: numeric

  - name: items
    structure: table
    description: "明細"
    columns:
      - name: description
        description: "品名"
      - name: quantity
        description: "数量"
        type: number
        normalize: numeric
      - name: unit_price
        description: "単価"
        type: number
        normalize: numeric
      - name: amount
        description: "金額"
        type: number
        normalize: numeric
```

### 名刺スキーマ（LLMベース向け）

```yaml
fields:
  - name: person_name
    structure: kv
    description: "氏名"
    type: string

  - name: company
    structure: kv
    description: "会社名"
    type: string

  - name: title
    structure: kv
    description: "役職"
    type: string

  - name: phone
    structure: kv
    description: "TEL"
    type: string
    normalize: phone_jp

  - name: email
    structure: kv
    description: "E-mail"
    type: string

  - name: address
    structure: kv
    description: "住所"
    type: string
```
