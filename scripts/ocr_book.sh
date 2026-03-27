#!/bin/bash
#
# OCR Book Processor - OCRのみ実行
# Usage: ./ocr_book.sh <input_path> [output_dir] [options...]
#
# PDF または 画像ディレクトリをOCR処理し、pages/ にMarkdown出力
# 章分割は /ocr-toc コマンドで別途実行
#
# 対応入力:
#   - PDF: book.pdf
#   - 画像ディレクトリ: book_images/ (png, jpg, jpeg, tiff)
#
# オプション (第3引数以降):
#   --figure          図版を画像として抽出
#   --figure_letter   図版内テキストも含める
#   --dpi <N>         PDF読み込みDPI (デフォルト: 200)
#   --reading_order <mode>  読み順: auto, right2left, left2right, top2bottom
#   --pages <spec>    処理するページ指定 (例: 1-40, 41-80)
#   -v                可視化画像を出力
#
# 並列バッチ実行時の注意:
#   yomitokuは --pages 指定時、実際のページ番号でファイル名を振る
#   （例: --pages 41-43 → {name}_p41.md, {name}_p42.md, {name}_p43.md）。
#   --pages 指定時は一時ディレクトリに出力し、page_NNN.md 形式にリネームしてから
#   pages/ に移動する。これにより後続スクリプト（rebuild_chapters.py等）が
#   統一的な命名規則でページを処理できる。
#

set -e

# 引数チェック
if [ -z "$1" ]; then
    echo "Usage: $0 <input_path> [output_dir] [options...]"
    echo ""
    echo "input_path: PDF file or directory containing images"
    echo ""
    echo "Options:"
    echo "  --figure          Extract figures/images"
    echo "  --figure_letter   Include text within figures"
    echo "  --dpi <N>         PDF DPI (default: 200)"
    echo "  --reading_order <mode>  Reading order: auto, right2left, left2right, top2bottom"
    echo "  -v                Output visualization images"
    exit 1
fi

INPUT_PATH="$1"

# 入力タイプ判定
if [ -d "$INPUT_PATH" ]; then
    # ディレクトリ（画像）
    INPUT_TYPE="images"
    BOOK_NAME=$(basename "$INPUT_PATH")
elif [ -f "$INPUT_PATH" ]; then
    # ファイル（PDF）
    INPUT_TYPE="pdf"
    BOOK_NAME=$(basename "$INPUT_PATH" .pdf)
else
    echo "Error: Input not found: $INPUT_PATH"
    exit 1
fi

# 出力ディレクトリ
if [ -n "$2" ] && [[ "$2" != --* ]] && [[ "$2" != -v ]]; then
    OUTPUT_DIR="$2"
    shift 2
else
    OUTPUT_DIR="ocr_output/$BOOK_NAME"
    shift 1
fi

# 追加オプション解析
EXTRA_OPTS=""
FIGURE_MODE=false
PAGES_SPEC=""
while [ $# -gt 0 ]; do
    case "$1" in
        --figure)
            FIGURE_MODE=true
            shift
            ;;
        --figure_letter)
            EXTRA_OPTS="$EXTRA_OPTS --figure_letter"
            shift
            ;;
        --dpi)
            EXTRA_OPTS="$EXTRA_OPTS --dpi $2"
            shift 2
            ;;
        --reading_order)
            EXTRA_OPTS="$EXTRA_OPTS --reading_order $2"
            shift 2
            ;;
        --pages)
            PAGES_SPEC="$2"
            shift 2
            ;;
        -v)
            EXTRA_OPTS="$EXTRA_OPTS -v"
            shift
            ;;
        *)
            echo "Warning: Unknown option: $1"
            shift
            ;;
    esac
done

# OUTPUT_DIRを絶対パスに変換（--figure_dirのパス解決に必要）
OUTPUT_DIR="$(cd "$(dirname "$OUTPUT_DIR")" 2>/dev/null && pwd)/$(basename "$OUTPUT_DIR")" || OUTPUT_DIR="$(pwd)/$OUTPUT_DIR"

# 図版抽出の設定（絶対パスで指定）
if [ "$FIGURE_MODE" = true ]; then
    FIGURE_DIR="$OUTPUT_DIR/figures"
    mkdir -p "$FIGURE_DIR"
    EXTRA_OPTS="--figure --figure_dir $FIGURE_DIR $EXTRA_OPTS"
fi

# スクリプトディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo "OCR Book Processor"
echo "========================================"
echo "Input:  $INPUT_PATH ($INPUT_TYPE)"
echo "Output: $OUTPUT_DIR"
if [ "$FIGURE_MODE" = true ]; then
echo "Figure: $FIGURE_DIR"
fi
if [ -n "$PAGES_SPEC" ]; then
echo "Pages:  $PAGES_SPEC"
fi
echo "Options:$EXTRA_OPTS"
echo "========================================"

# 入力検証
if [ "$INPUT_TYPE" = "pdf" ]; then
    # PDFサイズチェック（0バイトはDropbox未同期の可能性）
    PDF_SIZE=$(stat -f%z "$INPUT_PATH" 2>/dev/null || stat -c%s "$INPUT_PATH" 2>/dev/null)
    if [ "$PDF_SIZE" -eq 0 ]; then
        echo "Error: PDF file is 0 bytes (possibly not synced from Dropbox)"
        exit 1
    fi
else
    # 画像ディレクトリのファイル数チェック
    IMG_COUNT=$(find "$INPUT_PATH" -maxdepth 1 -type f \( -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.tiff" -o -name "*.PNG" -o -name "*.JPG" -o -name "*.JPEG" \) | wc -l | tr -d ' ')
    if [ "$IMG_COUNT" -eq 0 ]; then
        echo "Error: No image files found in directory: $INPUT_PATH"
        exit 1
    fi
    echo "Found $IMG_COUNT image files"
fi

# 出力ディレクトリ作成
mkdir -p "$OUTPUT_DIR/pages"

# 進捗ログファイル
LOG_FILE="$OUTPUT_DIR/.ocr_progress.log"

echo ""
echo "[OCR] Running yomitoku..."
echo "  Progress logged to: $LOG_FILE"
echo ""

# ネットワーク環境の確認
# yomitoku (huggingface_hub v1.4+) は初回起動時にHuggingFace Hubへ
# config.json のHEADリクエストを送る。リポジトリにconfig.jsonは存在しないため
# 404が返り正常続行するが、ネットワーク遮断時はLocalEntryNotFoundErrorでクラッシュする。
# → サンドボックス環境ではネットワーク制限を解除する必要がある。
# → TMPDIR も /tmp ではなくサンドボックス許可パスに設定する必要がある。
export TMPDIR="${TMPDIR:-/tmp}"

# --pages 指定時: 一時ディレクトリに出力 → page_NNN.md にリネーム → pages/ に移動
# yomitoku は {dirname}_{filename}_pN.md 形式で出力するため、
# パイプライン統一形式 page_NNN.md にリネームする。
if [ -n "$PAGES_SPEC" ]; then
    # ページ範囲からPDFページ番号リストを展開（例: "41-43,45" → "41 42 43 45"）
    PAGE_LIST=()
    IFS=',' read -ra PARTS <<< "$PAGES_SPEC"
    for part in "${PARTS[@]}"; do
        if [[ "$part" == *-* ]]; then
            range_start="${part%-*}"
            range_end="${part#*-}"
            for ((p=range_start; p<=range_end; p++)); do
                PAGE_LIST+=("$p")
            done
        else
            PAGE_LIST+=("$part")
        fi
    done

    # バッチ固有の一時ディレクトリ（PID + ページ範囲で一意にする）
    BATCH_TMPDIR="$OUTPUT_DIR/.batch_tmp_$$_$(echo "$PAGES_SPEC" | tr ',' '_' | tr '-' '_')"
    mkdir -p "$BATCH_TMPDIR"

    echo "[OCR] Pages: $PAGES_SPEC (${#PAGE_LIST[@]} pages)"
    echo "[OCR] Temp dir: $BATCH_TMPDIR"

    # OCR実行（一時ディレクトリに出力）
    yomitoku "$INPUT_PATH" \
        -f md \
        -o "$BATCH_TMPDIR" \
        -d mps \
        --ignore_meta \
        --ignore_line_break \
        --pages "$PAGES_SPEC" \
        $EXTRA_OPTS \
        2>&1 | tee "$LOG_FILE"

    # リネーム: {name}_pN.md → page_NNN.md (パイプライン統一形式)
    # yomitoku は {dirname}_{filename}_pN.md 形式で出力する（Nは実ページ番号）
    echo ""
    echo "[Rename] Normalizing output files to page_NNN.md format..."
    SEQ=0
    for f in $(ls "$BATCH_TMPDIR"/*_p*.md 2>/dev/null | sort); do
        # ファイル名からページ番号を抽出（例: dirname_book_p41.md → 41）
        PAGE_NUM=$(echo "$(basename "$f")" | grep -oE '_p([0-9]+)\.md$' | grep -oE '[0-9]+')
        if [ -n "$PAGE_NUM" ]; then
            PADDED=$(printf "%03d" "$PAGE_NUM")
            DEST="$OUTPUT_DIR/pages/page_${PADDED}.md"
            mv "$f" "$DEST"
            echo "  $(basename "$f") -> page_${PADDED}.md"
            SEQ=$((SEQ + 1))
        fi
    done

    # figure画像も同様にリネーム（存在する場合）
    if [ -d "$BATCH_TMPDIR" ]; then
        for f in $(ls "$BATCH_TMPDIR"/*.png "$BATCH_TMPDIR"/*.jpg 2>/dev/null); do
            # figure画像はそのまま移動（ファイル名にページ情報が含まれている場合がある）
            mv "$f" "$OUTPUT_DIR/pages/" 2>/dev/null || true
        done
    fi

    # 一時ディレクトリ削除
    rm -rf "$BATCH_TMPDIR"
    echo "[Rename] Done. $SEQ files moved to pages/"

else
    # 通常モード（全ページ処理、直接 pages/ に出力）
    yomitoku "$INPUT_PATH" \
        -f md \
        -o "$OUTPUT_DIR/pages" \
        -d mps \
        --ignore_meta \
        --ignore_line_break \
        $EXTRA_OPTS \
        2>&1 | tee "$LOG_FILE"
fi

# OCR完了フラグ
touch "$OUTPUT_DIR/.ocr_complete"

echo ""
echo "========================================"
echo "OCR Complete!"
echo "========================================"
echo "Output: $OUTPUT_DIR/pages/"
echo ""
echo "Next step: Run /ocr-toc to analyze TOC and split chapters"
echo "========================================"
