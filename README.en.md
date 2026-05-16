# yomitoku-ocr

**[日本語](README.md)**

Claude Code Skill for OCR-ing Japanese books using [YomiToku](https://github.com/kotaro-kinoshita/yomitoku).

PDF → Markdown OCR → Table extraction → TOC analysis → Chapter splitting — all automated as a single pipeline.

## Features

- **4 modes**: Normal / Figure / Dual (two-pass) / Dictionary (`--ignore_ruby` + residual cleanup)
- **Parallel batch processing**: Split large PDFs into batches for concurrent OCR. Since v0.12.1's lazy `load_pdf`, single-process whole-book runs are also practical.
- **Auto table extraction**: Detect table-heavy documents and extract structured JSON
- **LLM-based TOC analysis**: Parse table of contents and split into chapters
- **Tracks YomiToku v0.13.0**: enhanced detection & handwriting recognition models, `--ignore_ruby`, `--dpi`, `--pages`, etc.

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4) or Linux with NVIDIA GPU
- Python 3.10-3.13, PyTorch 2.6+
- YomiToku **v0.13.0** or later
- macOS 14.0+ for MPS. On macOS 26 (Tahoe), PyTorch 2.12 reports `MPS available=False`, so the skill falls back to CPU (`--lite -d cpu`).
- Claude Code CLI

```bash
brew install uv poppler

# Under a SOCKS proxy (Cloudflare WARP, Mullvad, etc.) you must bundle httpx[socks]
uv tool install 'yomitoku[extract]' --with 'httpx[socks]' --python 3.13

# Already installed with an older version?
uv tool install 'yomitoku[extract]' --with 'httpx[socks]' --reinstall --python 3.13
# or simply
uv tool upgrade yomitoku
```

First run downloads ~630MB of models from HuggingFace Hub. Prefetch them outside the sandbox once to avoid `PermissionError` later:

```bash
download_model
```

## Installation

```bash
cd ~/.claude/skills/
git clone https://github.com/hirookagikko/yomitoku-ocr.git
```

## Usage

Once installed, Claude Code will automatically use this skill when you ask it to OCR a book or PDF.

Example prompts:
- "This PDF book, OCR it and split into chapters"
- "Digitize this book with figure extraction"
- "OCR this dictionary and drop the ruby" (Dictionary mode = `--ignore_ruby` + residual cleanup)
- "OCR this PDF to Markdown"

## Structure

```
yomitoku-ocr/
├── SKILL.md              # Skill entry point
├── agents/               # Pipeline step definitions
│   ├── ocr-pipeline.md   # Orchestrator
│   ├── ocr-book.md       # OCR execution
│   ├── ocr-toc.md        # TOC analysis + chapter split
│   └── ocr-extract.md    # Table extraction
├── scripts/              # Automation scripts
│   ├── ocr_book.sh       # OCR driver
│   ├── rebuild_chapters.py
│   ├── scan_tables.py
│   └── ...
└── references/           # Detailed documentation
    ├── API_REFERENCE.md
    ├── CLI_REFERENCE.md
    └── ...
```

## Output

```
ocr_output/{book_name}/
├── README.md          # TOC with links
├── chapters/          # Chapter-level Markdown
├── pages/             # Page-level OCR output
├── _extractions/      # Structured table data (if applicable)
└── chapter_override.json
```

## Sandbox Setup

YomiToku downloads models (~630MB) from HuggingFace Hub on first run and sends a HEAD request on each startup.

### Recommended: Pre-cache models + allowedHosts

```bash
# 1. Pre-cache models (run once, outside Claude Code).
#    v0.12.0+ provides a dedicated command:
download_model

# 2. Add HuggingFace to sandbox allowedHosts in your settings
# ~/.claude/settings.local.json:
```

```json
{
  "sandbox": {
    "allowedHosts": ["huggingface.co", "*.hf.co"]
  }
}
```

### Fallback

If the above doesn't work, use `dangerouslyDisableSandbox: true` as a last resort. The `/tmp` issue is already handled via `$TMPDIR` in the scripts.

## License

This skill (scripts, agent definitions, documentation) is licensed under MIT.

Note: [YomiToku](https://github.com/kotaro-kinoshita/yomitoku) itself is licensed under **CC BY-NC-SA 4.0**. Commercial use requires a separate license. See the YomiToku repository for details.
