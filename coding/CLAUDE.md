# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A web application for qualitative coding of PDF papers as part of a systematic literature review for a PhD dissertation. Built for a single user (the researcher). The app handles Phase 3 full-text screening and qualitative coding of papers that passed earlier screening phases.

**Core workflow:** Read PDF papers, highlight text or draw areas, tag annotations with codes, fill in a synthesis matrix, and make include/exclude screening decisions.

## Commands

```bash
# Install dependencies
uv sync

# Run the application (port 5001)
uv run python app.py

# Reset database (WARNING: drops all coding data)
rm lit_review.db && cp ../lit_review.db . && uv run python app.py
```

## Architecture

**Stack:** Flask + SQLite + Alpine.js + DaisyUI (Tailwind CSS) + PDF.js. No build step — all frontend deps loaded via CDN.

**Single-page app** served by Flask at `/`. All data flows through JSON API endpoints. PDF.js renders PDFs client-side.

### Key Files

| File | Purpose |
|------|---------|
| `app.py` | Flask routes — pages, API endpoints |
| `db.py` | Database queries — all SQLite access |
| `schema.py` | Table creation and migrations (runs on startup) |
| `templates/index.html` | The entire SPA — Alpine.js + DaisyUI components |
| `static/js/app.js` | Alpine.js app logic — state, methods, PDF rendering |
| `static/css/app.css` | Custom styles (PDF layers, modes, resize handles) |
| `static/icons.svg` | Heroicons v2.1.5 SVG sprite sheet |

### Database

Shares `lit_review.db` with the sibling `lit-review/` TUI app. This app reads existing tables (`document`, `article`, `inproceedings`, `inbook`, `pass_review`, `exclusion_code`) and adds its own:

- `code` — Hierarchical tags. Top-level codes (parent_id=NULL) = matrix columns. Sub-codes = dropdown options in matrix cells.
- `annotation` — Highlighted text or drawn areas on PDFs. Types: `highlight`, `note`, `area`.
- `annotation_code` — Many-to-many junction linking annotations to codes, with optional relationship notes.
- `matrix_cell` — Synthesis values per paper x top-level code. Evidence comes from annotations.
- `document_pdf` — Tracks uploaded PDF files per document.

Phase 3 screening reuses `pass_review` with `pass_number=3`.

### Frontend Architecture

**Alpine.js** manages all state in a single `app` data object on `<body>`. Key state groups:

- **Papers**: `papers[]`, `selectedPaperId`, `selectedPaper`, search/filter state
- **PDF**: `pdfScale`, `pdfMode` (hand/text/box), page tracking. PDF.js document stored outside Alpine (`_pdfDoc`) to avoid Proxy issues with private class fields.
- **Annotations**: `paperAnnotations[]`, `selectedAnnotation`, creation toolbar state
- **Codes**: `codes[]` (tree), `codeUsageCounts`, code picker state
- **Matrix Columns**: `matrixColumns[]`, `paperMatrixCells`, column editor state
- **Themes**: `selectedThemeCodeId`, `themesAnnotations[]`
- **UI**: `view` (papers/matrix/themes), `theme`, `sidebarOpen`, panel widths, `rightTab`

**PDF.js** loaded dynamically via `import()`. Pages rendered to `<canvas>` with a `textLayer` overlay for text selection and an `annotationLayer` for highlight rendering. Coordinates stored in PDF user space, converted to/from viewport on render.

**Three PDF interaction modes:**
- **Hand (H)**: Pan/drag to scroll, double-click to fit-width
- **Text (T)**: Select text to create highlight annotations
- **Box (B)**: Draw rectangles for area annotations

### Data Model

Codes and matrix columns are **independent concepts**:

```
code (hierarchical tags for annotation)
  ├── top-level code (e.g., "Challenges", "Application Framing")
  │     ├── sub-code
  │     └── sub-code
  └── top-level code

annotation (on PDF)
  ├── annotation_code → code (with relationship note)
  └── annotation_code → code

matrix_column (independent of codes)
  ├── column_type: enum_single | enum_multi | text
  ├── matrix_column_option → dropdown/checkbox values
  └── matrix_column_code → linked codes (for evidence tracking)

matrix_cell (paper × column → value)
  └── evidence: annotations tagged with codes linked to this column
```

## API Routes

### Papers & Screening
- `GET /api/papers?search=&status=` — Filtered paper list
- `GET /api/papers/<id>` — Single paper with Phase 3 review
- `POST /api/papers/<id>/review` — Save include/exclude decision
- `GET /api/exclusion-codes` — List exclusion codes
- `GET /api/stats` — Phase 3 progress counts

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

## Key Patterns

### PDF.js + Alpine.js Proxy Issue
PDF.js objects use private class fields (`#field`) which break through Alpine's Proxy wrappers. The PDF document is stored in a plain variable (`_pdfDoc`) outside Alpine's reactive state.

### Coordinate System
Annotation rects stored in PDF user space (72 DPI). Converted to/from viewport using `viewport.convertToPdfPoint()` and `viewport.convertToViewportPoint()`. Each rect includes a `page` number for multi-page annotations.

### Text Layer
Uses PDF.js v5 `TextLayer` class with CSS custom properties `--scale-factor` and `--scale-round-x/y`. The `.textLayer` class is custom CSS (not the official `pdf_viewer.css`).

### HTML Tag Closing
When editing multi-line HTML tags in `index.html`, ensure the closing `>` is preserved. This has been a recurring source of bugs where attributes on new lines cause the tag to be left unclosed.

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

- **Bug fixes**: Check browser console for errors. Common issues: missing `>` on multi-line HTML tags, Alpine Proxy issues with PDF.js, DaisyUI dropdown z-index problems.
- **New features**: Follow existing patterns — add db.py function, app.py route, then Alpine method + HTML template.
- **Code picker**: Used in two places (annotation creation toolbar and annotation detail view). Both use `codes` tree with `codeMatchesSearch`/`subCodeMatchesSearch` filters.
- **Annotations**: Backend supports all CRUD. Frontend creates via text selection (text mode) or rectangle drawing (box mode). Overlays rendered in `renderAnnotationOverlays()`.
