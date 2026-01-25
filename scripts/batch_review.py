#!/usr/bin/env python3
"""Batch LLM review script for processing multiple papers."""

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_schema import DB_PATH, init_db
from llm_assistant import LLMAssistant, LLMSuggestion


def get_searches(conn: sqlite3.Connection) -> list[tuple[int, str, int]]:
    """Get all searches with document counts."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.source, COUNT(d.id) as total
        FROM search s
        LEFT JOIN document d ON d.search_id = s.id
        GROUP BY s.id
    """)
    return [(row['id'], row['source'], row['total']) for row in cursor.fetchall()]


def get_documents_for_batch(
    conn: sqlite3.Connection,
    search_id: int | None,
    pass_number: int,
    unreviewed_only: bool = True,
) -> list[dict]:
    """Get documents for batch processing.

    Args:
        conn: Database connection
        search_id: Optional search ID filter (None for all)
        pass_number: 1 or 2
        unreviewed_only: If True, only get documents without existing review
    """
    cursor = conn.cursor()

    # Build query based on pass number
    if pass_number == 1:
        base_query = """
            SELECT
                d.id, d.title,
                COALESCE(a.year, i.year, ib.year) as year,
                COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
                COALESCE(a.journal, i.booktitle, ib.booktitle) as venue,
                COALESCE(a.abstract, i.abstract, ib.abstract) as abstract
            FROM document d
            LEFT JOIN article a ON a.document_id = d.id
            LEFT JOIN inproceedings i ON i.document_id = d.id
            LEFT JOIN inbook ib ON ib.document_id = d.id
        """
        conditions = []

        if search_id is not None:
            conditions.append(f"d.search_id = {search_id}")

        if unreviewed_only:
            conditions.append("""
                NOT EXISTS (
                    SELECT 1 FROM pass_review pr
                    WHERE pr.document_id = d.id AND pr.pass_number = 1
                    AND pr.llm_suggestion IS NOT NULL
                )
            """)

    else:  # pass_number == 2
        # Only process documents that passed Pass 1
        base_query = """
            SELECT
                d.id, d.title,
                COALESCE(a.year, i.year, ib.year) as year,
                COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
                COALESCE(a.journal, i.booktitle, ib.booktitle) as venue,
                COALESCE(a.abstract, i.abstract, ib.abstract) as abstract
            FROM document d
            LEFT JOIN article a ON a.document_id = d.id
            LEFT JOIN inproceedings i ON i.document_id = d.id
            LEFT JOIN inbook ib ON ib.document_id = d.id
            JOIN pass_review pr1 ON pr1.document_id = d.id AND pr1.pass_number = 1
        """
        conditions = ["pr1.decision IN ('include', 'uncertain')"]

        if search_id is not None:
            conditions.append(f"d.search_id = {search_id}")

        if unreviewed_only:
            conditions.append("""
                NOT EXISTS (
                    SELECT 1 FROM pass_review pr2
                    WHERE pr2.document_id = d.id AND pr2.pass_number = 2
                    AND pr2.llm_suggestion IS NOT NULL
                )
            """)

    if conditions:
        query = base_query + " WHERE " + " AND ".join(conditions)
    else:
        query = base_query

    query += " ORDER BY d.id"

    cursor.execute(query)
    documents = []
    for row in cursor.fetchall():
        documents.append({
            'id': row['id'],
            'title': row['title'],
            'year': row['year'],
            'keywords': row['keywords'],
            'venue': row['venue'],
            'abstract': row['abstract'],
        })

    return documents


def save_llm_suggestion(
    conn: sqlite3.Connection,
    document_id: int,
    pass_number: int,
    suggestion: LLMSuggestion,
) -> None:
    """Save LLM suggestion to pass_review table."""
    cursor = conn.cursor()

    # Serialize suggestion
    llm_json = json.dumps({
        "decision": suggestion.decision,
        "reasoning": suggestion.reasoning,
        "confidence": suggestion.confidence,
        "exclusion_codes": suggestion.exclusion_codes,
        "raw_response": suggestion.raw_response,
        "error": suggestion.error,
        "domain": suggestion.domain,
        "model": suggestion.model,
        "thinking_mode": suggestion.thinking_mode,
        "response_time_ms": suggestion.response_time_ms,
        "requested_at": suggestion.requested_at,
    })

    # Insert or update (only llm_suggestion field)
    cursor.execute("""
        INSERT INTO pass_review (document_id, pass_number, llm_suggestion, llm_request_log_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(document_id, pass_number) DO UPDATE SET
            llm_suggestion = excluded.llm_suggestion,
            llm_request_log_id = excluded.llm_request_log_id
    """, (document_id, pass_number, llm_json, suggestion.log_id))

    conn.commit()


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    """Get LLM settings from database."""
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    return {row['key']: row['value'] for row in cursor.fetchall()}


async def process_batch(
    documents: list[dict],
    pass_number: int,
    host: str,
    model: str,
    thinking_mode: bool,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Process a batch of documents.

    Returns: (processed, errors, skipped)
    """
    if dry_run:
        print(f"\n[DRY RUN] Would process {len(documents)} documents\n")
        for i, doc in enumerate(documents[:10]):  # Show first 10
            title = doc['title'] or 'No title'
            if len(title) > 60:
                title = title[:57] + "..."
            print(f"  {i+1}. [{doc['id']}] {title}")
        if len(documents) > 10:
            print(f"  ... and {len(documents) - 10} more")
        return 0, 0, len(documents)

    # Initialize connection for saving
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    assistant = LLMAssistant(host=host, model=model)

    processed = 0
    errors = 0
    total = len(documents)

    print(f"\nProcessing {total} documents for Pass {pass_number}...\n")

    for i, doc in enumerate(documents):
        title = doc['title'] or 'No title'
        if len(title) > 50:
            title = title[:47] + "..."

        # Progress indicator
        progress = f"[{i+1}/{total}]"
        print(f"{progress} Processing: {title}... ", end="", flush=True)

        try:
            if pass_number == 1:
                suggestion = await assistant.suggest_pass1(
                    document_id=doc['id'],
                    title=doc['title'] or "",
                    year=doc['year'],
                    keywords=doc['keywords'],
                    venue=doc['venue'],
                    thinking_mode=thinking_mode,
                )
            else:
                suggestion = await assistant.suggest_pass2(
                    document_id=doc['id'],
                    title=doc['title'] or "",
                    year=doc['year'],
                    keywords=doc['keywords'],
                    venue=doc['venue'],
                    abstract=doc['abstract'],
                    thinking_mode=thinking_mode,
                )

            # Save suggestion
            save_llm_suggestion(conn, doc['id'], pass_number, suggestion)

            if suggestion.error:
                print(f"ERROR: {suggestion.error}")
                errors += 1
            else:
                decision_emoji = {
                    'include': '+',
                    'exclude': '-',
                    'uncertain': '?',
                }.get(suggestion.decision, '?')
                print(f"{decision_emoji} ({suggestion.confidence:.0%})")
                processed += 1

        except Exception as e:
            print(f"FAILED: {e}")
            errors += 1

    conn.close()

    print(f"\nCompleted: {processed} processed, {errors} errors")
    return processed, errors, 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch LLM review for literature screening"
    )
    parser.add_argument(
        "--pass", "-p",
        dest="pass_number",
        type=int,
        choices=[1, 2],
        required=True,
        help="Pass number (1 or 2)"
    )
    parser.add_argument(
        "--search-id", "-s",
        type=int,
        help="Search ID to process (omit for all searches)"
    )
    parser.add_argument(
        "--all-searches", "-a",
        action="store_true",
        help="Process all searches"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Show what would be processed without making LLM requests"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all documents (including those with existing suggestions)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Limit number of documents to process"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.search_id is None and not args.all_searches:
        print("Error: Must specify --search-id or --all-searches")
        sys.exit(1)

    # Initialize database
    conn = init_db()

    # Get settings
    settings = get_settings(conn)
    host = settings.get('llm_host', 'http://localhost:11434')
    model = settings.get('llm_model', 'qwen3:8b')
    thinking_mode = settings.get('llm_thinking_mode', 'true') == 'true'

    print(f"LLM Configuration:")
    print(f"  Host: {host}")
    print(f"  Model: {model}")
    print(f"  Thinking Mode: {thinking_mode}")

    # Get documents
    search_id = None if args.all_searches else args.search_id
    unreviewed_only = not args.all

    documents = get_documents_for_batch(
        conn, search_id, args.pass_number, unreviewed_only
    )

    if args.limit:
        documents = documents[:args.limit]

    if not documents:
        print(f"\nNo documents to process for Pass {args.pass_number}")
        if unreviewed_only:
            print("(Use --all to include documents with existing suggestions)")
        conn.close()
        return

    # Show search info
    if args.all_searches:
        searches = get_searches(conn)
        print(f"\nSearches:")
        for sid, source, total in searches:
            print(f"  [{sid}] {source}: {total} documents")
    elif args.search_id:
        cursor = conn.cursor()
        cursor.execute("SELECT source FROM search WHERE id = ?", (args.search_id,))
        row = cursor.fetchone()
        if row:
            print(f"\nSearch: {row['source']}")

    print(f"\nFound {len(documents)} documents to process")

    conn.close()

    # Run batch processing
    asyncio.run(process_batch(
        documents,
        args.pass_number,
        host,
        model,
        thinking_mode,
        args.dry_run,
    ))


if __name__ == "__main__":
    main()
