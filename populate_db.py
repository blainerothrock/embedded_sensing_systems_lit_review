"""Populate database from bibtex files in a search directory."""

import sqlite3
from pathlib import Path

import bibtexparser

from db_schema import init_db


def add_search(conn: sqlite3.Connection, source: str, details: str | None) -> int:
    """Add a search record and return its ID."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO search (source, details) VALUES (?, ?)",
        (source, details)
    )
    conn.commit()
    return cursor.lastrowid


def add_document(
    conn: sqlite3.Connection,
    bibtex_key: str,
    entry_type: str,
    title: str | None,
    doi: str | None,
    url: str | None,
    search_id: int
) -> tuple[int | None, int | None]:
    """
    Add a document record and return (doc_id, duplicate_group_id).
    Returns (None, None) if bibtex_key is duplicate.
    Returns (doc_id, group_id) if DOI duplicate found (group_id links to existing review).
    """
    cursor = conn.cursor()
    duplicate_group_id = None

    # Check for DOI duplicate (only if DOI exists)
    if doi:
        cursor.execute(
            "SELECT id, duplicate_group_id FROM document WHERE doi = ?", (doi,)
        )
        existing = cursor.fetchone()

        if existing:
            # Found a document with same DOI
            duplicate_group_id = existing["duplicate_group_id"]

            if not duplicate_group_id:
                # Create new duplicate group
                cursor.execute(
                    "INSERT INTO duplicate_group (doi) VALUES (?)", (doi,)
                )
                duplicate_group_id = cursor.lastrowid
                # Update the existing document to belong to this group
                cursor.execute(
                    "UPDATE document SET duplicate_group_id = ? WHERE id = ?",
                    (duplicate_group_id, existing["id"])
                )

    try:
        cursor.execute(
            """INSERT INTO document (bibtex_key, entry_type, title, doi, url, search_id, duplicate_group_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (bibtex_key, entry_type, title, doi, url, search_id, duplicate_group_id)
        )
        conn.commit()
        return cursor.lastrowid, duplicate_group_id
    except sqlite3.IntegrityError:
        # Duplicate bibtex_key, skip
        conn.rollback()
        return None, None


def add_article(conn: sqlite3.Connection, document_id: int, entry: dict) -> None:
    """Add article-specific fields."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO article
           (document_id, author, journal, year, volume, number, pages, issn,
            publisher, address, abstract, keywords, month, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            document_id,
            entry.get("author"),
            entry.get("journal"),
            entry.get("year"),
            entry.get("volume"),
            entry.get("number"),
            entry.get("pages"),
            entry.get("issn"),
            entry.get("publisher"),
            entry.get("address"),
            entry.get("abstract"),
            entry.get("keywords"),
            entry.get("month"),
            entry.get("note"),
        )
    )
    conn.commit()


def add_inproceedings(conn: sqlite3.Connection, document_id: int, entry: dict) -> None:
    """Add inproceedings-specific fields."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inproceedings
           (document_id, author, booktitle, year, series, pages, articleno, numpages,
            isbn, publisher, address, location, abstract, keywords)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            document_id,
            entry.get("author"),
            entry.get("booktitle"),
            entry.get("year"),
            entry.get("series"),
            entry.get("pages"),
            entry.get("articleno"),
            entry.get("numpages"),
            entry.get("isbn"),
            entry.get("publisher"),
            entry.get("address"),
            entry.get("location"),
            entry.get("abstract"),
            entry.get("keywords"),
        )
    )
    conn.commit()


def add_inbook(conn: sqlite3.Connection, document_id: int, entry: dict) -> None:
    """Add inbook-specific fields."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inbook
           (document_id, author, booktitle, year, chapter, pages, isbn,
            publisher, address, abstract, keywords, edition)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            document_id,
            entry.get("author"),
            entry.get("booktitle"),
            entry.get("year"),
            entry.get("chapter"),
            entry.get("pages"),
            entry.get("isbn"),
            entry.get("publisher"),
            entry.get("address"),
            entry.get("abstract"),
            entry.get("keywords"),
            entry.get("edition"),
        )
    )
    conn.commit()


def create_review_entry(conn: sqlite3.Connection, document_id: int, duplicate_group_id: int | None = None) -> None:
    """Create a blank review entry for a document.

    If duplicate_group_id is set, check if a review already exists for the group.
    If so, skip creating a new review (duplicates share reviews).
    """
    cursor = conn.cursor()

    if duplicate_group_id:
        # Check if any document in this group already has a review
        cursor.execute("""
            SELECT r.id FROM review r
            JOIN document d ON r.document_id = d.id
            WHERE d.duplicate_group_id = ?
        """, (duplicate_group_id,))
        if cursor.fetchone():
            # Review already exists for this duplicate group
            return

    cursor.execute(
        "INSERT INTO review (document_id) VALUES (?)",
        (document_id,)
    )
    conn.commit()


def populate_from_directory(conn: sqlite3.Connection, directory: Path, search_id: int) -> dict:
    """
    Populate database from all .bib files in a directory.
    Returns statistics about the import.
    """
    stats = {
        "files_processed": 0,
        "entries_added": 0,
        "duplicates_skipped": 0,
        "doi_duplicates": 0,
        "by_type": {"article": 0, "inproceedings": 0, "inbook": 0, "other": 0}
    }

    bib_files = sorted(directory.glob("*.bib"))

    for bib_file in bib_files:
        stats["files_processed"] += 1
        print(f"Processing {bib_file.name}...")

        with open(bib_file, encoding="utf-8") as f:
            bib_db = bibtexparser.load(f)

        for entry in bib_db.entries:
            entry_type = entry.get("ENTRYTYPE", "").lower()
            bibtex_key = entry.get("ID", "")
            title = entry.get("title")
            doi = entry.get("doi")
            url = entry.get("url")

            doc_id, duplicate_group_id = add_document(conn, bibtex_key, entry_type, title, doi, url, search_id)

            if doc_id is None:
                stats["duplicates_skipped"] += 1
                continue

            stats["entries_added"] += 1

            if duplicate_group_id:
                stats["doi_duplicates"] += 1

            # Add type-specific details
            if entry_type == "article":
                add_article(conn, doc_id, entry)
                stats["by_type"]["article"] += 1
            elif entry_type == "inproceedings":
                add_inproceedings(conn, doc_id, entry)
                stats["by_type"]["inproceedings"] += 1
            elif entry_type == "inbook":
                add_inbook(conn, doc_id, entry)
                stats["by_type"]["inbook"] += 1
            else:
                stats["by_type"]["other"] += 1

            # Create blank review entry (skipped if duplicate group already has review)
            create_review_entry(conn, doc_id, duplicate_group_id)

    return stats


def read_source_file(directory: Path) -> str:
    """Read source name from source.txt in directory."""
    source_file = directory / "source.txt"
    if source_file.exists():
        return source_file.read_text().strip()
    # Fallback to directory name
    return directory.name


def read_details_file(directory: Path) -> str | None:
    """Read search details from search.txt or serach.md in directory."""
    # Try multiple possible filenames
    for filename in ["search.txt", "serach.md", "search.md"]:
        details_file = directory / filename
        if details_file.exists():
            return details_file.read_text()
    return None


def search_exists(conn: sqlite3.Connection, source: str) -> bool:
    """Check if a search with this source name already exists."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM search WHERE source = ?", (source,))
    return cursor.fetchone() is not None


def print_stats(stats: dict, source: str) -> None:
    """Print import statistics."""
    print(f"\n--- Import Statistics for '{source}' ---")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Entries added: {stats['entries_added']}")
    print(f"Bibtex key duplicates skipped: {stats['duplicates_skipped']}")
    print(f"DOI duplicates (linked): {stats['doi_duplicates']}")
    print(f"By type:")
    for entry_type, count in stats["by_type"].items():
        if count > 0:
            print(f"  {entry_type}: {count}")


def main():
    """Main entry point for populating database from all search directories."""
    base_dir = Path(__file__).parent
    searches_dir = base_dir / "searches"

    if not searches_dir.exists():
        print(f"Error: searches directory not found at {searches_dir}")
        return

    # Initialize database (also runs migrations)
    conn = init_db()

    # Get all subdirectories in searches/
    search_dirs = sorted([d for d in searches_dir.iterdir() if d.is_dir()])

    if not search_dirs:
        print("No search directories found in searches/")
        conn.close()
        return

    print(f"Found {len(search_dirs)} search directories")

    total_stats = {
        "searches_processed": 0,
        "searches_skipped": 0,
        "total_entries": 0,
        "total_doi_duplicates": 0,
    }

    for search_dir in search_dirs:
        source = read_source_file(search_dir)

        # Skip if already imported
        if search_exists(conn, source):
            print(f"\nSkipping '{source}' - already imported")
            total_stats["searches_skipped"] += 1
            continue

        print(f"\n{'='*50}")
        print(f"Processing: {source}")
        print(f"Directory: {search_dir.name}")
        print(f"{'='*50}")

        # Read search details
        details = read_details_file(search_dir)

        # Add search record
        search_id = add_search(conn, source, details)
        print(f"Created search '{source}' with ID {search_id}")

        # Populate from bibtex files
        stats = populate_from_directory(conn, search_dir, search_id)
        print_stats(stats, source)

        total_stats["searches_processed"] += 1
        total_stats["total_entries"] += stats["entries_added"]
        total_stats["total_doi_duplicates"] += stats["doi_duplicates"]

    print(f"\n{'='*50}")
    print("OVERALL SUMMARY")
    print(f"{'='*50}")
    print(f"Searches processed: {total_stats['searches_processed']}")
    print(f"Searches skipped (already imported): {total_stats['searches_skipped']}")
    print(f"Total entries added: {total_stats['total_entries']}")
    print(f"Total DOI duplicates linked: {total_stats['total_doi_duplicates']}")

    conn.close()


if __name__ == "__main__":
    main()
