---
name: yomitoku-ocr
description: |
  YomiTokuでPDF書籍をOCR処理しMarkdownに変換、目次解析・章分割・テーブル抽出まで
  一貫実行するパイプラインスキル。3モード（通常/figure/デュアル）対応。
  Apple Silicon MPS最適化。並列バッチ処理で大規模PDFも高速処理。
  「書籍OCR」「PDF→Markdown」「章分割」「YomiToku」「本のデジタル化」
  「OCRして」「この本をテキスト化」「PDFをMarkdownに」などのキーワードで使用。
  PDFや書籍のOCR処理を依頼されたら、たとえユーザーが明示的にスキル名を言わなくても
  積極的にこのスキルを使うこと。
---

# YomiToku OCR Pipeline

PDF書籍をOCR処理し、目次解析・章分割・テーブル抽出まで一貫実行するパイプライン。

## Quick Start

`agents/ocr-pipeline.md` を Read して、その手順に従って実行する。

```
PDF入力 → OCR (pages/*.md) → テーブル抽出 → 目次解析 → 章分割 (chapters/*.md)
```

## パス規約

本スキル内のすべてのパスは `SKILL_DIR` をプレースホルダーとして使用する。

**SKILL_DIR = このSKILL.mdが存在するディレクトリの絶対パス。**

実行前に解決すること:
```bash
SKILL_DIR="/path/to/yomitoku-ocr"  # このファイルの場所
```

## Prerequisites

| 項目 | 要件 |
|------|------|
| Python | 3.10-3.13（3.14未対応） |
| PyTorch | 2.6以降（pyproject.tomlで `torch>=2.6.0, torchvision>=0.21.0`） |
| YomiToku | v0.13.0以降 |
| macOS | 14.0以降（MPS推論時）。macOS 26 (Tahoe) では PyTorch 2.12 時点で MPS 不可。[TROUBLESHOOTING](references/TROUBLESHOOTING.md#macos-26-tahoe-で-mps-が-available-false-になる) を参照 |
| poppler | `brew install poppler` |
| RAM | 16GB以上（64GB推奨） |
| VRAM | 8GB以上推奨（GPUモード） |

### インストール

```bash
brew install uv poppler

# SOCKS プロキシを経由する環境では httpx[socks] を同梱しないと起動できない
uv tool install 'yomitoku[extract]' --with 'httpx[socks]' --python 3.13

# 既存インストールを最新版に上げる(socks 同梱を保つ)
uv tool install 'yomitoku[extract]' --with 'httpx[socks]' --reinstall --python 3.13
# あるいは
uv tool upgrade yomitoku
```

> **SOCKS proxy について**: `ALL_PROXY=socks5://...` や Cloudflare WARP, Mullvad 等が有効な環境では、yomitoku が HuggingFace Hub に HEAD リクエストを送る段階で `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.` を踏む。上記の `--with 'httpx[socks]'` でこれを回避する。

### モデルキャッシュ

v0.12.0 以降は `download_model` で明示的にプリフェッチできる。**初回は sandbox 外で 1 回実行することを推奨**(sandbox の filesystem 制限で `~/.cache/huggingface/hub/` への書き込みが拒否されるため):

```bash
# ターミナルで直接、または Claude Code 内で `!` プレフィックスで sandbox を抜けて実行
download_model

# 確認: モデルキャッシュが取得されたか
ls ~/.cache/huggingface/hub/ | grep -i yomitoku
```

未実行でも初回 OCR 時に自動ダウンロードを試みるが、sandbox 制限下では `PermissionError: Operation not permitted: ~/.cache/huggingface/hub/...` で失敗する。

### 依存関係チェック

```bash
python3 SKILL_DIR/scripts/check_dependencies.py
```

## パイプライン概要

4つのモードがある:

| モード | いつ使う | 処理内容 |
|--------|---------|---------|
| A. 通常 | デフォルト | OCR → テーブル抽出 → 章分割 |
| B. figure | 図版が必要な本 | OCR(`--figure`) → テーブル抽出 → 章分割 |
| C. デュアル | テキスト+図版両方必要 | 通常OCR + figureOCR → テーブル抽出 → 章分割(2種) |
| D. 辞書 | 辞書・事典類 | OCR(`--dpi 300 --ignore_ruby --ruby_threshold 2.0`) → 残ルビ最終調整 → エラー検出 → 章分割 |

辞書モードは v0.12.0 で追加された `--ignore_ruby` を主、`clean_ruby_text.py` の Stage 1 (既知パターン置換) を補助に降格させた構成。詳細は [agents/ocr-dictionary.md](agents/ocr-dictionary.md)。

## 使い方

1. このSKILL.mdのパスから `SKILL_DIR` を解決する
2. `agents/ocr-pipeline.md` を Read する
3. そこに記載された手順に従ってパイプラインを実行する

パイプラインは人間の介入なしに自動で各ステップを連結する。

## エージェント一覧

| ステップ | エージェント | 役割 |
|----------|------------|------|
| 全体制御 | [ocr-pipeline](agents/ocr-pipeline.md) | パイプライン全体のオーケストレーション |
| OCR実行 | [ocr-book](agents/ocr-book.md) | PDF→ページ単位Markdown変換 |
| テーブル抽出 | [ocr-extract](agents/ocr-extract.md) | テーブルリッチ文書の構造化データ抽出 |
| 目次解析+章分割 | [ocr-toc](agents/ocr-toc.md) | LLMベース目次解析と章分割 |
| 辞書後処理 | [ocr-dictionary](agents/ocr-dictionary.md) | ルビ崩壊修正＋JMDictエラー検出 |

## サンドボックスとセットアップ

YomiToku は初回起動時に HuggingFace Hub からモデル（約630MB）をダウンロードする。
2回目以降はローカルキャッシュを使用するが、起動時に HEAD リクエストを送る仕様がある。

### 初回セットアップ（必須）

**パイプライン実行前にモデルキャッシュを準備する。** ユーザーに以下を実行してもらう:

```bash
# v0.12.0 以降推奨: 明示的にプリフェッチ
download_model

# 旧来の方法: yomitoku --help でもダウンロードがトリガーされる
yomitoku --help
```

または Claude Code 内で `!` プレフィックスを使う:
```
! download_model
```

### サンドボックス内での動作

モデルキャッシュ済みの場合、yomitoku の HEAD リクエストは 404 を受けて正常続行する。
ただしサンドボックスがネットワークをブロックすると `LocalEntryNotFoundError` になる。

**推奨**: サンドボックスの `allowedHosts` に HuggingFace を追加する:
```json
{
  "permissions": {
    "allow": [],
    "deny": []
  },
  "sandbox": {
    "allowedHosts": ["huggingface.co", "*.hf.co"]
  }
}
```

### フォールバック

上記で解決しない場合のみ `dangerouslyDisableSandbox: true` を使用する。
これは全保護を無効化するため最終手段として扱うこと。

- `HF_HUB_OFFLINE=1` は使用禁止（キャッシュ参照にも失敗する）
- `/tmp` 問題は `$TMPDIR` で回避済み（ocr_book.sh が自動処理）

## メモリ制約

v0.12.1 で `load_pdf` が遅延レンダリング化されてから、PDFを丸ごとメモリに載せる経路のOOMは消えた。残るのは **OCR推論時の GPU/MPS メモリ**:

- 1プロセスあたり OCR 推論で約 5-7GB（M2 Pro 32GB / M4 Pro 64GB 共通の実測値）
- 並列上限: 通常モード最大5、figureモード最大1(検出器が大きく単体でVRAMを食う)
- 並列はあくまで「OCR推論のスループット最大化」目的。1プロセス全通しと比較した実測値は [references/BATCH.md](references/BATCH.md) を参照
- ユーザー指示なしにオプションを追加しないこと

## Apple Silicon 環境変数

詳しくは [references/APPLE_SILICON.md](references/APPLE_SILICON.md) を参照。スキル側の既定方針は以下:

```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1
```

- `PYTORCH_MPS_HIGH_WATERMARK_RATIO` / `PYTORCH_MPS_LOW_WATERMARK_RATIO` は**両方ペアで明示する場合のみ**設定する(HIGH のみ単独設定で `invalid low watermark ratio` を踏んだ報告あり)
- macOS 26 (Tahoe) は PyTorch 2.12 時点で MPS が `available=False`。CPU 推論 (`--lite -d cpu`) で動かすか、対応版の PyTorch を待つこと

## 出力構造

```
ocr_output/{書籍名}/
├── README.md              # 目次リンク付きメタ情報
├── chapters/              # 章ごとに統合されたMarkdown
├── pages/                 # ページごとのOCR出力（元データ）
├── figures/               # 図版（figureモード時）
├── _extractions/          # テーブル抽出結果（テーブルリッチ時）
├── chapter_override.json  # 章構成定義
└── .ocr_complete          # OCR完了フラグ
```

## リファレンス一覧

| ドキュメント | 内容 | いつ読むか |
|-------------|------|-----------|
| [API Reference](references/API_REFERENCE.md) | Python API詳細 | カスタムスクリプト作成時 |
| [Apple Silicon](references/APPLE_SILICON.md) | MPS設定・メモリ管理 | Apple Silicon環境の最適化時 |
| [Batch処理](references/BATCH.md) | ディレクトリ一括処理 | 大量ファイル処理時 |
| [CLI Reference](references/CLI_REFERENCE.md) | 全CLIオプション | オプション確認時 |
| [Extractor Reference](references/EXTRACTOR_REFERENCE.md) | YAMLスキーマ詳細 | テーブル抽出のカスタマイズ時 |
| [Extractor Pitfalls](references/EXTRACTOR_PITFALLS.md) | Extractor注意点 | 抽出結果に問題がある時 |
| [Troubleshooting](references/TROUBLESHOOTING.md) | エラー対処法 | エラー発生時 |

## エラーハンドリング

| エラー | 解決策 |
|--------|--------|
| `ModuleNotFoundError: yomitoku` | `uv tool install yomitoku --python 3.13` |
| `PDFInfoNotInstalledError` | `brew install poppler` |
| `LocalEntryNotFoundError` | `dangerouslyDisableSandbox: true` で実行 |
| `The MPS backend is supported on macOS 14.0+` | macOS 26 では PyTorch 2.12 が MPS を未対応扱いする既知問題。CPU 推論にフォールバック |
| MPS device not found | macOS 14.0以降 + ARM64 Python必須 |
| Out of Memory | `--lite`使用、並列数を減らす |
| PDF 0バイト | Dropbox Smart Sync確認、ローカルにダウンロード |

## デバイス別性能

| 環境 | デバイス | 処理時間/ページ |
|------|----------|----------------|
| NVIDIA GPU | cuda | 約7秒 |
| Apple Silicon (M2 Pro) | mps | 約12秒 (PyTorch 2.9.1) — macOS 14/15 で実測 |
| CPU | cpu (--lite) | 約78秒 |

> macOS 26 + PyTorch 2.12 では現状 MPS が使えないため、上記の MPS 行は再現できない。CPU フォールバック (`--lite -d cpu`) で約 78 秒/ページが現実的なライン。
