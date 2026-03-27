# トラブルシューティング

yomitoku使用時によくある問題と解決策。

## インストール関連

### ModuleNotFoundError: yomitoku

```
ModuleNotFoundError: No module named 'yomitoku'
```

**解決策:**
```bash
# uvでインストール（推奨）
brew install uv
uv tool install yomitoku --python 3.13

# または仮想環境
python -m venv ~/.venv/yomitoku
source ~/.venv/yomitoku/bin/activate
pip install yomitoku
```

### PDFInfoNotInstalledError

```
pdf2image.exceptions.PDFInfoNotInstalledError: Unable to get page count. Is poppler installed and in PATH?
```

**解決策:**
```bash
# macOS
brew install poppler

# 確認
which pdfinfo
```

## API関連

### configs must be a dict

```
ValueError: configs must be a dict. See the https://kotaro-kinoshita.github.io/yomitoku-dev/usage/
```

**原因:** yomitoku 0.4.1で`configs`パラメータが必須になった。

**解決策:**
```python
# 旧（エラー）
analyzer = DocumentAnalyzer(device="mps")

# 新（正しい）
analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=False)
```

### AttributeError: 'DocumentAnalyzerSchema' object has no attribute 'to_markdown_text'

```
AttributeError: 'DocumentAnalyzerSchema' object has no attribute 'to_markdown_text'
```

**原因:** `to_markdown_text()`メソッドは存在しない。

**解決策:**
```python
# ファイルに出力してから読み込む
results.to_markdown("output.md", img=img)

# または一時ファイル経由
import tempfile
with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as tmp:
    results.to_markdown(tmp.name, img=img)
    with open(tmp.name, 'r') as f:
        content = f.read()
```

## 実行時エラー

### BrokenPipeError (multiprocessing)

```
BrokenPipeError: [Errno 32] Broken pipe
FileNotFoundError: [Errno 2] No such file or directory: '<stdin>'
```

**原因:** heredoc（`<<EOF`）やstdin経由でPythonスクリプトを実行するとmultiprocessingが失敗する。

**解決策:** スクリプトをファイルとして保存して実行する。

```bash
# NG: heredocで実行
python << 'EOF'
from yomitoku import DocumentAnalyzer
...
EOF

# OK: スクリプトファイルで実行
cat > ocr_script.py << 'EOF'
from yomitoku import DocumentAnalyzer
...
EOF
python ocr_script.py
```

### PDFが0バイト（Dropbox Smart Sync）

```
ValueError: Failed to open the PDF file
Syntax Error: Document stream is empty
```

**原因:** Dropboxの「オンラインのみ」設定でファイルがダウンロードされていない。

**解決策:**
1. Finderでファイルを右クリック
2. 「オフラインアクセスを許可」を選択
3. ダウンロード完了を待つ

```bash
# ファイルサイズ確認
ls -la document.pdf
# 0バイトならダウンロード待ち
```

## MPS関連

### CUDA is not available. Use CPU instead.

```
WARNING - CUDA is not available. Use CPU instead.
```

**原因:** Apple SiliconではCUDAは使用不可。MPSを指定する。

**解決策:**
```python
analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=False)
```

### MPS device not found

**原因:** macOS 12.3未満またはx86_64版Python使用。

**確認:**
```bash
python -c "import platform; print(platform.machine())"
# arm64 と表示されるべき
```

**解決策:**
```bash
# ARM64版Pythonを使用
arch -arm64 brew install python@3.11
```

## 性能問題

### 処理が遅い（45秒以上/ページ）

**確認ポイント:**
1. MPSが正しく使用されているか
2. 環境変数が設定されているか
3. PyTorchのバージョン

```python
import torch
print(f"MPS Available: {torch.backends.mps.is_available()}")
print(f"PyTorch: {torch.__version__}")
```

**最適化:**
```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.7
```

**期待値:** M2 Proで約12秒/ページ（PyTorch 2.9.1 + Python 3.13）

## Extractor関連（v0.11.0）

### yomitoku_extract コマンドが見つからない

**解決策:**
```bash
# extract機能付きでインストール
uv tool install 'yomitoku[extract]' --python 3.13
```

### ルールベースで結果が空になる

**原因1:** `description`にページ内に存在しないテキストを指定している。

> `description`は人間向けの説明文ではなく、**OCRされたページ内のラベル文字列と照合するための検索テキスト**。

**対処:**
```bash
# --prompt-only でOCR結果のテキストとセルIDを確認
yomitoku_extract_with_llm input.jpg -s schema.yaml -m MODEL --prompt-only -d mps

# 確認したセルIDやテキストでスキーマを修正
# 例: description: "合計金額"  → ページ内の「合計金額」ラベルにマッチ
# 例: cell_id: "c15"          → セルID直接指定（最も確実）
```

**原因2:** テーブルに罫線がなく、CellDetectorがセルを検出できない。
- 罫線なしの「見た目テーブル」はルールベースでは検出困難
- → LLMベースを使用する

### LLMサーバー接続エラー

```
ConnectionError: Error communicating with API
```

**原因:** LLMサーバーが起動していない、またはURLが異なる。

**解決策（Ollama - Apple Silicon推奨）:**
```bash
brew services start ollama
ollama pull qwen3:4b
curl http://localhost:11434/v1/models

yomitoku_extract_with_llm input.jpg -s schema.yaml \
  -m qwen3:4b --api-base http://localhost:11434/v1 -d mps
```

**解決策（vLLM - CUDA環境）:**
```bash
vllm serve Qwen/Qwen3-4B-AWQ --quantization awq --dtype float16
curl http://localhost:8000/v1/models
```

### LLM応答のパースエラー（content: null）

```
Expecting value: line 1 column 1 (char 0)
```

**原因1（Apple Silicon）:** vllm-mlx + Qwen3 の組み合わせで、モデル出力が`tool_calls`として
誤パースされ `content: null` になる。

**対処:** Ollamaに切り替える（上記参照）。

**原因2（Ollama + Qwen3）:** Qwen3のthinking modeにより、出力トークンの大半が`reasoning`に
消費され`content`が空になる。デフォルト`--max-tokens 4096`では思考だけで枯渇する。

**対処:**
```bash
# max-tokensを大幅に増やす（8192推奨）
yomitoku_extract_with_llm input.jpg -s schema.yaml -m qwen3:4b \
  --api-base http://localhost:11434/v1 --max-tokens 8192 -d mps
```

> **注意**: thinking modeのため、LLMベース抽出は1ページあたり数分かかることがある。
> ルールベースで十分な場合はそちらを推奨。

**原因3:** LLMがJSON形式で応答しなかった（複雑すぎるスキーマ、トークン不足）。

**対処:**
```bash
# プロンプトを確認（情報量が多すぎないか）
yomitoku_extract_with_llm input.jpg -s schema.yaml -m MODEL --prompt-only

# スキーマを簡素化する（フィールド数を減らす）
# max-tokensを増やす
yomitoku_extract_with_llm input.jpg -s schema.yaml -m MODEL --max-tokens 8192

# temperatureを0にする
yomitoku_extract_with_llm input.jpg -s schema.yaml -m MODEL --temperature 0.0
```

### YAMLスキーマのバリデーションエラー

```
ValidationError: field required
```

**原因:** スキーマYAMLの必須フィールドが不足。

**確認ポイント:**
- `fields:` ルートキーが存在するか
- 各フィールドに `name` と `structure` があるか
- `structure` が `kv` または `table` のいずれかか
- `description` が指定されているか（cell_id/bbox未使用時は必須）

### normalizeのバリデーションエラー

```
ValidationError: Input should be a valid string [type=string_type, input_value=['numeric'], input_type=list]
```

**原因:** `normalize`はリストではなく**文字列**。

**解決策:**
```yaml
# NG: リスト形式
normalize: [numeric]
normalize:
  - numeric

# OK: 文字列
normalize: numeric
normalize: date_jp
normalize: phone_jp
```

### ポート競合（ComfyUI等）

**原因:** ポート8000が他のサービスで使用中。

**対処:**
```bash
# 別ポートを使用
vllm-mlx serve mlx-community/Qwen3-4B-4bit --port 8100
yomitoku_extract_with_llm input.jpg -s schema.yaml -m MODEL --api-base http://localhost:8100/v1
```
