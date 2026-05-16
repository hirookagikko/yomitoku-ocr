# Apple Silicon最適化ガイド

Mac Mini M2 Pro/M4 ProでYomitokuを最適化する設定。

## インストール

```bash
# uvでの隔離インストール(推奨)
brew install uv poppler
uv tool install 'yomitoku[extract]' --python 3.13

# 既存環境のアップグレード
uv tool upgrade yomitoku

# 確認
yomitoku --help | head -5
~/.local/share/uv/tools/yomitoku/bin/python -c "from yomitoku import DocumentAnalyzer; print('OK')"
```

> **注意**: `poppler` は PDF 処理 (pdf2image) に必須。

## バージョン要件 (v0.13.0 想定)

| 項目 | 要件 |
|------|------|
| YomiToku | v0.13.0 以降 |
| PyTorch | 2.6 以降 (pyproject.toml で `torch>=2.6.0, torchvision>=0.21.0`) |
| Python | 3.10〜3.13 |
| macOS | **14.0 以降** (MPS 推論時) |

> macOS 26 (Tahoe) では PyTorch 2.12 が MPS を `is_available()=False` と判定する既知問題がある(`The MPS backend is supported on macOS 14.0+` というエラー文を吐く)。CPU 推論 (`-d cpu --lite`) で動作させるか、PyTorch 側の対応を待つこと。

## 環境変数設定

```bash
# 必須: 未対応操作時のCPUフォールバック
export PYTORCH_ENABLE_MPS_FALLBACK=1
```

### Watermark ratio (オプション・上級者向け)

`PYTORCH_MPS_HIGH_WATERMARK_RATIO` を**単独で**設定すると、PyTorch 2.5+ で
内部の low watermark 計算が破綻し `invalid low watermark ratio` エラーになる
ことがある。設定する場合は **HIGH/LOW を必ずペアで明示**する:

```bash
# 32GB環境の例 (両方ペアで明示)
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.7
export PYTORCH_MPS_LOW_WATERMARK_RATIO=0.6

# 64GB環境の例
# export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.9
# export PYTORCH_MPS_LOW_WATERMARK_RATIO=0.8
```

`load_pdf` が v0.12.1 で遅延レンダリング化されたあとは、PDF 全ページを一度にメモリへ載せる経路でのOOMは消えた。Watermark 設定が効くのは「OCR 推論 (DocumentAnalyzer) のキャッシュ管理を絞り込みたい」場面に限られる。デフォルトで十分動く環境が多い。

Pythonスクリプト内で設定する場合:

```python
import os
os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK', '1')
# 必要なときだけ Watermark を明示する
# os.environ.setdefault('PYTORCH_MPS_HIGH_WATERMARK_RATIO', '0.7')
# os.environ.setdefault('PYTORCH_MPS_LOW_WATERMARK_RATIO', '0.6')
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
| CUDA (RTX 3060) | 約 7 秒 | 最速 |
| **MPS (M2 Pro)** | **約 12 秒** | PyTorch 2.9.1 + Python 3.13 + macOS 14/15 の旧実測値 |
| MPS (macOS 26 + PyTorch 2.12) | 利用不可 | 既知の互換問題 — 下記参照 |
| CPU (`--lite`) | 約 78 秒 | GPU/MPS が使えない環境向け |

> **実測結果 (旧)**: M2 Pro 環境で `--lite` フラグなしで約 12 秒/ページを達成。PyTorch 2.9.1 と Python 3.13 の組み合わせで高速動作を確認。
> **macOS 26 環境**: PyTorch 2.12 では MPS が `available=False` を返すため、`--lite -d cpu` フォールバックとなり 78 秒/ページが現実的なライン。

**MPSの特性**: CUDA に近い速度を実現しつつ、電力効率は 80% 改善。

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
