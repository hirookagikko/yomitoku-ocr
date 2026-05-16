#!/usr/bin/env python3
"""OCR出力から漢字熟語のルビ崩壊を自動検出するスクリプト

JMDict（日本語辞書）を使い、漢字熟語+ひらがな のパターンを抽出して
正しい読みと照合。不一致を「ルビ崩壊候補」としてレポートする。

Usage:
    python detect_ruby_errors.py <input_dir_or_file> [--limit 100]

依存: jamdict, jamdict-data (pip install jamdict jamdict-data)
"""
import os
import re
import sys
from pathlib import Path

from jamdict import Jamdict

# ── 設定 ──
# 漢字2文字以上 + ひらがな1文字以上 + 後続が助詞/句読点/漢字/記号
KANJI_HIRA_RE = re.compile(
    r'([\u4e00-\u9fff]{2,})([\u3040-\u309f]+)'
    r'(?=[。、\s\u4e00-\u9fff▲▼▶·\)\]がのにをはもでとへか]|$)'
)

# 助詞（1文字ひらがなで文法的に助詞になるもの）
PARTICLES = set('がのにをはもでとへかよねさえまりだばなてし')

# てにをは辞典の用例パターン（コロケーション動詞語尾）
# これらは漢字の「読み」ではなく用例なので除外
COLLOCATION_SUFFIXES = [
    # サ変動詞
    'する', 'させる', 'される', 'した', 'して', 'しない', 'すべき',
    # 基本動詞語尾
    'なる', 'ある', 'いる', 'ない', 'できる', 'れる', 'られる',
    # 形容詞・形容動詞語尾
    'しい', 'たい',
    # てにをは辞典頻出の用例パターン
    'になる', 'にする', 'をする', 'がある', 'がない', 'がつく',
    'という', 'といい', 'とする', 'とした', 'として',
    'である', 'ている', 'ていく', 'てくる', 'ておく',
    'のように', 'のような', 'のよう',
    'ほど', 'ほどに', 'ばかり',
    # 辞典記号直後
    'から', 'まで', 'より', 'ごと', 'ずつ',
    # 形容詞活用
    'しく', 'しい', 'しさ',
    # 動詞活用
    'める', 'せる', 'ける', 'げる', 'べる', 'ねる', 'てる', 'れる',
    'まる', 'わる', 'かる', 'がる', 'さる', 'たる', 'なる',
    'む', 'ぶ', 'ぐ', 'く', 'す', 'つ', 'ぬ', 'る',
    'んで', 'んだ', 'って', 'った',
    'いて', 'いた', 'える', 'おる',
    # 副詞・接続
    'ながら', 'ように', 'ところ', 'みたい', 'らしい', 'っぽい',
]


def is_collocation(hira: str) -> bool:
    """ひらがな部分がコロケーション用例パターンかどうか"""
    for suffix in COLLOCATION_SUFFIXES:
        if hira == suffix or hira.startswith(suffix):
            return True
    # 「〜に」「〜と」「〜で」で終わる2文字は助詞付きパターン
    if len(hira) <= 2 and hira[-1] in 'にとでをがはもへか':
        return True
    return False


def load_jamdict():
    """JMDict辞書をロード"""
    return Jamdict()


def get_valid_readings(jam, kanji_text: str) -> set[str]:
    """漢字熟語の正しい読み（ひらがな）をJMDictから取得"""
    readings = set()
    result = jam.lookup(kanji_text)
    for entry in result.entries:
        for kana in entry.kana_forms:
            readings.add(str(kana))
    return readings


SMALL_KANA = set('ぁぃぅぇぉゃゅょ')

# strict モードの追加フィルタ: 辞書OCRで頻出する送り仮名付き動詞・形容詞
# これらは MISMATCH になるが正常な日本語
OKURIGANA_SAFE = [
    # 超頻出パターン（送り仮名が読みと不一致で MISMATCH になるが正常）
    'ちよく', 'ちよい', 'ちより', 'ちよさ',  # 気持ち系
    'しろい', 'しろく', 'しろさ',  # 面白い系
    'まちが', 'まちい',  # 間違い系
    'もち',  # 心持ち系
    'わい', 'わく', 'わさ', 'わげ',  # 可愛い系
    'たち', 'だち',  # 言葉たち系
    'ぱい',  # 心配系
]


def extract_candidates(text: str, strict: bool = False) -> list[dict]:
    """テキストから 漢字+ひらがな パターンを抽出

    strict=True: ルビ崩壊の可能性が高いものだけに絞り込む
      - 小書き文字(ぁぃぅぇぉゃゅょ)で始まるパターン
      - JMDictに漢字がないパターン（extract時点ではフラグのみ）
    """
    candidates = []
    for m in KANJI_HIRA_RE.finditer(text):
        kanji = m.group(1)
        hira = m.group(2)
        if len(hira) == 1 and hira in PARTICLES:
            continue
        if is_collocation(hira):
            continue

        if strict:
            # strict モード: 小書き文字で始まるもののみ抽出
            # （NO_ENTRYフィルタは classify 段階で適用）
            if hira[0] not in SMALL_KANA:
                continue

        candidates.append({
            'kanji': kanji,
            'hira': hira,
            'full': m.group(0),
            'pos': m.start(),
        })
    return candidates


def classify_candidate(jam, kanji: str, hira: str) -> dict:
    """候補を分類: OK / SUSPICIOUS / ERROR"""
    readings = get_valid_readings(jam, kanji)

    if hira in readings:
        return {'status': 'OK_READING', 'readings': readings}

    for r in readings:
        if hira.startswith(r):
            return {'status': 'OK_OKURIGANA', 'readings': readings, 'base': r}
        if r.startswith(hira):
            return {'status': 'OK_PARTIAL', 'readings': readings}

    if not readings:
        return {'status': 'NO_ENTRY', 'readings': set()}

    return {'status': 'MISMATCH', 'readings': readings}


def process_file(jam, filepath: str, strict: bool = False) -> list[dict]:
    """1ファイルを処理してエラー候補を返す"""
    with open(filepath, encoding='utf-8') as f:
        text = f.read()

    candidates = extract_candidates(text, strict=strict)
    errors = []

    for cand in candidates:
        result = classify_candidate(jam, cand['kanji'], cand['hira'])
        if result['status'] in ('MISMATCH', 'NO_ENTRY'):
            start = max(0, cand['pos'] - 20)
            end = min(len(text), cand['pos'] + len(cand['full']) + 20)
            context = text[start:end].replace('\n', '↵')

            errors.append({
                'file': os.path.basename(filepath),
                'kanji': cand['kanji'],
                'hira': cand['hira'],
                'full': cand['full'],
                'status': result['status'],
                'expected': result['readings'],
                'context': context,
            })

    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python detect_ruby_errors.py <input_dir_or_file> [--limit N] [--strict]",
              file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    limit = 200
    strict = '--strict' in sys.argv
    if '--limit' in sys.argv:
        idx = sys.argv.index('--limit')
        limit = int(sys.argv[idx + 1])

    if strict:
        print("Strict mode: small-kana-initial patterns only", file=sys.stderr)

    print("Loading JMDict...", file=sys.stderr)
    jam = load_jamdict()
    print("JMDict loaded.", file=sys.stderr)

    if os.path.isdir(input_path):
        files = sorted(Path(input_path).glob("*.md"))
    else:
        files = [Path(input_path)]

    all_errors = []
    for f in files:
        print(f"  Scanning {f.name}...", file=sys.stderr)
        errors = process_file(jam, str(f), strict=strict)
        all_errors.extend(errors)

    # 重複排除
    seen = set()
    unique_errors = []
    for e in all_errors:
        key = (e['kanji'], e['hira'])
        if key not in seen:
            seen.add(key)
            unique_errors.append(e)

    unique_errors.sort(key=lambda e: (0 if e['status'] == 'MISMATCH' else 1, e['kanji']))

    # レポート出力
    print(f"\n{'='*70}")
    print(f"ルビ崩壊候補: {len(unique_errors)} 件 (重複除外)")
    print(f"{'='*70}\n")

    mismatch = [e for e in unique_errors if e['status'] == 'MISMATCH']
    no_entry = [e for e in unique_errors if e['status'] == 'NO_ENTRY']

    if mismatch:
        print(f"## MISMATCH（読み不一致）: {len(mismatch)} 件")
        print("  辞書に漢字はあるが、後続のひらがなが正しい読みと一致しない\n")
        for e in mismatch[:limit]:
            expected = ', '.join(sorted(e['expected']))
            print(f"  {e['full']:<20s} 期待: {expected:<20s} ...{e['context']}")
        print()

    if no_entry:
        print(f"## NO_ENTRY（辞書に未登録）: {len(no_entry)} 件")
        print("  漢字の組み合わせが辞書にない（OCR誤認 or 珍しい熟語）\n")
        for e in no_entry[:limit]:
            print(f"  {e['full']:<20s} ...{e['context']}")
        print()

    print(f"Total: {len(mismatch)} MISMATCH + {len(no_entry)} NO_ENTRY = {len(unique_errors)}")


if __name__ == "__main__":
    main()
