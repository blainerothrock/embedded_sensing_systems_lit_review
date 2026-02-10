#!/usr/bin/env python3
"""Sync prompt files to database with versioning."""

import hashlib
import re
import sqlite3
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_schema import DB_PATH, init_db


def parse_prompt_file(file_path: Path) -> tuple[str, str] | None:
    """Parse a prompt markdown file with YAML frontmatter.

    Returns (prompt_name, content) or None if invalid.
    """
    content = file_path.read_text()

    # Parse YAML frontmatter (between --- markers)
    frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
    if not frontmatter_match:
        return None

    frontmatter = frontmatter_match.group(1)
    body = frontmatter_match.group(2).strip()

    # Extract name from frontmatter
    name_match = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
    if not name_match:
        return None

    prompt_name = name_match.group(1).strip()
    return prompt_name, body


def compute_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def get_latest_version(conn: sqlite3.Connection, prompt_name: str) -> tuple[int, str] | None:
    """Get the latest version of a prompt.

    Returns (id, content_hash) or None if not found.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, content_hash
        FROM prompt_version
        WHERE prompt_name = ?
        ORDER BY id DESC
        LIMIT 1
    """, (prompt_name,))
    row = cursor.fetchone()
    return (row['id'], row['content_hash']) if row else None


def insert_prompt_version(
    conn: sqlite3.Connection,
    prompt_name: str,
    content: str,
    content_hash: str
) -> int:
    """Insert a new prompt version and return its ID."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO prompt_version (prompt_name, content, content_hash)
        VALUES (?, ?, ?)
    """, (prompt_name, content, content_hash))
    conn.commit()
    return cursor.lastrowid


def main() -> None:
    """Sync all prompt files to database."""
    prompts_dir = Path(__file__).parent.parent / "prompts"

    if not prompts_dir.exists():
        print(f"Error: prompts directory not found at {prompts_dir}")
        sys.exit(1)

    # Initialize database (ensures tables exist)
    conn = init_db()

    prompt_files = list(prompts_dir.glob("*.md"))
    if not prompt_files:
        print("No prompt files found in prompts/")
        sys.exit(1)

    print(f"Processing {len(prompt_files)} prompt files...\n")

    updated = 0
    unchanged = 0
    errors = 0

    for file_path in sorted(prompt_files):
        result = parse_prompt_file(file_path)
        if result is None:
            print(f"  {file_path.name} -> ERROR (invalid format)")
            errors += 1
            continue

        prompt_name, content = result
        content_hash = compute_hash(content)

        latest = get_latest_version(conn, prompt_name)

        if latest is None:
            # New prompt
            new_id = insert_prompt_version(conn, prompt_name, content, content_hash)
            print(f"  {file_path.name} -> NEW (id={new_id})")
            updated += 1
        elif latest[1] != content_hash:
            # Content changed
            new_id = insert_prompt_version(conn, prompt_name, content, content_hash)
            print(f"  {file_path.name} -> UPDATED (id={new_id})")
            updated += 1
        else:
            # No change
            print(f"  {file_path.name} -> unchanged (id={latest[0]})")
            unchanged += 1

    conn.close()

    print(f"\nSummary: {updated} updated, {unchanged} unchanged, {errors} errors")


if __name__ == "__main__":
    main()
