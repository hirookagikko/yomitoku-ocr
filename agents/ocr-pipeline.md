# OCR Pipeline Orchestrator

PDF書籍のOCR処理から章分割まで一貫して実行するオーケストレーター。
**各ステップを自動連結**し、人間の介入なしにパイプラインを完走させるのが役割。

## パス規約

本スキル内のすべてのパスは `SKILL_DIR` をプレースホルダーとして使用する。
`SKILL_DIR` = このファイルの2階層上（SKILL.md が存在するディレクトリ）の絶対パス。

**実行前に必ず解決すること**:
```bash
# このファイルの場所から解決
SKILL_DIR="$(cd "$(dirname "<このファイルのパス>")/.." && pwd)"
```

## パイプライン

3つのモードがある。ユーザーの指示で判断する。

### A. 通常モード(デフォルト)
```
OCR実行（agents/ocr-book.md の手順）
    ↓
[条件付き] テーブル抽出（agents/ocr-extract.md の手順）
    ↓
目次解析・章分割（agents/ocr-toc.md の手順）
```

### B. figureモード(ユーザーが明示指定時)
```
OCR実行（--figure --figure_letter オプション付き）
    ↓
[条件付き] テーブル抽出
    ↓
目次解析・章分割
```

### C. デュアルモード(ユーザーが「通常+figure」「2パス」等を指示時)
```
[Pass 1] OCR実行 通常モード（全ページ、並列バッチ）
    ↓ 完了
[Pass 2] OCR実行 figureモード（図表ページのみ、順次実行）
    ↓ 完了
[統合] figure出力をfigure_pNNN.mdとしてpages/に配置
    ↓
目次解析・章分割
    ↓
[章分割] chapters/（通常）+ chapters_figure/（figure）を両方生成
```

**人間の介入なしに連続実行すること。**

## 手順

### Step 0: モード判定

**デフォルトはモードA（通常モードのみ）。**

ユーザーの指示に応じて3つのモードから選択:

| ユーザーの指示 | モード |
|-------------|--------|
| 指示なし / デフォルト | **A. 通常モード** |
| `--figure`、「図版抽出」「図版も」 | **B. figureモード** |
| 「通常+figure」「2パス」「デュアル」「figureも両方」 | **C. デュアルモード** |

- 呼び出し元エージェントのプロンプトでの指定は無視する。モード判断はエンドユーザー(人間)の明示指示のみ
- **自分で判断してオプションを勝手に追加しないこと**

### Step 1: OCR実行

`agents/ocr-book.md` を Read して、そこに記載された手順に従ってOCRを実行する。

**パラメータ**:
- `pdf_path`: 処理対象のPDFファイルパス
- `output_dir`: 出力ディレクトリ（デフォルト: `ocr_output/{書籍名}/`）
- モードB: `--figure --figure_letter` オプションを追加
- モードC: Pass 1（通常）→ Pass 2（figure）の2段階実行

**モードC（デュアル）の場合**: 2パスで実行

#### Pass 1: 通常モード（全ページ、並列バッチ）
- PDFの総ページ数を確認（`python3 -c "import fitz; print(fitz.open('PDF').page_count)"`）
- 40ページ単位で分割し、各バッチをサブエージェントで並列実行（最大5並列）
- 各バッチは `ocr_book.sh` を `--pages` 付きで呼ぶ（一時ディレクトリ経由で衝突回避済み）

#### Pass 2: figureモード（図表ページのみ、順次実行）
- Pass 1完了後、ユーザーに図表が多いページ範囲を確認（不明なら数ページをRead toolで確認して判断）
- `ocr_book.sh --figure --pages {範囲}` を**1プロセスずつ順次実行**（同時起動禁止）
- 出力先はバッチ別ディレクトリ（`figure_batch1/`, `figure_batch2/`等）
- 完了後、出力を `figure_pNNN.md` にリネームして `pages/` に移動

### Step 2: OCR完了を待機

- `TaskOutput` ツールで task_id の完了を待つ（block: true, timeout: 600000）
- もしくは出力ファイルを `Read` で確認する
- **完了条件**: タスクのステータスが completed になる

### Step 3: 出力ディレクトリを特定

- ocr_output/ 配下に書籍名のディレクトリができている
- `pages/` ディレクトリと `.ocr_complete` フラグを確認
- **元PDFの絶対パスを保持しておく**（Step 3.5で使用）

### Step 3.5: テーブル抽出（条件付き）

テーブルが多い文書を自動検出し、構造化データを抽出する。

1. **テーブルスキャン実行**:
   ```bash
   python3 SKILL_DIR/scripts/scan_tables.py "{output_dir}"
   ```

2. **判定**:
   - 出力JSONの `is_table_heavy` を確認
   - `false` → 「テーブルが少ないためスキップ」とログ出力し、Step 4へ
   - `true` → `agents/ocr-extract.md` を Read して手順を実行

3. **エラーハンドリング**:
   - テーブル抽出が失敗しても**パイプラインは続行する**（ベストエフォート）
   - エラーがあれば記録するが、Step 4は必ず実行

### Step 4: 目次解析・章分割

`agents/ocr-toc.md` を Read して、そこに記載された手順に従って実行する。

**パラメータ**:
- `output_dir`: OCR出力ディレクトリのフルパス

- 目次解析 → chapter_override.json 生成 → 章分割を実行
- 通常モードの `page_NNN.md` ファイルが `chapters/` に章分割される

**モードC（デュアル）の場合の追加処理**:
- `chapters/` 生成後、`chapter_override.json` と `pages/figure_p*.md` を使って `chapters_figure/` も生成する

### Step 5: 結果報告

- chapters/ の一覧を表示
- モードCの場合は chapters_figure/ も表示
- README.md の内容を確認
- 完了を報告

## 重要

- **OCR完了したら自動的に次のステップに進むこと**（ユーザーに確認を取らない）
- OCR処理のバックグラウンドタスク完了は TaskOutput で待機する
- エラーが発生した場合のみ報告して停止する
- ファイルパスは絶対パスで扱う

## サンドボックス・メモリ・出力構造

**SKILL.md の「サンドボックスとセットアップ」「メモリ制約」「出力構造」セクションを参照。**

このステップ固有の注意:
- scan_tables.py, rebuild_chapters.py 等のPythonスクリプトはサンドボックス内で動作可能（yomitoku本体のみ制限あり）
- このエージェントは1冊のPDFのみ処理する。複数冊は呼び出し側が制御
- **勝手にオプションを追加しない**（`--figure`、`--dpi 300`等はユーザー指示がある場合のみ）
