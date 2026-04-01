# Lit Review Coding

A desktop web application for qualitative coding of PDF papers as part of a systematic literature review. Built for a single researcher conducting Phase 3 full-text screening and coding.

## What it does

- **PDF viewing** with text highlighting and area annotation tools
- **Qualitative coding** with hierarchical codes and relationship notes (markdown)
- **Synthesis matrix** for structured data extraction across papers
- **Themes view** for cross-paper analysis by code
- **Per-paper LLM chat** (Ollama/Claude) with PDF context
- **Screening decisions** (include/exclude/uncertain) with exclusion codes
- **Paper notes** (markdown) for general observations per paper

## Stack

- **Backend:** Python, Flask, SQLite
- **Frontend:** Vue 3, Pinia, Vite, Tailwind CSS, DaisyUI 4, PDF.js
- **Desktop:** pywebview (optional — also works in browser)
- **LLM:** Ollama (local) or Claude (API)

## Setup

```bash
# Python dependencies
uv sync

# Frontend dependencies
cd frontend && npm install
```

## Running

### Development (hot reload)

```bash
# Terminal 1: API server
uv run python app.py

# Terminal 2: Frontend dev server
cd frontend && npm run dev
```

Open `http://localhost:5173`

### Production / Desktop

```bash
# Build frontend
cd frontend && npm run build

# Run as desktop app
uv run python app.py --desktop

# Or run in browser
uv run python app.py
# Open http://localhost:5001
```

### Desktop with hot reload

```bash
cd frontend && npm run dev &
uv run python app.py --desktop --dev-url http://localhost:5173
```

## Database

Shares `lit_review.db` with the sibling TUI screening app (`../lit-review/`). Papers are imported there; this app adds coding tables on first run.

To reset coding data (keeps papers):

```bash
rm lit_review.db && cp ../lit_review.db .
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `H` | Hand (pan) mode |
| `T` | Text select mode |
| `B` | Box draw mode |
| `←` / `J` | Previous paper |
| `→` / `K` | Next paper |
| `Ctrl+S` | Save review |
| `Esc` | Close dialog/picker |

## Views

- **Papers** — 3-column layout: paper list, PDF viewer, detail panel (metadata, screening, annotations, matrix cells)
- **Matrix** — Full spreadsheet: papers × columns with inline editing and evidence counts
- **Themes** — Cross-paper view: select a code, see all annotations tagged with it across papers, with a detail panel for paper context
