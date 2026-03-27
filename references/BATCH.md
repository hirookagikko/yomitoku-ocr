# バッチ処理ワークフロー

ディレクトリ内の複数ファイルを一括処理。

## CLIバッチ処理

```bash
# ディレクトリ内の全ファイルを処理（サブディレクトリ含む）
yomitoku ./documents/ -f md -o ./output -d mps --lite

# 可視化画像も出力
yomitoku ./documents/ -f md -o ./output -v -d mps

# 図表抽出付き
yomitoku ./documents/ -f md -o ./output --figure --figure_letter -d mps
```

## Python APIバッチ処理

```python
import os
import torch
from pathlib import Path
from yomitoku import DocumentAnalyzer
from yomitoku.data.functions import load_pdf, load_image

SUPPORTED = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff'}

def process_directory(input_dir: str, output_dir: str, device: str = "mps"):
    """ディレクトリ内ファイルをバッチ処理"""
    analyzer = DocumentAnalyzer(device=device)
    os.makedirs(output_dir, exist_ok=True)

    input_path = Path(input_dir)
    files = [f for f in input_path.rglob("*") if f.suffix.lower() in SUPPORTED]

    processed = 0
    for file_path in files:
        ext = file_path.suffix.lower()

        # 読み込み
        if ext == '.pdf':
            imgs = load_pdf(str(file_path))
        else:
            imgs = load_image(str(file_path))

        # 処理
        for i, img in enumerate(imgs):
            results, _, _ = analyzer(img)

            output_name = f"{file_path.stem}_page{i}.md"
            output_path = os.path.join(output_dir, output_name)
            results.to_markdown(output_path, img=img)

        # メモリ解放
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()

        processed += 1

    return processed

# 使用例
count = process_directory("./documents", "./output", device="mps")
print(f"処理完了: {count}ファイル")
```

## 大規模バッチ最適化

### 推奨バッチサイズ

| 環境 | バッチサイズ | キャッシュクリア間隔 |
|------|-------------|-------------------|
| M2 Pro 32GB | 8ファイル | 8ファイルごと |
| M4 Pro 64GB | 16ファイル | 16ファイルごと |
| 高解像度（2000px超） | 1-2ファイル | 毎回 |

### メモリ管理付きバッチ処理

```python
BATCH_SIZE = 8  # 32GB環境

for i, file_path in enumerate(files):
    # ... 処理 ...

    if (i + 1) % BATCH_SIZE == 0:
        torch.mps.empty_cache()
        torch.mps.synchronize()
        print(f"キャッシュクリア: {i+1}ファイル処理済み")
```

## 進捗表示付きバッチ

```python
from tqdm import tqdm

files = list(input_path.rglob("*"))
files = [f for f in files if f.suffix.lower() in SUPPORTED]

for file_path in tqdm(files, desc="OCR処理中"):
    # ... 処理 ...
```

## エラーハンドリング

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

failed_files = []

for file_path in files:
    try:
        # ... 処理 ...
    except Exception as e:
        logger.error(f"処理失敗: {file_path} - {e}")
        failed_files.append(file_path)
        continue

if failed_files:
    print(f"失敗したファイル: {len(failed_files)}")
    for f in failed_files:
        print(f"  - {f}")
```
