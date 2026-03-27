# Python API リファレンス

## コアクラス

### DocumentAnalyzer

```python
from yomitoku import DocumentAnalyzer

# yomitoku 0.4.1以降: configs={}が必須パラメータ
analyzer = DocumentAnalyzer(
    configs={},         # 必須（空dictでデフォルト設定使用）
    device="mps",       # "cuda", "cpu", "mps"
    visualize=False     # 可視化出力を有効化
)
```

**パラメータ:**

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|---------|------|
| `configs` | dict | None | **必須**。空dict `{}` でデフォルト設定 |
| `device` | str | "cuda" | デバイス選択 |
| `visualize` | bool | False | 可視化画像を出力 |

> **破壊的変更 (v0.4.1)**: `configs`パラメータが必須になった。旧構文 `DocumentAnalyzer(device="mps")` はエラーになる。

**戻り値（呼び出し時）:**

```python
results, ocr_vis, layout_vis = analyzer(img)
```

| 戻り値 | 型 | 説明 |
|--------|-----|------|
| `results` | DocumentAnalyzerResult | 解析結果オブジェクト |
| `ocr_vis` | ndarray or None | OCR可視化画像 |
| `layout_vis` | ndarray or None | レイアウト可視化画像 |

### DocumentAnalyzerResult

```python
# Markdown出力
results.to_markdown(
    "output.md",
    img=img,                    # 元画像（図表抽出用）
    export_figure=True,         # 図表を出力
    export_figure_letter=False, # 図表内テキストも含める
    ignore_line_break=False,    # 改行を無視
    figure_width=200,           # 図表の幅
    figure_dir="figures"        # 図表の出力ディレクトリ
)

# JSON出力
results.to_json("output.json")

# CSV出力
results.to_csv("output.csv")

# HTML出力
results.to_html("output.html", img=img)
```

**to_markdownパラメータ:**

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|---------|------|
| `out_path` | str | - | 出力ファイルパス |
| `img` | ndarray | None | 元画像（図表抽出用） |
| `export_figure` | bool | True | 図表を出力 |
| `export_figure_letter` | bool | False | 図表内テキストも含める |
| `ignore_line_break` | bool | False | 改行を無視して連結 |
| `figure_width` | int | 200 | 図表の幅 |
| `figure_dir` | str | "figures" | 図表の出力ディレクトリ |

> **注意**: `ignore_meta`（ヘッダー・フッター除外）はCLIのみ対応。Python APIでは利用不可。

## データ読み込み関数

### load_pdf

```python
from yomitoku.data.functions import load_pdf

imgs = load_pdf("document.pdf")
# imgs: List[ndarray] - 各ページの画像リスト
```

### load_image

```python
from yomitoku.data.functions import load_image

imgs = load_image("document.png")
# imgs: List[ndarray] - 単一画像のリスト
```

**対応形式:** `.png`, `.jpg`, `.jpeg`, `.tiff`

## 基本的な使用パターン

### 単一ファイル処理

```python
from yomitoku import DocumentAnalyzer
from yomitoku.data.functions import load_pdf, load_image

# 初期化（configs={}が必須）
analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=False)

# PDF読み込み
imgs = load_pdf("document.pdf")

# 処理・出力
for i, img in enumerate(imgs):
    results, _, _ = analyzer(img)
    results.to_markdown(f"output/page_{i}.md", img=img)
```

### ページ範囲指定（CLIにはない機能）

```python
# 最初の5ページのみ処理
analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=False)
imgs = load_pdf("document.pdf")

for i in range(min(5, len(imgs))):
    results, _, _ = analyzer(imgs[i])
    results.to_markdown(f"output/page_{i+1}.md", img=imgs[i])
```

### 複数ページを1ファイルに統合

```python
import tempfile
import os

analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=False)
imgs = load_pdf("document.pdf")

all_markdown = []
for i, img in enumerate(imgs):
    results, _, _ = analyzer(img)

    # 一時ファイルに書き出して読み込む
    with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as tmp:
        tmp_path = tmp.name
    results.to_markdown(tmp_path, img=img, export_figure=False)
    with open(tmp_path, 'r') as f:
        all_markdown.append(f"## ページ {i+1}\n\n{f.read()}")
    os.unlink(tmp_path)

# 統合ファイル出力
with open("combined.md", "w") as f:
    f.write("\n\n---\n\n".join(all_markdown))
```

### 図表抽出付き

```python
analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=False)

for i, img in enumerate(imgs):
    results, _, _ = analyzer(img)
    results.to_markdown(
        f"output/page_{i}.md",
        img=img,
        export_figure=True,
        export_figure_letter=True
    )
```

### 可視化付き

```python
import cv2

analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=True)

for i, img in enumerate(imgs):
    results, ocr_vis, layout_vis = analyzer(img)

    if ocr_vis is not None:
        cv2.imwrite(f"output/ocr_vis_{i}.png", ocr_vis)
    if layout_vis is not None:
        cv2.imwrite(f"output/layout_vis_{i}.png", layout_vis)
```

## 非同期処理パターン

### FastAPI統合

```python
from starlette.concurrency import run_in_threadpool
from yomitoku import DocumentAnalyzer
from yomitoku.data.functions import load_pdf, load_image
import torch

# グローバル初期化（起動時1回）
analyzer = DocumentAnalyzer(configs={}, device="mps", visualize=False)

async def process_document(file_path: str, output_dir: str):
    ext = file_path.split('.')[-1].lower()

    if ext == "pdf":
        imgs = load_pdf(file_path)
    elif ext in ["jpg", "jpeg", "png", "tiff"]:
        imgs = load_image(file_path)
    else:
        raise ValueError(f"未対応形式: {ext}")

    outputs = []
    for i, img in enumerate(imgs):
        # 同期処理をスレッドプールで実行
        results, _, _ = await run_in_threadpool(analyzer, img)

        output_path = f"{output_dir}/page_{i}.md"
        results.to_markdown(output_path, img=img)
        outputs.append(output_path)

        # メモリ解放
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()

    return outputs
```

## メモリ管理

### キャッシュクリア

```python
import torch

def clear_cache():
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
        torch.mps.synchronize()
```

### バッチ処理でのメモリ管理

```python
BATCH_SIZE = 8

for i, img in enumerate(imgs):
    results, _, _ = analyzer(img)
    results.to_markdown(f"output/page_{i}.md", img=img)

    if (i + 1) % BATCH_SIZE == 0:
        torch.mps.empty_cache()
```

## エラーハンドリング

```python
import logging

logger = logging.getLogger(__name__)

def safe_process(file_path: str):
    try:
        if file_path.endswith('.pdf'):
            imgs = load_pdf(file_path)
        else:
            imgs = load_image(file_path)

        for i, img in enumerate(imgs):
            results, _, _ = analyzer(img)
            results.to_markdown(f"output/page_{i}.md", img=img)

        return True
    except Exception as e:
        logger.error(f"処理失敗: {file_path} - {e}")
        return False
```
