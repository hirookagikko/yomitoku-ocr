# OCR TOC Analyzer

OCR処理済みの書籍から目次を解析し、章分割を行う。

**LLMベースの目次解析**: 正規表現では検出困難な目次構造も解析可能。

## パラメータ

このエージェントは ocr-pipeline.md から呼ばれる。以下のパラメータが渡される:

- `output_dir`: OCR出力ディレクトリのフルパス
- `SKILL_DIR`: スキルルートディレクトリの絶対パス

---

## Phase 1: ディレクトリ選択

パラメータが指定されている場合はそのディレクトリを使用。
指定がない場合は対話的に選択。

### 処理手順

1. **OCR出力ディレクトリを検索**
   - `.ocr_complete` フラグがあり、`pages/` ディレクトリが存在するフォルダ
   - 既に `chapters/` がある場合は「処理済み」と表示

2. **一覧を表示**（テーブル形式）

3. **ユーザーに選択を促す**（AskUserQuestion使用）

---

## Phase 2: 目次解析（LLM処理）

### Step 1: ページを順次読み込み

pages/ からページ1から順に読み込む。

### Step 2: 目次ページを検出

以下のキーワードを探す:
- 「目次」「もくじ」「CONTENTS」「Contents」

**検出したら目次解析を開始**。

### Step 3: 章情報を抽出

目次ページから以下のパターンを抽出:
- 章タイトル（第N章、Part N、Chapter N、技法N、etc.）
- ページ番号（末尾の数字）

**目次終了の判定**:
- 連続する「タイトル + ページ番号」パターンが途切れた
- 「はじめに」「序章」の本文が始まった
- 空ページや図版のみのページが続いた

### Step 4: オフセット検証

目次に記載されたページ番号と、実際のPDFページ番号の差を検証。

```
offset = PDFページ - 印刷ページ
```

**検証方法**:
- 目次の最初の章の開始ページをpages/で探す
- 章タイトルが含まれるページ番号を確認
- 差分がオフセット

---

## Phase 3: chapter_override.json 生成

解析結果をJSONで出力:

```json
{
  "book_title": "書籍名",
  "total_pages": N,
  "chapters": [
    {"number": "0", "title": "前付け", "start_page": 1, "end_page": 10},
    {"number": "1", "title": "第1章 xxx", "start_page": 11, "end_page": 50},
    {"number": "2", "title": "第2章 yyy", "start_page": 51, "end_page": 100}
  ]
}
```

**注意点**:
- `start_page`, `end_page` はPDFページ番号（印刷ページではない）
- 各章の `end_page` は次章の `start_page - 1`
- 最終章の `end_page` は `total_pages`

---

## Phase 4: 章分割実行

```bash
python3 SKILL_DIR/scripts/rebuild_chapters.py "{output_dir}"
```

出力: `chapters/` に章単位Markdown、`README.md` に目次リンク、`.rebuild_complete` フラグ。
詳細は SKILL.md の「出力構造」参照。

---

## エラーハンドリング

| 状況 | 対処 |
|------|------|
| 目次ページが見つからない | ユーザーに目次ページ番号を確認 |
| 章情報が抽出できない | 手動で章構成を指定するよう案内 |
| オフセットが不明確 | 複数ページで検証を試みる |
