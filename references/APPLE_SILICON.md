# Apple Silicon最適化ガイド

Mac Mini M2 Pro/M4 ProでYomitokuを最適化する設定。

## インストール

```bash
# uvでの隔離インストール（推奨）
brew install uv poppler
uv tool install yomitoku --python 3.13

# 確認
yomitoku --version
~/.local/share/uv/tools/yomitoku/bin/python -c "from yomitoku import DocumentAnalyzer; print('OK')"
```

> **注意**: `poppler`はPDF処理（pdf2image）に必須。

## 環境変数設定

処理開始前に設定（Pythonスクリプト先頭または.zshrc/.bashrc）:

```bash
# 必須：未対応操作時のCPUフォールバック
export PYTORCH_ENABLE_MPS_FALLBACK=1

# メモリ設定（32GB環境）
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.7  # 上限22GB程度
export PYTORCH_MPS_LOW_WATERMARK_RATIO=0.6   # GC開始閾値

# 64GB環境
# export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.9  # 上限約51GB
# export PYTORCH_MPS_LOW_WATERMARK_RATIO=0.8
```

Pythonスクリプト内で設定:

```python
import os
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'] = '0.7'
os.environ['PYTORCH_MPS_LOW_WATERMARK_RATIO'] = '0.6'
```

## MPS確認スクリプト

```python
import torch
import sys

print(f"Python: {sys.version}")
print(f"PyTorch: {torch.__version__}")
print(f"MPS Built: {torch.backends.mps.is_built()}")
print(f"MPS Available: {torch.backends.mps.is_available()}")

if torch.backends.mps.is_available():
    x = torch.randn(100, 100, device="mps")
    print("MPS Test: OK")
    print(f"Memory: {torch.mps.driver_allocated_memory() / 1e6:.2f} MB")
else:
    print("MPS利用不可 - macOS 12.3以降とARM64 Pythonが必要")
```

## メモリ管理ユーティリティ

```python
import torch

def clear_mps_cache():
    """大規模ドキュメント処理間でMPSキャッシュをクリア"""
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
        torch.mps.synchronize()

def get_mps_memory_info():
    """現在のMPSメモリ使用量を取得"""
    if torch.backends.mps.is_available():
        allocated = torch.mps.driver_allocated_memory()
        return f"MPS使用量: {allocated / 1024**3:.2f} GB"
    return "MPS利用不可"
```

## 性能比較

| 環境 | 1ページ処理時間 | 備考 |
|------|----------------|------|
| CUDA (RTX 3060) | 約7秒 | 最速 |
| **MPS (M2 Pro)** | **約12秒** | 実測値（PyTorch 2.9.1 + Python 3.13） |
| CPU (--lite) | 約78秒 | GPUなし環境向け |

> **実測結果**: M2 Pro環境で`--lite`フラグなしで約12秒/ページを達成。従来の45〜60秒から大幅に改善。PyTorch 2.9.1とPython 3.13の組み合わせで高速動作を確認。

**MPSの特性**: CUDAに近い速度を実現しつつ、電力効率は80%改善。

## 推奨バッチサイズ

| 環境 | 推奨バッチサイズ | 備考 |
|------|------------------|------|
| M2 Pro 32GB | 8ページ | メモリ監視しながら調整 |
| M4 Pro 64GB | 16ページ | 余裕のある処理が可能 |
| 高解像度画像（2000px超） | 1〜2ページ | メモリ集約的 |

## トラブルシューティング

| 問題 | 解決策 |
|------|--------|
| MPS device not found | macOS 12.3以降、ARM64 Python使用 |
| Operation not implemented | `PYTORCH_ENABLE_MPS_FALLBACK=1`設定 |
| Out of memory | バッチサイズ削減、`--lite`使用 |
| 処理が遅い（CPUフォールバック） | 未対応操作が多い場合はCPUモード推奨 |
| `PDFInfoNotInstalledError` | `brew install poppler` |
| `configs must be a dict` | `DocumentAnalyzer(configs={}, device="mps")` |
| `BrokenPipeError` (multiprocessing) | heredoc不可、スクリプトファイルで実行 |

### ARM64 Python確認

```bash
python -c "import platform; print(platform.machine())"
# 出力: arm64
```

`x86_64`と表示される場合はRosetta経由のIntel版Python。ARM64版を再インストール:

```bash
# Homebrewの場合
arch -arm64 brew install python@3.11
```
