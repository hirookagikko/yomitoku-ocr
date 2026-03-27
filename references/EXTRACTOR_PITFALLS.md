# Yomitoku Extractor v0.11.0 - つまづきポイントと解決策

Yomitoku Extractor（構造化データ抽出機能）をClaude Codeのエージェントで初めて使った際に
遭遇した問題と、その解決方法をまとめたドキュメントです。

**検証環境**: macOS / Apple Silicon (M2 Pro) / yomitoku 0.11.0 / Ollama + qwen3:4b

---

## 1. `description`の意味を誤解して空結果になる

**症状**: ルールベース抽出が全フィールド空で返ってくる。

**原因**: `description`を人間向けの説明文として書いてしまった。

```yaml
# NG: 人間向けの説明
- name: figure_title
  structure: kv
  description: "図表番号とタイトル"

# OK: ページ内に実在するラベルテキスト
- name: persona_name
  structure: kv
  description: "名前"
```

`description`は**OCRされたページ内のテキストと照合するための検索文字列**です。
ページ内に「名前」というラベルがあれば`description: "名前"`と書きます。

**解決策**: `--prompt-only`で先にOCR結果を確認し、実際のテキストを把握してからスキーマを書く。

```bash
yomitoku_extract_with_llm input.jpg -s schema.yaml -m MODEL --prompt-only -d mps
```

---

## 2. `normalize`をリストで書いてバリデーションエラー

**症状**:
```
ValidationError: Input should be a valid string [type=string_type, input_value=['numeric'], input_type=list]
```

**原因**: `normalize`はリストではなく**文字列型**。

```yaml
# NG
normalize: [numeric]
normalize:
  - numeric

# OK
normalize: numeric
```

---

## 3. vllm-mlx + Qwen3 で `content: null` になる

**症状**:
```
Expecting value: line 1 column 1 (char 0)
```

**原因**: vllm-mlx と Qwen3 の組み合わせで、モデルの出力が`tool_calls`フィールドに
ルーティングされ、`content`が`null`になる。yomitoku は`content`を読むため、JSONパースに失敗する。

**解決策**: Apple Silicon環境では**Ollama**を使う。

```bash
brew install ollama
brew services start ollama
ollama pull qwen3:4b

yomitoku_extract_with_llm input.jpg -s schema.yaml \
  -m qwen3:4b --api-base http://localhost:11434/v1 -d mps
```

---

## 4. Ollama + Qwen3 でも `content` が空になる

**症状**: Ollamaに切り替えても同じ`Expecting value`エラー。

**原因**: Qwen3にはthinking mode（推論モード）があり、出力トークンの大半が
内部の`reasoning`フィールドに消費される。デフォルトの`--max-tokens 4096`では
「考える」だけでトークンが尽きて、肝心のJSONが出力されない。

```json
// Ollama APIの実際のレスポンス
{
  "message": {
    "content": "",           // ← 空！
    "reasoning": "Okay, let me analyze..."  // ← 全トークンここに消費
  }
}
```

**解決策**: `--max-tokens 8192`を指定する。

```bash
yomitoku_extract_with_llm input.jpg -s schema.yaml \
  -m qwen3:4b --api-base http://localhost:11434/v1 \
  --max-tokens 8192 -d mps
```

> ただしthinking modeのため、1ページあたり数分〜10分かかる点に注意。

---

## 5. ポート競合（8000番）

**症状**: LLMサーバーが起動しない、または別のサービスに接続してしまう。

**原因**: ComfyUI等がデフォルトのポート8000を使用中。

**解決策**: 別ポートを指定し、`--api-base`も合わせる。

```bash
# Ollamaはデフォルト11434なので通常問題なし
# vllm-mlxを使う場合
vllm-mlx serve mlx-community/Qwen3-4B-4bit --port 8100
yomitoku_extract_with_llm input.jpg -s schema.yaml \
  -m MODEL --api-base http://localhost:8100/v1
```

---

## 6. ルールベースでテーブルの列が結合される

**症状**: 7列のテーブルなのに、最後の2列（「購入」「アフター購入」）が1つに結合される。

**原因**: ルールベースのグリッドマッチングの限界。罫線やセル構造の認識精度に依存する。

**解決策**: 列の分離が重要な場合は**LLMベース**を使う。LLMベースは文脈を理解して
正しく分離できる（ただし処理時間は大幅に増加）。

---

## 推奨ワークフロー

```
Step 1: --prompt-only でOCRデータを確認
        → セルID、テキスト、テーブル構造が全て見える

Step 2: YAMLスキーマを作成
        → descriptionにはページ内の実テキストを使う
        → 確実性が必要ならcell_idを直接指定

Step 3: ルールベースで抽出（高速・18秒/ページ）
        yomitoku_extract input.jpg -s schema.yaml -d mps --simple

Step 4: 不足があればLLMベースで補完（低速・数分/ページ）
        yomitoku_extract_with_llm input.jpg -s schema.yaml \
          -m qwen3:4b --api-base http://localhost:11434/v1 \
          --max-tokens 8192 -d mps --simple
```

---

## まとめ

| つまづきポイント | 根本原因 | 解決策 |
|:---|:---|:---|
| 全フィールド空 | `description`を説明文と誤解 | ページ内の実テキストを指定 |
| normalize ValidationError | リスト型で記述 | 文字列で記述（`normalize: numeric`） |
| content: null (vllm-mlx) | Qwen3出力がtool_callsに誤ルーティング | Ollamaに切り替え |
| content: null (Ollama) | Qwen3 thinking modeでトークン枯渇 | `--max-tokens 8192` |
| ポート競合 | 8000番が他サービスで使用中 | 別ポート指定 + `--api-base`変更 |
| テーブル列の結合 | ルールベースのグリッド認識限界 | LLMベースで抽出 |
