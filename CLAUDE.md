# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A terminal-based (TUI) application for conducting systematic literature reviews, built with Textual. Used for PhD dissertation research to screen papers from database searches (ACM, IEEE, etc.).

## Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run python app.py

# Populate database from search directories
uv run python populate_db.py

# Reset database (delete and re-populate)
rm lit_review.db && uv run python populate_db.py
```

## Architecture

**Core Files:**
- `app.py` - Main TUI application with three screens: MainMenuScreen (search selection), ReviewScreen (paper screening), BrowseScreen (filtering/viewing all papers)
- `db_schema.py` - SQLite schema with support for article/inproceedings/inbook types and duplicate detection via DOI
- `populate_db.py` - BibTeX parser that imports papers from `searches/` subdirectories

**Data Flow:**
1. BibTeX files in `searches/<search-name>/` directories are imported via `populate_db.py`
2. Each search directory needs: `*.bib` files, `source.txt` (source name), optionally `serach.md` (query details)
3. Papers are stored in `lit_review.db` with type-specific tables (article, inproceedings, inbook)
4. Duplicate papers (same DOI) across searches are linked via `duplicate_group` table and share a single review

**Review Workflow:**
- Papers have three states: pending (included=NULL), included (True), excluded (False)
- Excluded papers require one or more exclusion codes
- Papers can be tagged with domain (health/environmental) and reference flag
- Random paper selection (`g` key) reduces chronological bias in screening
