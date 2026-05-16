# Dictionary OCR Post-processor

辞書スキャンPDFのOCR後処理エージェント。YomiToku OCR出力に対して
ルビ崩壊修正（clean）とエラー検出（detect）を実行する。

**通常のOCRパイプライン（ocr-pipeline.md）が先に完了していることが前提。**

## パス規約

`SKILL_DIR` = このファイルの2階層上（SKILL.md が存在するディレクトリ）の絶対パス。

## 前提条件

- YomiToku OCR が **`--dpi 300 --ignore_ruby --ruby_threshold 2.0` 付き**で完了し `pages/*.md` が存在する
- v0.12.0 で OCR 本体に `--ignore_ruby` が入ったので、ルビ削除の主役は OCR 側
- このスクリプトの役割は「OCR で拾いきれなかった残ルビと、既知パターンの最終調整」
- `jamdict` + `jamdict-data` がインストール済み（detect に必要）

### jamdict インストール確認

```bash
python3 -c "from jamdict import Jamdict; print('OK')" 2>&1
```

未インストールの場合:
```bash
pip install jamdict jamdict-data
```

## パイプライン

```
pages/*.md (YomiToku OCR出力, --ignore_ruby 済み)
    ↓
[Step 1] clean_ruby_text.py --dict {辞書名}
    → pages_cleaned/*.md（Stage 1: 既知パターン置換のみ）
    ↓
[Step 2] detect_ruby_errors.py
    → エラー候補レポート（stderr出力）
    ↓
[Step 3] 人間トリアージ
    → KNOWN_FIXES追加 → Step 1 再実行
```

> v0.12.0 以前(`--ignore_ruby` 不在時)の Stage 2/3 汎用 regex 除去は、デフォルトでは無効化された。
> `clean_ruby_text.py --enable-stage2` で旧挙動を有効化できる。
> `--ignore_ruby` で OCR 時に高いリコールでルビが落ちるため、過剰除去のリスクを避けるのが新しい既定。

## パラメータ

| パラメータ | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `output_dir` | Yes | — | OCR出力ディレクトリ（`ocr_output/{書籍名}/`） |
| `dict_name` | No | なし | 辞書名（`data/known_fixes/` 内のファイル名） |

## 手順

### Step 1: ルビ崩壊修正（clean）

```bash
python3 SKILL_DIR/scripts/clean_ruby_text.py \
    "{output_dir}/pages" \
    "{output_dir}/pages_cleaned" \
    --dict {dict_name}
```

- `--dict` 指定時: Stage 1 (既知パターン置換) のみ適用 — `--ignore_ruby` 済み入力前提
- `--dict` 省略 + `--enable-stage2` 指定時: 旧来の汎用 regex (Stage 2/3) で残ルビを掃除する。`--ignore_ruby` を通していない古い OCR 出力を再処理するときに使う
- `--dict` 省略 + `--enable-stage2` なし: 何も置換せず入力をそのままコピーする (ドライランに有用)
- 出力: `{output_dir}/pages_cleaned/*.md`
- 変更行数がstderrに表示される

#### `--ruby_threshold` のチューニング指針

OCR 側 (`yomitoku --ruby_threshold N`) の閾値:
- 実装デフォルト **2.0** (高い: 強い bimodality を要求 → 控えめにルビ除去)
- 辞書スキャンで本文の漢字や小書き文字を巻き込んで消されるケースが目立つなら **2.5 〜 3.0** に上げる
- 逆にルビが残りすぎる場合は **1.5** 程度まで下げる
- README には 0.5 と書かれているが、`yomitoku --help` の実装側ヘルプは 2.0。混乱を避けるため、ocr-pipeline.md は実装に合わせ 2.0 を既定値として扱う

#### スモーク検証で観察された注意点 (2026-05-16, macOS 26 + PyTorch 2.12 + CPU)

「てにをは辞典」の1ページ (p.100) を 3 パターンで OCR し比較した:

| 出力 | 条件 | 文字数 | 観察 |
|------|------|-------|------|
| 旧 v0.11 | DPI 300, `--ignore_ruby` なし | 2100 | `鷹揚おう` `絹介州以` `九帳面決め` `雑談ばい` などルビが本文化 |
| 新 v0.13 (lite) | DPI 200, `--ignore_ruby --ruby_threshold 2.0`, `--lite` | 2098 | `鷹揚げら` `絹介納` `九帳面読い` `雑穀だい` (ルビ残存、認識結果が違うだけ) |
| 新 v0.13 (full) | DPI 300, `--ignore_ruby --ruby_threshold 2.0` | 2102 | `鷹揚げう` `凡帳面があ` `消介が` `雑談なっ` (同上) |

**3 者の文字数差は ±2 文字以内。`--ignore_ruby --ruby_threshold 2.0` はこの辞書スキャンではルビを取れていない**。考えられる原因:

1. **閾値 2.0 が辞書には厳しすぎる**: 辞書本体の文字も小さく、ルビとのサイズ差(bimodality)が弱い → `--ruby_threshold 1.5` 以下まで下げる必要がある
2. **ルビが OCR 段でそもそも検出されず**、本文と同サイズのひらがなとして読まれているなら、`--ignore_ruby` は介入する対象自体がない
3. **`--lite` モードは検出/認識の精度が落ちる**ため、ルビ判定パスを通る前段で読みが揺らぐ

辞書モードの**現状推奨**:
- フル設定でも `--ignore_ruby` だけでは不十分 → `clean_ruby_text.py --dict` (Stage 1) で既知パターンを掃く流れは引き続き有効
- 新環境で再検証する際は `--ruby_threshold 1.0` 〜 `1.5` あたりを試し、本文の誤削除と残ルビのバランスを取る
- MPS が使える環境(macOS 14/15)でフル設定 A/B を再実施し、効く閾値を固めるのが次の宿題

### Step 2: エラー検出（detect）

```bash
python3 SKILL_DIR/scripts/detect_ruby_errors.py \
    "{output_dir}/pages_cleaned" \
    --limit 100
```

- JMDictロードに数秒かかる（初回のみ）
- 出力: MISMATCH / NO_ENTRY のレポート（stdout）
- 精度は低い（てにをは辞典で約5%）— 候補を出して人間がトリアージする想定

### Step 3: 結果報告

以下をユーザーに報告:

1. **clean 結果**: 修正された行数と代表的な修正例
2. **detect 結果**: エラー候補の件数と上位の候補
3. **次のアクション提案**:
   - MISMATCH の中で本物のルビ崩壊があれば `data/known_fixes/{辞書名}.py` に追加
   - 追加後に Step 1 を再実行して検証

### Step 4: 章分割への反映（オプション）

既に `chapters/` が生成されている場合、クリーニング済みページから再構築する:

```bash
python3 SKILL_DIR/scripts/rebuild_chapters.py \
    "{output_dir}" \
    --pages-dir pages_cleaned
```

## 辞書別 KNOWN_FIXES の追加方法

新しい辞書の KNOWN_FIXES を追加するとき:

1. `SKILL_DIR/data/known_fixes/{辞書名}.py` を作成
2. `FIXES = [...]` にタプルリストを定義
3. ページ番号のコメントを入れて追跡可能にする

```python
"""○○辞典 — YomiToku OCR ルビ崩壊の既知修正パターン"""

FIXES = [
    # --- Page N ---
    ('OCR出力', '正しいテキスト'),
]
```

## 既知の制約

- `detect_ruby_errors.py` のコロケーションフィルタは**てにをは辞典向け**。
  語釈中心の辞書（大辞林、広辞苑等）では別のフィルタが必要になる可能性あり
- `っ` は汎用regexから除外（促音と小書きルビの区別不能）
- 行またぎルビ崩壊は KNOWN_FIXES の `\n\n` 付きエントリで個別対応
- 300DPI未満ではルビ文字が濁点・句読点と同サイズ（6-8px）になり誤認率が上がる

## サンドボックス

clean / detect の Python スクリプトはサンドボックス内で動作可能。
jamdict はローカルSQLiteを参照するのみでネットワーク不要。
