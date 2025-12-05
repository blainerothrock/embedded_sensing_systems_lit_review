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
) -> int | None:
    """Add a document record and return its ID. Returns None if duplicate."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO document (bibtex_key, entry_type, title, doi, url, search_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bibtex_key, entry_type, title, doi, url, search_id)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Duplicate bibtex_key, skip
        return None


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


def create_review_entry(conn: sqlite3.Connection, document_id: int) -> None:
    """Create a blank review entry for a document."""
    cursor = conn.cursor()
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

            doc_id = add_document(conn, bibtex_key, entry_type, title, doi, url, search_id)

            if doc_id is None:
                stats["duplicates_skipped"] += 1
                continue

            stats["entries_added"] += 1

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

            # Create blank review entry
            create_review_entry(conn, doc_id)

    return stats


def main():
    """Main entry point for populating database from ACM extract."""
    base_dir = Path(__file__).parent
    acm_dir = base_dir / "acm-extract"

    # Read source info
    source_file = acm_dir / "source.txt"
    if source_file.exists():
        source = source_file.read_text().strip()
    else:
        source = "ACM Digital Library"

    # Read search details (markdown)
    details_file = acm_dir / "serach.md"
    if details_file.exists():
        details = details_file.read_text()
    else:
        details = None

    # Initialize database
    conn = init_db()

    # Check if this search already exists
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM search WHERE source = ?", (source,))
    existing = cursor.fetchone()

    if existing:
        print(f"Search '{source}' already exists with ID {existing[0]}")
        print("Skipping to avoid duplicates. Delete the database to reimport.")
        conn.close()
        return

    # Add search record
    search_id = add_search(conn, source, details)
    print(f"Created search '{source}' with ID {search_id}")

    # Populate from bibtex files
    stats = populate_from_directory(conn, acm_dir, search_id)

    print("\n--- Import Statistics ---")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Entries added: {stats['entries_added']}")
    print(f"Duplicates skipped: {stats['duplicates_skipped']}")
    print(f"By type:")
    for entry_type, count in stats["by_type"].items():
        if count > 0:
            print(f"  {entry_type}: {count}")

    conn.close()


if __name__ == "__main__":
    main()
