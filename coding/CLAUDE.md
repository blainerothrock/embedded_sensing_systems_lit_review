# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A web application for qualitative coding of PDF papers as part of a systematic literature review for a PhD dissertation. Built for a single user (the researcher). The app handles Phase 3 full-text screening and qualitative coding of papers that passed earlier screening phases.

**Core workflow:** Read PDF papers, highlight text or draw areas, tag annotations with codes, write notes (markdown), fill in a synthesis matrix, and make include/exclude screening decisions.

## Commands

```bash
# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && npm install

# Development (two terminals)
uv run python app.py                    # Flask API on :5001
cd frontend && npm run dev              # Vite HMR on :5173

# Production build + desktop app
cd frontend && npm run build            # outputs to static/dist/
uv run python app.py --desktop          # pywebview window

# Desktop with Vite dev server (hot reload)
cd frontend && npm run dev &
uv run python app.py --desktop --dev-url http://localhost:5173

# Reset database (WARNING: drops all coding data)
rm lit_review.db && cp ../lit_review.db . && uv run python app.py
```

## Architecture

**Stack:** Flask (Python) + SQLite + Vue 3 + Pinia + Vite + DaisyUI 4 (Tailwind CSS 3) + PDF.js

**Frontend** is a Vue 3 SPA in `frontend/` built with Vite. In production, Vite outputs to `static/dist/` and Flask serves `index.html`. In development, Vite dev server on :5173 proxies `/api/*` to Flask on :5001.

**Backend** is a Flask JSON API. No server-side rendering.

### Key Files

| File | Purpose |
|------|---------|
| `app.py` | Flask routes — API endpoints, serves built Vue app |
| `db.py` | Database queries — all SQLite access |
| `schema.py` | Table creation and migrations (runs on startup) |
| `llm.py` | LLM provider abstraction (Ollama, Claude) |
| `frontend/` | Vue 3 SPA source (see Frontend Architecture below) |
| `static/dist/` | Vite build output (gitignored) |

### Frontend Architecture

```
frontend/
├── src/
│   ├── main.js              # Vue app bootstrap + Pinia
│   ├── App.vue              # Root — navbar, view switching, keyboard shortcuts
│   ├── stores/              # Pinia stores (Composition API)
│   │   ├── workspace.js     # Papers, annotations, review, paper notes
│   │   ├── codebook.js      # Hierarchical codes
│   │   ├── matrix.js        # Matrix columns, cells, debounced saves
│   │   ├── chat.js          # LLM chat with SSE streaming
│   │   └── ui.js            # View, theme, layout, toasts
│   ├── composables/
│   │   ├── usePdf.js        # PDF.js with shallowRef (avoids Proxy issues)
│   │   ├── useKeyboard.js   # Global shortcuts (H/T/B, arrows, Escape, Cmd+S)
│   │   └── useDebounce.js   # Debounce utility
│   ├── components/
│   │   ├── AppNavbar.vue           # View tabs, paper nav, toolbar actions
│   │   ├── WorkspaceLayout.vue     # 3-column resizable layout
│   │   ├── PaperList.vue           # Search, filter, paper list
│   │   ├── PaperListItem.vue       # Single paper row
│   │   ├── PdfViewer.vue           # PDF.js canvas, text/box selection, overlays
│   │   ├── PdfToolbar.vue          # Mode buttons, zoom, page indicator
│   │   ├── DetailPanel.vue         # Right sidebar: metadata, tabs, paper notes
│   │   ├── PaperDetails.vue        # Authors, venue, abstract, keywords
│   │   ├── ScreeningPanel.vue      # Include/exclude decision + notes
│   │   ├── AnnotationList.vue      # Annotation detail + list view
│   │   ├── RichTextEditor.vue      # Markdown textarea + rendered preview
│   │   ├── CodeSelector.vue        # Reusable hierarchical code picker
│   │   ├── MatrixView.vue          # Full matrix table view
│   │   ├── ThemesView.vue          # Cross-paper annotation view by code
│   │   ├── ChatPanel.vue           # LLM chat with SSE streaming
│   │   ├── CodeBuilderModal.vue    # Code CRUD modal
│   │   ├── ColumnEditorModal.vue   # Matrix column CRUD modal
│   │   └── ToastContainer.vue      # Notification toasts
│   └── api/
│       └── index.js          # Centralized fetch wrapper for all endpoints
├── vite.config.js            # Vite config with Flask proxy
├── tailwind.config.js        # Tailwind + DaisyUI theme (dark/light)
└── package.json
```

### Database

Shares `lit_review.db` with the sibling `lit-review/` TUI app. This app reads existing tables (`document`, `article`, `inproceedings`, `inbook`, `pass_review`, `exclusion_code`) and adds its own:

- `code` — Hierarchical tags. Top-level codes with sub-codes.
- `annotation` — Highlighted text or drawn areas on PDFs. Types: `highlight`, `note`, `area`.
- `annotation_code` — Many-to-many junction linking annotations to codes, with optional relationship notes.
- `matrix_column` — Column definitions with type (enum_single, enum_multi, text) and linked codes.
- `matrix_column_option` — Dropdown/checkbox values for enum columns.
- `matrix_column_code` — Links columns to codes for evidence tracking.
- `matrix_cell` — Synthesis values per paper x column.
- `document_pdf` — Tracks uploaded PDF files per document.
- `paper_note` — Per-paper markdown notes (separate from review notes).
- `paper_chat` / `chat_message` — LLM conversation history per paper.

Phase 3 screening reuses `pass_review` with `pass_number=3`.

### Data Model

```
code (hierarchical tags for annotation)
  ├── top-level code (e.g., "Challenges", "Application Framing")
  │     ├── sub-code (with description for LLM context)
  │     └── sub-code
  └── top-level code

annotation (on PDF)
  ├── annotation_code → code (with relationship note, markdown)
  └── note (markdown)

matrix_column (independent of codes)
  ├── column_type: enum_single | enum_multi | text
  ├── matrix_column_option → dropdown/checkbox values
  └── matrix_column_code → linked codes (for evidence tracking)

matrix_cell (paper × column → value)
  └── evidence: annotations tagged with codes linked to this column

paper_note (per-paper markdown notes)
```

## API Routes

### Papers & Screening
- `GET /api/papers?search=&status=` — Filtered paper list
- `GET /api/papers/<id>` — Single paper with Phase 3 review
- `POST /api/papers/<id>/review` — Save include/exclude decision
- `GET /api/exclusion-codes` — List exclusion codes
- `GET /api/stats` — Phase 3 progress counts

### Paper Notes
- `GET /api/papers/<id>/notes` — Get paper-level markdown notes
- `PUT /api/papers/<id>/notes` — Save paper-level notes

### PDF
- `POST /api/papers/<id>/upload-pdf` — Upload PDF file
- `GET /api/papers/<id>/pdf` — Serve PDF

### Codes
- `GET /api/codes` — Hierarchical code tree
- `POST /api/codes` — Create code (send `parent_id` for sub-codes)
- `PUT /api/codes/<id>` — Update name, description, color, sort_order
- `DELETE /api/codes/<id>` — Delete (fails if has annotations or children)
- `GET /api/codes/usage` — Annotation count per code

### Annotations
- `GET /api/papers/<id>/annotations` — All annotations with codes
- `POST /api/papers/<id>/annotations` — Create with `rects_json`, optional `code_ids`
- `PUT /api/annotations/<id>` — Update note, color, text, rects
- `DELETE /api/annotations/<id>` — Delete with cascade
- `POST /api/annotations/<id>/codes/<code_id>` — Tag annotation
- `PUT /api/annotations/<id>/codes/<code_id>/note` — Update relationship note
- `DELETE /api/annotations/<id>/codes/<code_id>` — Untag

### Matrix Columns
- `GET /api/matrix-columns` — All columns with options and linked codes
- `POST /api/matrix-columns` — Create column (name, column_type, description, color)
- `PUT /api/matrix-columns/<id>` — Update column
- `DELETE /api/matrix-columns/<id>` — Delete column and its cells/options/links
- `POST /api/matrix-columns/<id>/options` — Add enum option
- `DELETE /api/matrix-column-options/<id>` — Delete option
- `POST /api/matrix-columns/<id>/codes/<code_id>` — Link code for evidence
- `DELETE /api/matrix-columns/<id>/codes/<code_id>` — Unlink code

### Matrix Data
- `GET /api/matrix` — Papers x columns with cell values and evidence counts
- `POST /api/matrix/cell` — Save cell value (document_id, column_id, value)
- `GET /api/papers/<id>/matrix-cells` — Cells for a single paper
- `GET /api/coding/completeness` — Matrix fill status per paper

### Themes & Summary
- `GET /api/themes/<code_id>` — Annotations for a code across all papers
- `GET /api/papers/<id>/summary` — Annotations grouped by code for a paper

### Chat
- `GET /api/papers/<id>/chats` — List chat sessions for a paper
- `POST /api/papers/<id>/chats` — Create chat session
- `GET /api/chats/<id>/messages` — Get messages for a chat
- `DELETE /api/chats/<id>` — Delete chat session
- `POST /api/papers/<id>/chat` — Send message (SSE streaming response)
- `GET /api/llm/models` — Available LLM models

## Key Patterns

### PDF.js + Vue Proxy Issue
PDF.js objects use private class fields (`#field`) which break through Vue's reactive Proxy wrappers. The `usePdf` composable uses `shallowRef()` for `pdfDoc` and `pageViewports` to avoid deep proxying.

### Coordinate System
Annotation rects stored in PDF user space (72 DPI). Converted to/from viewport using `viewport.convertToPdfPoint()` and `viewport.convertToViewportPoint()`. Each rect includes a `page` number for multi-page annotations.

### Rich Text Editing
Notes (paper notes, annotation notes, code-annotation notes) use the `RichTextEditor` component: plain markdown textarea for editing (monospace font), rendered markdown for display. Click to edit, blur or Cmd+S to save. No WYSIWYG — the user prefers raw markdown editing.

### Custom Compact Collapsible
DaisyUI's built-in collapse has layout issues with compact single-line headers (arrow misaligned, wasted space). Use the custom `compact-collapse` CSS pattern instead: hidden checkbox + label + `grid-template-rows` animation. See `app.css`.

### Text Layer
Uses PDF.js `TextLayer` class with CSS custom properties `--scale-factor` and `--scale-round-x/y`. The `.textLayer` class is custom CSS (not the official `pdf_viewer.css`).

### Keyboard Shortcut Safety
`useKeyboard.js` checks `e.target.isContentEditable` and `e.target.closest('[contenteditable]')` in addition to standard form elements, preventing shortcuts from firing during rich text editing.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| H | Hand (pan) mode |
| T | Text select mode |
| B | Box select mode |
| ← or J | Previous paper |
| → or K | Next paper |
| Ctrl/Cmd+S | Save review |
| Escape | Close active dialog/picker (cascading) |

## How to Help

- **Bug fixes**: Check browser console for errors. Common issues: Vue reactivity with PDF.js objects (use `shallowRef`), DaisyUI class differences between v4/v5.
- **New features**: Add `db.py` function → `app.py` route → API wrapper in `api/index.js` → Pinia store action → Vue component.
- **Notes/text editing**: Use `RichTextEditor` component. Store markdown, render with `marked`. No WYSIWYG.
- **Collapsible sections**: Use the custom `compact-collapse` CSS pattern, not DaisyUI's collapse component.
- **Annotations**: Backend supports all CRUD. Frontend creates via text selection (text mode) or rectangle drawing (box mode). Overlays rendered imperatively by `usePdf.renderAnnotationOverlays()`.
