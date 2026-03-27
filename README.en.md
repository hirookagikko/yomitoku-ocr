# yomitoku-ocr

**[日本語](README.md)**

Claude Code Skill for OCR-ing Japanese books using [YomiToku](https://github.com/kotaro-kinoshita/yomitoku).

PDF → Markdown OCR → Table extraction → TOC analysis → Chapter splitting — all automated as a single pipeline.

## Features

- **3 modes**: Normal (text-only), Figure (with image extraction), Dual (two-pass for complex layouts)
- **Parallel batch processing**: Split large PDFs into batches for concurrent OCR
- **Auto table extraction**: Detect table-heavy documents and extract structured JSON
- **LLM-based TOC analysis**: Parse table of contents and split into chapters
- **Apple Silicon optimized**: MPS device support (~12s/page on M2 Pro)

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4) or Linux with NVIDIA GPU
- Python 3.10-3.13
- Claude Code CLI

```bash
brew install uv poppler
uv tool install yomitoku --python 3.13

# For table extraction
uv tool install 'yomitoku[extract]' --python 3.13
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
# 1. Pre-cache models (run once, outside Claude Code)
yomitoku --help

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
