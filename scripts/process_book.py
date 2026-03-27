#!/usr/bin/env python3
"""
OCR後処理スクリプト: 目次検出・章分割・README生成
Usage: python process_book.py <ocr_output_dir> [--book-title "書籍名"] [--author "著者名"]

機能:
- ページオフセット自動検出（PDFページ番号 vs 印刷ページ番号）
- 目次と実際の章見出し位置を照合して補正
- 検証ログ出力
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


@dataclass
class Chapter:
    """章情報"""
    number: str  # "序", "1", "2", "終", "後", "参"
    title: str
    start_page: int  # 印刷ページ番号（目次記載の番号）
    pdf_page: int = -1  # 実際のPDFページ番号
    end_page: Optional[int] = None
    pdf_end_page: Optional[int] = None
    filename: str = ""
    verified: bool = False  # 実際に章見出しが見つかったか


@dataclass
class BookInfo:
    """書籍情報"""
    title: str = ""
    author: str = ""
    publisher: str = ""
    chapters: list = field(default_factory=list)
    total_pages: int = 0
    page_offset: int = 0  # PDFページ - 印刷ページ


def detect_page_offset(pages_dir: Path) -> tuple[int, list[tuple[int, int]]]:
    """
    PDFページ番号と印刷ページ番号のオフセットを検出

    Returns:
        (offset, samples): offsetはPDFページ-印刷ページ、samplesは検出サンプル
    """
    page_files = sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))

    samples = []  # (pdf_page, printed_page) のペア

    # 最初の10ページはスキップ（表紙、目次など）
    # 10-60ページあたりをサンプリング
    for page_file in page_files[10:60]:
        pdf_page = extract_page_num(page_file.name)
        content = page_file.read_text(encoding='utf-8')
        lines = content.strip().split('\n')

        if not lines:
            continue

        # ページ番号は通常、最初か最後の行にある
        candidates = []
        if lines:
            candidates.append(lines[0].strip())
            candidates.append(lines[-1].strip())
        if len(lines) > 1:
            candidates.append(lines[1].strip())
            candidates.append(lines[-2].strip())

        for line in candidates:
            # 1-3桁の単独数字（ページ番号パターン）
            if re.match(r'^\d{1,3}$', line):
                printed_page = int(line)
                # 妥当性チェック: 印刷ページはPDFページより小さいはず
                if 0 < printed_page < pdf_page:
                    samples.append((pdf_page, printed_page))
                    break

    if not samples:
        return 0, []

    # オフセットを計算（最頻値を使用）
    offsets = [pdf - printed for pdf, printed in samples]
    offset_counter = Counter(offsets)
    most_common_offset = offset_counter.most_common(1)[0][0]

    # 信頼性チェック: 最頻値が全体の50%以上か
    confidence = offset_counter[most_common_offset] / len(offsets)
    if confidence < 0.3:
        # 信頼性が低い場合は0を返す
        return 0, samples

    return most_common_offset, samples


def find_chapter_in_files(chapter_pattern: str, pages_dir: Path,
                          hint_pdf_page: int = 0, search_range: int = 50) -> tuple[int, str]:
    """
    章見出しパターンを実際のOCRファイルから検索

    Args:
        chapter_pattern: 検索する正規表現パターン
        pages_dir: ページファイルディレクトリ
        hint_pdf_page: 予想されるPDFページ（ヒント、0なら全検索）
        search_range: ヒントからの検索範囲

    Returns:
        (pdf_page, matched_line): 見つかったPDFページ番号とマッチした行
    """
    page_files = sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))
    page_dict = {extract_page_num(p.name): p for p in page_files}

    # ヒントがある場合はその周辺を優先検索
    if hint_pdf_page > 0:
        search_pages = list(range(max(1, hint_pdf_page - search_range),
                                   hint_pdf_page + search_range + 1))
    else:
        search_pages = [extract_page_num(p.name) for p in page_files]

    for pdf_page in search_pages:
        if pdf_page not in page_dict:
            continue

        content = page_dict[pdf_page].read_text(encoding='utf-8')
        lines = content.split('\n')

        # ページの最初の15行を検索（章見出しは通常ページ上部にある）
        for line in lines[:15]:
            line_stripped = line.strip()
            if re.search(chapter_pattern, line_stripped):
                return pdf_page, line_stripped

    return 0, ""


def locate_chapters_in_files(chapters: list, pages_dir: Path) -> tuple[list, int]:
    """
    各章の見出しを実際のOCRファイルから検索し、PDFページ番号を特定

    Returns:
        (chapters, calculated_offset): 更新された章リストと計算されたオフセット
    """
    page_files = sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))

    offsets = []  # 各章から計算されたオフセット

    for chapter in chapters:
        # 章タイトルのパターンを作成（複数パターンを試行）
        patterns = []

        if chapter.number.isdigit():
            patterns.append(rf'^#?\s*第\s*{chapter.number}\s*章')
        elif chapter.number == "序":
            patterns.append(r'^#?\s*(はじめに|序章|序文|まえがき|プロローグ)')
        elif chapter.number == "終":
            patterns.append(r'^#?\s*終\s*章')
        elif chapter.number == "後":
            patterns.append(r'^#?\s*(あとがき|おわりに|エピローグ)')
        elif chapter.number == "参":
            patterns.append(r'^#?\s*(参考文献|引用文献|索引)')

        # タイトルからも検索パターンを生成
        # 例: "作品タイトル" → "^#?\s*作品タイトル" または "^#?\s*作品タ"
        title_clean = chapter.title.strip()
        # "第N章 タイトル" から "タイトル" 部分を抽出
        title_match = re.search(r'第\s*\d+\s*章\s*(.+)', title_clean)
        if title_match:
            title_clean = title_match.group(1).strip()

        if title_clean and len(title_clean) >= 2:
            # 完全タイトルマッチ
            safe_title = re.escape(title_clean[:20])
            patterns.append(rf'^#?\s*{safe_title}')
            # 短縮タイトルマッチ（最初の5文字）
            if len(title_clean) > 5:
                safe_short = re.escape(title_clean[:5])
                patterns.append(rf'^#?\s*{safe_short}')

        # ヒントとして目次のページ番号を使用
        hint = chapter.start_page if chapter.start_page > 0 else 0

        # 各パターンで検索
        found = False
        for pattern in patterns:
            pdf_page, matched_line = find_chapter_in_files(pattern, pages_dir, hint, search_range=30)
            if pdf_page > 0:
                chapter.pdf_page = pdf_page
                chapter.verified = True
                found = True

                # オフセット計算
                if chapter.start_page > 0:
                    offset = pdf_page - chapter.start_page
                    offsets.append(offset)

                print(f"  ✓ Found: {chapter.title[:30]}")
                print(f"       → PDF page {pdf_page} (printed: {chapter.start_page})")
                print(f"       matched: \"{matched_line[:50]}...\"")
                break

        if not found:
            print(f"  ? Not found: {chapter.title[:30]}")
            print(f"       (expected around printed page {chapter.start_page})")

    # 最頻オフセットを計算
    if offsets:
        offset_counter = Counter(offsets)
        calculated_offset = offset_counter.most_common(1)[0][0]
    else:
        calculated_offset = 0

    # 見つからなかった章にはオフセットを適用
    for chapter in chapters:
        if not chapter.verified and chapter.start_page > 0:
            chapter.pdf_page = chapter.start_page + calculated_offset

    return chapters, calculated_offset


def recalculate_end_pages_from_next_start(chapters: list, total_pages: int) -> list:
    """
    各章の終了ページを「次の章の開始ページ - 1」として再計算

    これにより、章の境界が正確になる（前章の内容が次章に混入しない）

    修正: 終了ページ < 開始ページの場合のバリデーション追加
    """
    # pdf_pageでソート
    chapters_sorted = sorted(chapters, key=lambda c: c.pdf_page if c.pdf_page > 0 else 9999)

    for i, chapter in enumerate(chapters_sorted):
        if i + 1 < len(chapters_sorted):
            next_chapter = chapters_sorted[i + 1]
            end_page = next_chapter.pdf_page - 1

            # バリデーション: 終了ページが開始ページ以上であることを確認
            if end_page < chapter.pdf_page:
                # エラーケース: 次の章と同じページから始まっている
                # → この章を1ページ分だけ割り当てる
                chapter.pdf_end_page = chapter.pdf_page
                print(f"  Warning: Chapter '{chapter.title[:30]}' has invalid range, setting to single page")
            else:
                chapter.pdf_end_page = end_page
        else:
            chapter.pdf_end_page = total_pages

    # 空章(開始=終了かつ内容なし)を除外せず、警告のみ
    valid_chapters = []
    for ch in chapters_sorted:
        if ch.pdf_end_page >= ch.pdf_page:
            valid_chapters.append(ch)
        else:
            print(f"  Skipping invalid chapter: {ch.title[:30]} (start={ch.pdf_page}, end={ch.pdf_end_page})")

    return valid_chapters


def verify_chapter_positions(chapters: list, pages_dir: Path, offset: int) -> list:
    """
    章の開始位置を実際のOCR内容と照合して検証・補正
    (後方互換性のため残す - locate_chapters_in_files を推奨)

    Args:
        chapters: 目次から抽出した章リスト
        pages_dir: ページファイルディレクトリ
        offset: 検出されたオフセット

    Returns:
        補正済みの章リスト
    """
    page_files = {extract_page_num(p.name): p for p in pages_dir.glob("*.md")}

    for chapter in chapters:
        if chapter.start_page <= 0:
            continue

        # 目次のページ番号 + オフセット = PDFページ番号
        expected_pdf_page = chapter.start_page + offset
        chapter.pdf_page = expected_pdf_page

        # 章タイトルのパターンを作成
        if chapter.number.isdigit():
            pattern = rf'第\s*{chapter.number}\s*章'
        elif chapter.number == "序":
            pattern = r'(はじめに|序章|序文|まえがき|プロローグ)'
        elif chapter.number == "終":
            pattern = r'終\s*章'
        elif chapter.number == "後":
            pattern = r'(あとがき|おわりに|エピローグ)'
        elif chapter.number == "参":
            pattern = r'(参考文献|引用文献|索引)'
        else:
            pattern = re.escape(chapter.title[:10])

        # 予測PDFページの前後3ページを検索
        search_range = range(max(1, expected_pdf_page - 3), expected_pdf_page + 4)

        for pdf_page in search_range:
            if pdf_page not in page_files:
                continue

            content = page_files[pdf_page].read_text(encoding='utf-8')
            # 最初の10行を検索
            for line in content.split('\n')[:10]:
                if re.search(pattern, line.strip()):
                    # 見つかった場合、実際のPDFページで補正
                    if pdf_page != expected_pdf_page:
                        # オフセットを微調整
                        actual_offset = pdf_page - chapter.start_page
                        chapter.pdf_page = pdf_page
                    chapter.verified = True
                    break
            if chapter.verified:
                break

    return chapters


def parse_anthology_toc(toc_content: str) -> list[Chapter]:
    """
    アンソロジー形式の目次をパース

    アンソロジー形式の目次パターン:
        著者A作品タイトル           （著者+タイトル、ページなし）
        著者B別の作品タイトル31
        著者 C スペース入りの名前53 （著者名にスペースあり）
        著者Dまた別の作品75

    著者名は通常2-5文字の漢字（＋スペース）
    """
    chapters = []
    current_section = ""

    lines = toc_content.split('\n')

    # セクション見出しパターン（一般的なアンソロジー構成）
    section_keywords = ['目次', 'もくじ', 'CONTENTS']

    def extract_author_smart(text):
        """
        著者名を抽出（スマート版）

        著者名の典型パターン:
        - 4文字: 山田太郎, 佐藤花子
        - 5文字: 田中みづき, 鈴木一太郎
        - スペース入り: 山田 航, 森 まゆみ（姓+スペース+名）
        """
        # パターン1: 姓(1-3文字) + スペース + 名 + タイトル
        space_match = re.match(r'^([一-龥]{1,3})\s(.+)$', text)
        if space_match:
            surname = space_match.group(1)
            rest_after_space = space_match.group(2)

            # 姓が短い(1文字)場合は名を長めに、姓が長い場合は名を短めに
            if len(surname) == 1:
                # 姓1文字: 名2-3文字を優先（森 まゆみ など）
                name_range = range(min(3, len(rest_after_space)), 0, -1)
            else:
                # 姓2-3文字: 名1-2文字を優先（岩崎 航 など）
                name_range = range(1, min(4, len(rest_after_space)))

            for name_len in name_range:
                given = rest_after_space[:name_len]
                title = rest_after_space[name_len:]

                if (re.match(r'^[一-龥ぁ-んァ-ヶ]+$', given) and len(title) >= 2):
                    if 2 <= len(surname) + name_len <= 5:
                        return f"{surname} {given}", title

        # パターン2: 著者名(4-6文字) + スペース + タイトル
        space_after_name = re.match(r'^([一-龥ぁ-んァ-ヶ]{4,6})\s+(.+)$', text)
        if space_after_name:
            return space_after_name.group(1), space_after_name.group(2)

        # パターン3: スペースなし、4文字で区切る
        if len(text) >= 5:
            char5 = text[4] if len(text) > 4 else ''
            char6 = text[5] if len(text) > 5 else ''

            # 5文字目と6文字目が共にひらがな/カタカナならタイトル開始
            if (re.match(r'[ぁ-んァ-ヶ]', char5) and
                re.match(r'[ぁ-んァ-ヶ、。]', char6)):
                return text[:4], text[4:]

            # 5文字目がひらがな/カタカナで、4文字目が漢字なら著者名は5文字
            if (re.match(r'[ぁ-んァ-ヶ]', char5) and
                re.match(r'[一-龥]', text[3]) and
                len(text) > 5 and re.match(r'[一-龥]', char6)):
                return text[:5], text[5:]

            # デフォルト: 4文字
            return text[:4], text[4:]

        return None, text

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # セクション見出しをチェック
        if line in section_keywords or (len(line) <= 10 and not any(c.isdigit() for c in line)):
            # 数字がなく短い行はセクション見出しの可能性
            if any(kw in line for kw in section_keywords) or len(line) <= 8:
                current_section = line
                continue

        # ページ番号ありのエントリ: 末尾に数字
        page_match = re.search(r'(\d{1,3})\s*$', line)
        if page_match:
            page = int(page_match.group(1))
            content = line[:page_match.start()].strip()

            # 著者名を抽出
            author, title = extract_author_smart(content)

            if author and title and len(title) >= 2:
                author_clean = author.replace(' ', '')
                chapters.append(Chapter(
                    number=str(len(chapters) + 1),
                    title=title,
                    start_page=page,
                    filename=f"{author_clean}_{title[:15]}"
                ))
            elif content and not re.match(r'(第\d+章|はじめに|序章|あとがき|参考文献)', content):
                # 著者名抽出できないが標準章パターンでもない
                chapters.append(Chapter(
                    number=str(len(chapters) + 1),
                    title=content,
                    start_page=page,
                    filename=content[:20]
                ))

        # ページ番号なしのエントリ（最初のエッセイなど）
        elif len(line) > 5 and not any(kw in line for kw in section_keywords):
            author, title = extract_author_smart(line)
            if author and title and len(title) >= 2:
                author_clean = author.replace(' ', '')
                chapters.append(Chapter(
                    number=str(len(chapters) + 1),
                    title=title,
                    start_page=-1,  # ページ番号不明（後で検出）
                    filename=f"{author_clean}_{title[:15]}"
                ))

    return chapters


def detect_anthology_chapters(pages_dir: Path) -> list[Chapter]:
    """
    目次ページからアンソロジー形式の章を検出

    Returns:
        検出された章リスト
    """
    # 目次ページを取得
    result = find_toc_pages(pages_dir)
    if not result:
        return []

    toc_page, toc_content = result

    # アンソロジー形式でパース
    chapters = parse_anthology_toc(toc_content)

    if chapters:
        print(f"  Detected anthology format: {len(chapters)} essays")

    return chapters


def find_toc_pages(pages_dir: Path) -> Optional[tuple[int, str]]:
    """目次ページを検索し、複数ページを統合"""
    toc_patterns = [
        r'^#?\s*(目\s*次|もくじ|CONTENTS|Contents)',
        r'^\s*(目\s*次|もくじ)',
    ]

    page_files = sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))

    toc_start = None
    toc_contents = []

    for page_file in page_files[:30]:  # 最初の30ページを検索
        content = page_file.read_text(encoding='utf-8')
        page_num = extract_page_num(page_file.name)

        # 目次開始を検出
        if toc_start is None:
            for pattern in toc_patterns:
                if re.search(pattern, content, re.MULTILINE):
                    toc_start = page_num
                    toc_contents.append(content)
                    break
        elif toc_start is not None:
            # 目次の続きページをチェック
            # 1. 標準章パターン（第N章、終章など）
            # 2. アンソロジーパターン（行末にページ番号がある）
            is_toc_continuation = (
                re.search(r'第\s*\d+\s*章|終章|あとがき|参考文献', content) or
                re.search(r'\d{1,3}\s*$', content, re.MULTILINE)  # 行末にページ番号
            )

            if is_toc_continuation:
                toc_contents.append(content)
                # 本文開始の兆候（長い段落など）があれば終了
                if len(content) > 1000 and not re.search(r'\d{1,3}\s*$', content, re.MULTILINE):
                    break
            else:
                # パターンがなければ目次終了
                break

            # 最大5ページまで
            if len(toc_contents) >= 5:
                break

    if toc_start is not None:
        return toc_start, '\n'.join(toc_contents)

    return None


def extract_page_num(filename: str) -> int:
    """ファイル名からページ番号を抽出"""
    match = re.search(r'_p(\d+)\.md$', filename)
    if match:
        return int(match.group(1))
    return 0


def parse_toc(toc_content: str) -> list[Chapter]:
    """目次からチャプター情報を抽出"""
    chapters = []
    seen_chapters = set()  # 重複防止

    lines = toc_content.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 第N章パターン（複数形式対応）
        # 形式1: 「第1章 タイトル...123」または「第1章 タイトル 123」
        # 形式2: 「第1章 タイトル123」（数字が直接連結）
        # 形式3: 「第1章 タイトル」（ページ番号なし - 後で本文から検出）
        match = re.search(r'(第\s*(\d+)\s*章)\s*([^0-9]+?)[\s…\.・]*(\d+)\s*$', line)
        if match:
            num = match.group(2)
            if num not in seen_chapters:
                seen_chapters.add(num)
                chapters.append(Chapter(
                    number=num,
                    title=f"{match.group(1)} {match.group(3).strip()}",
                    start_page=int(match.group(4))
                ))
            continue

        # ページ番号なしの第N章（後で本文から開始ページを検出）
        match = re.search(r'(第\s*(\d+)\s*章)\s*(.+?)$', line)
        if match and not re.search(r'\d+$', line):
            num = match.group(2)
            if num not in seen_chapters:
                seen_chapters.add(num)
                chapters.append(Chapter(
                    number=num,
                    title=f"{match.group(1)} {match.group(3).strip()}",
                    start_page=-1  # 後で本文から検出
                ))
            continue

        # 終章パターン（ページ番号付き）
        match = re.search(r'(終\s*章)\s*([^0-9]*?)[\s…\.・]*(\d+)\s*$', line)
        if match and "終" not in seen_chapters:
            seen_chapters.add("終")
            title = match.group(2).strip()
            chapters.append(Chapter(
                number="終",
                title=f"終章{' ' + title if title else ''}",
                start_page=int(match.group(3))
            ))
            continue

        # はじめに/序章（ローマ数字または数字）
        match = re.search(r'(はじめに|序章|序文|まえがき|プロローグ)\s*([ivxIVX]+|\d+)\s*$', line)
        if match and "序" not in seen_chapters:
            seen_chapters.add("序")
            page_str = match.group(2).lower()
            # ローマ数字を変換（簡易版）
            if page_str in ['i', 'ii', 'iii', 'iv', 'v']:
                page = {'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5}.get(page_str, 1)
            else:
                page = int(page_str) if page_str.isdigit() else 1
            chapters.append(Chapter(
                number="序",
                title=match.group(1),
                start_page=page
            ))
            continue

        # あとがき
        match = re.search(r'(あとがき|エピローグ|おわりに)\s*[\s…\.・]*(\d+)\s*$', line)
        if match and "後" not in seen_chapters:
            seen_chapters.add("後")
            chapters.append(Chapter(
                number="後",
                title=match.group(1),
                start_page=int(match.group(2))
            ))
            continue

        # 参考文献/索引
        match = re.search(r'(参考文献|引用文献|索引)\s*[\s…\.・]*(\d+)\s*$', line)
        if match:
            label = match.group(1)
            if label not in seen_chapters:
                seen_chapters.add(label)
                chapters.append(Chapter(
                    number="参",
                    title=label,
                    start_page=int(match.group(2))
                ))

    # ページ番号でソート
    chapters.sort(key=lambda c: c.start_page)

    return chapters


def kanji_to_number(kanji: str) -> int:
    """漢数字を数字に変換"""
    kanji_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                 '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
    if kanji in kanji_map:
        return kanji_map[kanji]
    # 十一、十二など
    if kanji.startswith('十'):
        if len(kanji) == 1:
            return 10
        return 10 + kanji_map.get(kanji[1], 0)
    # 二十、三十など
    if len(kanji) >= 2 and kanji[1] == '十':
        base = kanji_map.get(kanji[0], 0) * 10
        if len(kanji) > 2:
            return base + kanji_map.get(kanji[2], 0)
        return base
    return 0


def detect_chapters_from_content(pages_dir: Path) -> list[Chapter]:
    """本文から章見出しを直接検出 - 拡張版"""
    chapters = []
    seen_chapters = set()  # 各章の最初の出現のみ記録
    first_chapter_page = None  # 第1章の開始ページ

    page_files = sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))

    # まず第1章を探す（目次ページをスキップするため）
    for page_file in page_files:
        content = page_file.read_text(encoding='utf-8')
        for line in content.split('\n')[:5]:
            # 数字版と漢数字版の両方をチェック
            if re.search(r'^#?\s*第\s*(1|一)\s*章', line.strip()):
                first_chapter_page = extract_page_num(page_file.name)
                break
        if first_chapter_page:
            break

    for page_file in page_files:
        content = page_file.read_text(encoding='utf-8')
        page_num = extract_page_num(page_file.name)

        # 各ページの最初の5行を検索
        for line in content.split('\n')[:5]:
            line = line.strip()

            # 第N章パターン (数字)
            match = re.search(r'^#?\s*(第\s*(\d+)\s*章)', line)
            if match:
                num = match.group(2)
                # 第1章より前のページで第2章以降が見つかった場合はスキップ（目次ページ）
                if first_chapter_page and page_num < first_chapter_page and num != "1":
                    continue
                if num not in seen_chapters:
                    seen_chapters.add(num)
                    chapters.append(Chapter(
                        number=num,
                        title=match.group(1).strip(),
                        start_page=page_num
                    ))
                break

            # 第N章パターン (漢数字: 第一章、第二章...)
            match = re.search(r'^#?\s*(第\s*([一二三四五六七八九十]+)\s*章)', line)
            if match:
                kanji_num = match.group(2)
                num = str(kanji_to_number(kanji_num))
                if first_chapter_page and page_num < first_chapter_page and num != "1":
                    continue
                if num not in seen_chapters:
                    seen_chapters.add(num)
                    chapters.append(Chapter(
                        number=num,
                        title=match.group(1).strip(),
                        start_page=page_num
                    ))
                break

            # Part/PART/パート形式
            match = re.search(r'^#?\s*(Part\s*(\d+)|PART\s*(\d+)|パート\s*(\d+))', line, re.IGNORECASE)
            if match:
                num = match.group(2) or match.group(3) or match.group(4)
                key = f"part_{num}"
                if key not in seen_chapters:
                    seen_chapters.add(key)
                    chapters.append(Chapter(
                        number=f"P{num}",
                        title=match.group(1).strip(),
                        start_page=page_num
                    ))
                break

            # Chapter形式 (英語)
            match = re.search(r'^#?\s*(Chapter\s*(\d+)|CHAPTER\s*(\d+))', line, re.IGNORECASE)
            if match:
                num = match.group(2) or match.group(3)
                key = f"ch_{num}"
                if key not in seen_chapters:
                    seen_chapters.add(key)
                    chapters.append(Chapter(
                        number=num,
                        title=match.group(1).strip(),
                        start_page=page_num
                    ))
                break

            # はじめに/序章/プロローグ
            match = re.search(r'^#?\s*(はじめに|序章|序文|まえがき|プロローグ|Prologue)', line, re.IGNORECASE)
            if match and "序" not in seen_chapters:
                seen_chapters.add("序")
                chapters.append(Chapter(
                    number="序",
                    title=match.group(1),
                    start_page=page_num
                ))
                break

            # 終章/エピローグ（スペース入りも対応）
            match = re.search(r'^#?\s*(終\s*章|エピローグ|Epilogue)', line, re.IGNORECASE)
            if match and "終" not in seen_chapters:
                seen_chapters.add("終")
                chapters.append(Chapter(
                    number="終",
                    title=match.group(1).replace(' ', ''),
                    start_page=page_num
                ))
                break

            # あとがき
            match = re.search(r'^#?\s*(あとがき|おわりに|後書き|Afterword)', line, re.IGNORECASE)
            if match and "後" not in seen_chapters:
                seen_chapters.add("後")
                chapters.append(Chapter(
                    number="後",
                    title=match.group(1),
                    start_page=page_num
                ))
                break

            # 参考文献/索引
            match = re.search(r'^#?\s*(参考文献|引用文献|索引|Bibliography|Index)', line, re.IGNORECASE)
            if match and "参" not in seen_chapters:
                seen_chapters.add("参")
                chapters.append(Chapter(
                    number="参",
                    title=match.group(1),
                    start_page=page_num
                ))
                break

    return chapters


def create_fallback_chapters(pages_dir: Path, target_chapter_size: int = 50) -> list[Chapter]:
    """
    章検出に完全に失敗した場合のフォールバック

    戦略: 約50ページごとに均等分割
    (全ページを1ファイルに統合するよりは実用的)

    Args:
        pages_dir: ページファイルディレクトリ
        target_chapter_size: 1章あたりの目標ページ数 (デフォルト50)

    Returns:
        均等分割された章リスト
    """
    page_files = sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))
    total_pages = len(page_files)

    if total_pages <= target_chapter_size:
        # 50ページ以下なら1章で良い
        return [Chapter(number="1", title="全編", start_page=1, pdf_page=1)]

    num_chapters = (total_pages + target_chapter_size - 1) // target_chapter_size
    chapters = []

    for i in range(num_chapters):
        start = i * target_chapter_size + 1
        end = min((i + 1) * target_chapter_size, total_pages)
        chapters.append(Chapter(
            number=str(i + 1),
            title=f"Part {i + 1} (pp.{start}-{end})",
            start_page=start,
            pdf_page=start,
            end_page=end,
            pdf_end_page=end,
            verified=False
        ))

    print(f"  Fallback: Created {num_chapters} chapters ({target_chapter_size} pages each)")
    return chapters


def fill_missing_page_numbers(chapters: list[Chapter], pages_dir: Path) -> list[Chapter]:
    """start_page=-1 の章について本文から開始ページを検出"""
    missing = [ch for ch in chapters if ch.start_page == -1]
    if not missing:
        return chapters

    page_files = sorted(pages_dir.glob("*.md"), key=lambda p: extract_page_num(p.name))

    for chapter in missing:
        # 章番号を抽出
        match = re.search(r'第\s*(\d+)\s*章', chapter.title)
        if not match:
            continue
        chapter_num = match.group(1)
        pattern = rf'^#?\s*第\s*{chapter_num}\s*章'

        for page_file in page_files:
            content = page_file.read_text(encoding='utf-8')
            # 最初の5行を検索
            for line in content.split('\n')[:5]:
                if re.search(pattern, line.strip()):
                    chapter.start_page = extract_page_num(page_file.name)
                    break
            if chapter.start_page != -1:
                break

    # まだ -1 の章を削除
    chapters = [ch for ch in chapters if ch.start_page != -1]

    # ページ番号でソート
    chapters.sort(key=lambda c: c.start_page)

    return chapters


def calculate_end_pages(chapters: list[Chapter], total_pages: int) -> list[Chapter]:
    """各章の終了ページを計算"""
    for i, chapter in enumerate(chapters):
        if i + 1 < len(chapters):
            chapter.end_page = chapters[i + 1].start_page - 1
        else:
            chapter.end_page = total_pages
    return chapters


def sanitize_title_for_filename(title: str, max_length: int = 50) -> str:
    """
    タイトルをファイル名用に正規化

    処理:
    1. 制御文字・不正文字の除去
    2. OCR誤認識パターンの修正
    3. 過度な空白・記号の正規化
    """
    # Step 1: 不正文字の除去 (ファイル名に使えない文字)
    safe_title = re.sub(r'[/\\:*?"<>|]', '', title)

    # Step 2: 制御文字の除去
    safe_title = re.sub(r'[\x00-\x1f\x7f]', '', safe_title)

    # Step 3: 全角・半角スペース、タブをアンダースコアに
    safe_title = re.sub(r'[\s　\t]+', '_', safe_title)

    # Step 4: 連続するアンダースコアを1つに
    safe_title = re.sub(r'_+', '_', safe_title)

    # Step 5: 先頭・末尾のアンダースコア除去
    safe_title = safe_title.strip('_')

    # Step 6: OCR誤認識パターンの検出・除去
    # 例: 謎の記号の連続、不自然な文字化けパターン
    safe_title = re.sub(r'[□■◆●○◎△▽▲▼]+', '', safe_title)

    # Step 7: 長すぎる場合は切り詰め（日本語の文字境界を考慮）
    if len(safe_title) > max_length:
        safe_title = safe_title[:max_length].rstrip('_')

    # Step 8: 最低限の文字数を確保
    if len(safe_title) < 2:
        safe_title = "untitled"

    return safe_title


def generate_filename(index: int, chapter: Chapter) -> str:
    """章ファイル名を生成 - 改良版"""
    safe_title = sanitize_title_for_filename(chapter.title)
    return f"{index:02d}_{safe_title}.md"


def merge_pages(pages_dir: Path, chapters_dir: Path, chapters: list[Chapter], offset: int = 0) -> None:
    """ページファイルを章ごとにマージ（PDFページ番号を使用）"""
    chapters_dir.mkdir(exist_ok=True)

    page_files = {extract_page_num(p.name): p for p in pages_dir.glob("*.md")}

    for i, chapter in enumerate(chapters):
        chapter.filename = generate_filename(i, chapter)
        output_path = chapters_dir / chapter.filename

        content_parts = []
        content_parts.append(f"# {chapter.title}\n\n")

        # PDFページ番号を使用（設定されていなければ印刷ページ+オフセット）
        start_pdf = chapter.pdf_page if chapter.pdf_page > 0 else chapter.start_page + offset
        end_pdf = chapter.pdf_end_page if chapter.pdf_end_page else (
            chapter.end_page + offset if chapter.end_page else start_pdf
        )

        for pdf_page in range(start_pdf, end_pdf + 1):
            if pdf_page in page_files:
                page_content = page_files[pdf_page].read_text(encoding='utf-8')
                # 印刷ページ番号も記録
                printed_page = pdf_page - offset
                content_parts.append(f"<!-- pdf:{pdf_page} printed:{printed_page} -->\n")
                content_parts.append(page_content)
                content_parts.append("\n\n")

        output_path.write_text(''.join(content_parts), encoding='utf-8')
        verified_mark = "✓" if chapter.verified else "?"
        print(f"  {verified_mark} Created: {chapter.filename} (pdf:{start_pdf}-{end_pdf}, printed:{chapter.start_page}-{chapter.end_page})")


def write_verification_log(output_dir: Path, book_info: BookInfo, chapters: list[Chapter],
                           offset: int, offset_samples: list) -> None:
    """検証ログを出力"""
    log_path = output_dir / ".verification_log.json"

    log_data = {
        "processed_at": datetime.now().isoformat(),
        "book_title": book_info.title,
        "total_pages": book_info.total_pages,
        "detected_offset": offset,
        "offset_samples": [{"pdf": pdf, "printed": printed} for pdf, printed in offset_samples[:10]],
        "chapters": [
            {
                "number": ch.number,
                "title": ch.title,
                "printed_page": ch.start_page,
                "pdf_page": ch.pdf_page,
                "verified": ch.verified,
                "end_printed": ch.end_page,
                "end_pdf": ch.pdf_end_page,
            }
            for ch in chapters
        ],
        "verification_summary": {
            "total_chapters": len(chapters),
            "verified_chapters": sum(1 for ch in chapters if ch.verified),
            "unverified_chapters": [ch.title for ch in chapters if not ch.verified],
        }
    }

    log_path.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding='utf-8')

    # 人間可読なログも出力
    readable_log = output_dir / ".verification_log.txt"
    lines = [
        f"=== 検証ログ ===",
        f"処理日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"書籍: {book_info.title}",
        f"総ページ数: {book_info.total_pages}",
        f"",
        f"=== ページオフセット ===",
        f"検出オフセット: {offset} (PDFページ = 印刷ページ + {offset})",
        f"サンプル数: {len(offset_samples)}",
        f"",
        f"=== 章検証結果 ===",
    ]

    for ch in chapters:
        status = "✓ 確認済" if ch.verified else "? 未確認"
        lines.append(f"  {status} {ch.title}")
        lines.append(f"         印刷ページ: {ch.start_page} → PDFページ: {ch.pdf_page}")

    verified_count = sum(1 for ch in chapters if ch.verified)
    lines.extend([
        f"",
        f"=== サマリー ===",
        f"検証済み: {verified_count}/{len(chapters)} 章",
    ])

    if verified_count < len(chapters):
        lines.append(f"注意: 一部の章が未確認です。手動確認を推奨します。")

    readable_log.write_text('\n'.join(lines), encoding='utf-8')
    print(f"  Created: .verification_log.txt")


def generate_readme(output_dir: Path, book_info: BookInfo, chapters: list[Chapter]) -> None:
    """README.mdを生成"""
    readme_path = output_dir / "README.md"

    lines = [
        f"# {book_info.title}\n",
        "",
    ]

    if book_info.author:
        lines.append(f"**著者**: {book_info.author}")
    if book_info.publisher:
        lines.append(f"**出版**: {book_info.publisher}")

    lines.extend([
        "",
        "---",
        "",
        "## 目次",
        "",
        "| No. | タイトル | ファイル |",
        "|-----|---------|----------|",
    ])

    for chapter in chapters:
        lines.append(
            f"| {chapter.number} | [{chapter.title}](chapters/{chapter.filename}) | `{chapter.filename}` |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## OCR情報",
        "",
        f"- **処理日**: {datetime.now().strftime('%Y-%m-%d')}",
        "- **ツール**: yomitoku",
        "- **オプション**: `-f md -d mps --ignore_meta --ignore_line_break`",
        f"- **総ページ数**: {book_info.total_pages}ページ",
        "",
        "---",
        "",
        "## フォルダ構成",
        "",
        "```",
        f"{book_info.title}/",
        "├── README.md          # このファイル",
        "├── chapters/          # 章ごとに統合されたMarkdownファイル",
    ])

    for chapter in chapters[:3]:
        lines.append(f"│   ├── {chapter.filename}")
    if len(chapters) > 3:
        lines.append("│   └── ...")

    lines.extend([
        "└── pages/             # ページごとのOCR出力（元データ）",
        "```",
        "",
    ])

    readme_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"  Created: README.md")


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_book.py <ocr_output_dir> [--book-title TITLE] [--author AUTHOR]")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    pages_dir = output_dir / "pages"
    chapters_dir = output_dir / "chapters"

    # オプション解析
    book_title = output_dir.name
    author = ""

    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--book-title" and i + 1 < len(args):
            book_title = args[i + 1]
        elif arg == "--author" and i + 1 < len(args):
            author = args[i + 1]

    if not pages_dir.exists():
        print(f"Error: pages directory not found: {pages_dir}")
        sys.exit(1)

    print(f"\n=== Processing: {book_title} ===\n")

    # 総ページ数を取得
    page_files = list(pages_dir.glob("*.md"))
    total_pages = len(page_files)
    print(f"Total pages: {total_pages}")

    # 章検出（まず標準パターン、次にアンソロジー形式を試行）
    print("\n[1/5] Detecting chapters...")

    # 1. 標準パターン検出（第N章など）
    print("  Trying standard chapter patterns...")
    chapters = detect_chapters_from_content(pages_dir)

    if chapters:
        chapter_nums = sorted([int(ch.number) for ch in chapters if ch.number.isdigit()])
        expected = list(range(1, max(chapter_nums) + 1)) if chapter_nums else []
        missing = set(expected) - set(chapter_nums)
        if missing:
            print(f"  Warning: Missing chapters: {sorted(missing)}")
        print(f"  Found {len(chapters)} standard chapters")

    # 2. 標準パターンで見つからない/少ない場合はアンソロジー形式を試行
    if len(chapters) <= 2:
        print("  Trying anthology format (author + essay title)...")
        anthology_chapters = detect_anthology_chapters(pages_dir)

        if len(anthology_chapters) > len(chapters):
            print(f"  Anthology format detected: {len(anthology_chapters)} essays")
            chapters = anthology_chapters
        elif anthology_chapters:
            print(f"  Found {len(anthology_chapters)} anthology entries (keeping standard)")

    # 3. 何も見つからない、または極端に少ない場合はフォールバック
    use_fallback = False
    if not chapters:
        print("  Warning: No chapters detected.")
        use_fallback = True
    elif len(chapters) == 1 and total_pages > 50:
        print(f"  Warning: Only 1 chapter for {total_pages} pages (under-segmented).")
        use_fallback = True

    if use_fallback:
        print("  Applying fallback strategy: even page distribution...")
        chapters = create_fallback_chapters(pages_dir, target_chapter_size=50)
        error_log = output_dir / ".process_errors.log"
        error_log.write_text(
            f"Chapter detection failed for: {book_title}\n"
            f"Total pages: {total_pages}\n"
            f"Fallback: Even distribution ({len(chapters)} parts)\n",
            encoding='utf-8'
        )

    print(f"  Total detected: {len(chapters)} chapters/essays")

    # [NEW] 章見出しを実際のファイルから検索してPDFページを特定
    print("\n[2/5] Locating chapter headings in files...")
    chapters, offset = locate_chapters_in_files(chapters, pages_dir)
    verified_count = sum(1 for ch in chapters if ch.verified)
    print(f"\n  Offset calculated from chapters: {offset}")
    print(f"  Verified: {verified_count}/{len(chapters)} chapters")

    # ページ番号からのオフセット検出（補助情報として）
    print("\n[3/5] Cross-checking with page number detection...")
    page_offset, offset_samples = detect_page_offset(pages_dir)
    if page_offset > 0:
        print(f"  Page number offset: {page_offset}")
        if page_offset != offset:
            print(f"  Note: Differs from chapter-based offset ({offset})")
            # 章ベースのオフセットを優先するが、記録は残す
    else:
        print(f"  No page numbers detected in content")

    # 終了ページ計算（次章の開始ページ - 1）
    print("\n[4/5] Calculating page ranges from chapter positions...")

    # 見つからなかった章のpdf_pageを設定
    for ch in chapters:
        if ch.pdf_page <= 0:
            ch.pdf_page = ch.start_page + offset

    # 次章の開始位置から終了位置を計算
    chapters = recalculate_end_pages_from_next_start(chapters, total_pages)

    # 印刷ページ番号も更新
    for ch in chapters:
        ch.end_page = ch.pdf_end_page - offset if ch.pdf_end_page else None

    for ch in chapters:
        verified_mark = "✓" if ch.verified else "?"
        print(f"  {verified_mark} {ch.number}: {ch.title}")
        print(f"       PDF: {ch.pdf_page}-{ch.pdf_end_page} (printed: {ch.start_page}-{ch.end_page})")

    # 章ごとにマージ
    print("\n[5/5] Merging pages into chapters...")
    merge_pages(pages_dir, chapters_dir, chapters, offset)

    # README生成
    print("\n[+] Generating README...")
    book_info = BookInfo(
        title=book_title,
        author=author,
        total_pages=total_pages,
        chapters=chapters,
        page_offset=offset
    )
    generate_readme(output_dir, book_info, chapters)

    # [NEW] 検証ログ出力
    print("\n[+] Writing verification log...")
    write_verification_log(output_dir, book_info, chapters, offset, offset_samples)

    # 完了フラグ
    (output_dir / ".process_complete").touch()

    print(f"\n=== Complete! ===")
    print(f"Output: {output_dir}")
    print(f"Chapters: {chapters_dir}")
    print(f"Offset: {offset} (PDF page = printed page + {offset})")
    print(f"Verified: {verified_count}/{len(chapters)} chapters")


if __name__ == "__main__":
    main()
