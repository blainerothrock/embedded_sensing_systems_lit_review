"""Database schema for literature review tool."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "lit_review.db"


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the database schema."""
    cursor = conn.cursor()

    # Search table - tracks where documents came from
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            details TEXT
        )
    """)

    # Duplicate group table - links papers with same DOI across searches
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS duplicate_group (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doi TEXT UNIQUE NOT NULL
        )
    """)

    # Main document reference table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bibtex_key TEXT UNIQUE NOT NULL,
            entry_type TEXT NOT NULL,
            title TEXT,
            doi TEXT,
            url TEXT,
            search_id INTEGER NOT NULL,
            duplicate_group_id INTEGER,
            FOREIGN KEY (search_id) REFERENCES search(id),
            FOREIGN KEY (duplicate_group_id) REFERENCES duplicate_group(id)
        )
    """)

    # Article-specific fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS article (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER UNIQUE NOT NULL,
            author TEXT,
            journal TEXT,
            year TEXT,
            volume TEXT,
            number TEXT,
            pages TEXT,
            issn TEXT,
            publisher TEXT,
            address TEXT,
            abstract TEXT,
            keywords TEXT,
            month TEXT,
            note TEXT,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)

    # Inproceedings-specific fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inproceedings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER UNIQUE NOT NULL,
            author TEXT,
            booktitle TEXT,
            year TEXT,
            series TEXT,
            pages TEXT,
            articleno TEXT,
            numpages TEXT,
            isbn TEXT,
            publisher TEXT,
            address TEXT,
            location TEXT,
            abstract TEXT,
            keywords TEXT,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)

    # Inbook-specific fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inbook (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER UNIQUE NOT NULL,
            author TEXT,
            booktitle TEXT,
            year TEXT,
            chapter TEXT,
            pages TEXT,
            isbn TEXT,
            publisher TEXT,
            address TEXT,
            abstract TEXT,
            keywords TEXT,
            edition TEXT,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)

    # Review table
    # domain: 'health' or 'environmental' (optional)
    # reference: boolean flag (optional)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER UNIQUE NOT NULL,
            included INTEGER DEFAULT NULL,
            notes TEXT,
            domain TEXT CHECK(domain IN ('health', 'environmental') OR domain IS NULL),
            reference INTEGER DEFAULT NULL,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)

    # Exclusion codes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exclusion_code (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL
        )
    """)

    # Junction table for review exclusion codes (many-to-many)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_exclusion_code (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            exclusion_code_id INTEGER NOT NULL,
            FOREIGN KEY (review_id) REFERENCES review(id),
            FOREIGN KEY (exclusion_code_id) REFERENCES exclusion_code(id),
            UNIQUE(review_id, exclusion_code_id)
        )
    """)

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_search ON document(search_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_entry_type ON document(entry_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_included ON review(included)")
    # Note: idx_document_duplicate_group and idx_document_doi are created in migration

    conn.commit()


def migrate_duplicate_support(conn: sqlite3.Connection) -> None:
    """Add duplicate_group support to existing database."""
    cursor = conn.cursor()

    # Check if duplicate_group table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='duplicate_group'
    """)
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_group (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doi TEXT UNIQUE NOT NULL
            )
        """)

    # Check if duplicate_group_id column exists in document
    cursor.execute("PRAGMA table_info(document)")
    columns = [row[1] for row in cursor.fetchall()]

    if "duplicate_group_id" not in columns:
        cursor.execute("""
            ALTER TABLE document
            ADD COLUMN duplicate_group_id INTEGER REFERENCES duplicate_group(id)
        """)

    # Create indexes if they don't exist
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_duplicate_group ON document(duplicate_group_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_doi ON document(doi)")

    # Backfill: find existing duplicates by DOI and group them
    cursor.execute("""
        SELECT doi FROM document
        WHERE doi IS NOT NULL AND doi != ''
        GROUP BY doi HAVING COUNT(*) > 1
    """)
    duplicate_dois = cursor.fetchall()

    for row in duplicate_dois:
        doi = row[0]
        # Create duplicate group
        cursor.execute("INSERT OR IGNORE INTO duplicate_group (doi) VALUES (?)", (doi,))
        cursor.execute("SELECT id FROM duplicate_group WHERE doi = ?", (doi,))
        group_id = cursor.fetchone()[0]
        # Update all documents with this DOI
        cursor.execute(
            "UPDATE document SET duplicate_group_id = ? WHERE doi = ?",
            (group_id, doi)
        )

    conn.commit()


def init_db() -> sqlite3.Connection:
    """Initialize database and return connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    migrate_duplicate_support(conn)
    return conn


if __name__ == "__main__":
    conn = init_db()
    print(f"Database created at {DB_PATH}")
    conn.close()
