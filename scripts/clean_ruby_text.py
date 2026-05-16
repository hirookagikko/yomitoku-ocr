#!/usr/bin/env python3
"""YomiToku OCR出力からルビ(振り仮名)崩壊を修正する後処理スクリプト

役割の変遷:
    v0.12.0 で yomitoku 本体に --ignore_ruby が入ったため、ルビ削除の主役は OCR 側に移った。
    本スクリプトは「OCR で拾いきれなかった残ルビと、辞書ごとに蓄積した既知崩壊パターンの
    最終調整」を担当する。

ステージ:
    Stage 1 (既知パターン置換) — 辞書別ファイル(data/known_fixes/*.py)の FIXES に基づき確実な置換
    Stage 2 (汎用 regex 除去) — 小書き文字で始まるルビ残骸を除去 [既定では無効]
    Stage 3 (途中小書き含むルビ除去) — Stage 2 と同様、--enable-stage2 で同時に有効化

Usage:
    # 単一ファイル
    python clean_ruby_text.py <input.md> [output.md] [--dict てにをは辞典]

    # ディレクトリ一括処理
    python clean_ruby_text.py <input_dir> <output_dir> [--dict てにをは辞典]

    # 旧バージョン(--ignore_ruby 不在時)の出力を再処理する場合
    python clean_ruby_text.py <input> <output> --enable-stage2
"""
import importlib.util
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data" / "known_fixes"


def load_known_fixes(dict_name: str | None) -> list[tuple[str, str]]:
    """辞書別KNOWN_FIXESをロード。dict_name=None なら空リスト"""
    if not dict_name:
        return []

    fixes_file = DATA_DIR / f"{dict_name}.py"
    if not fixes_file.exists():
        available = [f.stem for f in DATA_DIR.glob("*.py") if f.stem != "__init__"]
        print(f"Error: '{dict_name}' not found in {DATA_DIR}", file=sys.stderr)
        print(f"Available: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    spec = importlib.util.spec_from_file_location(f"known_fixes.{dict_name}", fixes_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FIXES


def clean_ruby(
    text: str,
    known_fixes: list[tuple[str, str]] | None = None,
    enable_stage2: bool = False,
) -> str:
    """OCR出力テキストからルビ混入を修正"""

    # Stage 1: 既知パターン置換(長いパターンから順に適用)
    if known_fixes:
        fixes_sorted = sorted(known_fixes, key=lambda x: len(x[0]), reverse=True)
        for pattern, replacement in fixes_sorted:
            text = text.replace(pattern, replacement)

    if not enable_stage2:
        return text

    # Stage 2: 汎用ルビ残骸除去 — 小書き文字で始まるパターン
    # 条件:
    #   - 漢字2文字以上の直後
    #   - 小書き ぁぃぅぇぉゃゅょ で始まる(っは除外 — 本文の促音と区別不能)
    #   - その後にひらがな0-2文字が続く
    #   - 直後が漢字・記号・空白(=ルビの終端)
    # 助詞(が・の・に・を・は・も・で・と・へ・か)もルビ終端として扱い、
    # 助詞が巻き込まれるのを防ぐ
    text = re.sub(
        r'([一-鿿]{2,})[ぁぃぅぇぉゃゅょ][ぁ-ん]{0,2}(?=[。、\s一-鿿▲▼▶·\)\]がのにをはもでとへか])',
        r'\1',
        text,
    )

    # Stage 3: 途中に小書き文字を含むルビ残骸除去
    # 「漢字2+」→「ひらがな0-2 + 小書き文字 + optional う/ん」のパターンを除去
    # 例: 躊躇ちゅうする → 躊躇する, 華奢きゃな → 華奢な
    # ホワイトリスト: 「〜じゅう」(中)、「〜ちゃ」(口語縮約)等
    _safe_mid = re.compile(
        r'^(?:じゅう|でしゃ|をしゃ|にしゃ|りしゃ|をしょ|でしょ'
        r'|をぺちゃ|をきゅきゅ|がじゃん|がぴちゃ|にごちゃ'
        r'|ちゃ$)'  # 単独「ちゃ」は口語縮約(数撃ちゃ、言っちゃ)
    )

    def _stage3_replace(m):
        kanji = m.group(1)
        hira = m.group(2)
        if _safe_mid.match(hira):
            return m.group(0)
        return kanji

    text = re.sub(
        r'([一-鿿]{2,})([ぁ-ん]{0,2}[ぁぃぅぇぉゃゅょ][うん]{0,1})(?=[ぁ-ん。、\s一-鿿▲▼▶·\)\]])',
        _stage3_replace,
        text,
    )

    return text


def process_file(
    input_path: str,
    output_path: str,
    known_fixes: list[tuple[str, str]] | None = None,
    enable_stage2: bool = False,
) -> int:
    """1ファイルを処理。修正箇所数を返す"""
    with open(input_path, encoding="utf-8") as f:
        original = f.read()

    cleaned = clean_ruby(original, known_fixes, enable_stage2=enable_stage2)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned)

    # 変更箇所をカウント(行単位)
    orig_lines = original.splitlines()
    clean_lines = cleaned.splitlines()
    changes = sum(1 for a, b in zip(orig_lines, clean_lines) if a != b)
    return changes


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python clean_ruby_text.py <input> [output] [--dict NAME] [--enable-stage2]",
            file=sys.stderr,
        )
        sys.exit(1)

    args = list(sys.argv[1:])

    # --enable-stage2 フラグ抽出
    enable_stage2 = False
    if "--enable-stage2" in args:
        enable_stage2 = True
        args.remove("--enable-stage2")
    # 旧名 --legacy-stage2 も互換のため受け付ける
    if "--legacy-stage2" in args:
        enable_stage2 = True
        args.remove("--legacy-stage2")

    # --dict パラメータを抽出
    dict_name = None
    if "--dict" in args:
        idx = args.index("--dict")
        dict_name = args[idx + 1]
        args = args[:idx] + args[idx + 2 :]

    known_fixes = load_known_fixes(dict_name)
    if dict_name:
        print(f"Loaded {len(known_fixes)} known fixes for '{dict_name}'", file=sys.stderr)
    else:
        if enable_stage2:
            print("No --dict specified; running Stage 2/3 (generic regex) only", file=sys.stderr)
        else:
            print(
                "No --dict and no --enable-stage2: nothing to do (pure copy).\n"
                "Hint: pass --enable-stage2 to clean ruby from pre-v0.12 OCR output.",
                file=sys.stderr,
            )

    input_path = args[0]
    output_path = args[1] if len(args) > 1 else None

    if os.path.isdir(input_path):
        # ディレクトリ一括処理
        if not output_path:
            print("Error: output directory required for batch mode", file=sys.stderr)
            sys.exit(1)
        os.makedirs(output_path, exist_ok=True)
        total_changes = 0
        total_files = 0
        for md_file in sorted(Path(input_path).glob("*.md")):
            out_file = Path(output_path) / md_file.name
            changes = process_file(str(md_file), str(out_file), known_fixes, enable_stage2)
            total_files += 1
            total_changes += changes
            if changes > 0:
                print(f"  {md_file.name}: {changes} lines changed", file=sys.stderr)
        print(f"Processed {total_files} files, {total_changes} total changes", file=sys.stderr)
    else:
        # 単一ファイル処理
        if output_path:
            changes = process_file(input_path, output_path, known_fixes, enable_stage2)
            print(
                f"Cleaned: {input_path} -> {output_path} ({changes} lines changed)",
                file=sys.stderr,
            )
        else:
            with open(input_path, encoding="utf-8") as f:
                text = f.read()
            print(clean_ruby(text, known_fixes, enable_stage2=enable_stage2))


if __name__ == "__main__":
    main()
