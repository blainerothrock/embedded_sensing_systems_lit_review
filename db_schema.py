"""Database schema for literature review tool."""

import json
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

    # Pass-specific reviews (for multi-pass screening)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pass_review (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            pass_number INTEGER NOT NULL CHECK(pass_number IN (1, 2)),
            decision TEXT CHECK(decision IN ('include', 'exclude', 'uncertain')),
            notes TEXT,
            llm_suggestion TEXT,
            llm_accepted INTEGER,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id),
            UNIQUE(document_id, pass_number)
        )
    """)

    # Pass-specific exclusion codes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pass_review_exclusion_code (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pass_review_id INTEGER NOT NULL,
            exclusion_code_id INTEGER NOT NULL,
            FOREIGN KEY (pass_review_id) REFERENCES pass_review(id),
            FOREIGN KEY (exclusion_code_id) REFERENCES exclusion_code(id),
            UNIQUE(pass_review_id, exclusion_code_id)
        )
    """)

    # App settings (persisted)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Versioned prompts (full text stored)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompt_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_name TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(prompt_name, content_hash)
        )
    """)

    # LLM request audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_request_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            pass_number INTEGER NOT NULL,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model TEXT NOT NULL,
            thinking_mode INTEGER NOT NULL,
            system_prompt_id INTEGER NOT NULL,
            inclusion_criteria_id INTEGER NOT NULL,
            exclusion_criteria_id INTEGER NOT NULL,
            user_prompt_id INTEGER NOT NULL,
            full_system_prompt TEXT NOT NULL,
            full_user_prompt TEXT NOT NULL,
            raw_response TEXT,
            decision TEXT,
            confidence REAL,
            reasoning TEXT,
            exclusion_codes TEXT,
            domain TEXT CHECK(domain IN ('health', 'ecological') OR domain IS NULL),
            error TEXT,
            response_time_ms INTEGER,
            FOREIGN KEY (document_id) REFERENCES document(id),
            FOREIGN KEY (system_prompt_id) REFERENCES prompt_version(id),
            FOREIGN KEY (inclusion_criteria_id) REFERENCES prompt_version(id),
            FOREIGN KEY (exclusion_criteria_id) REFERENCES prompt_version(id),
            FOREIGN KEY (user_prompt_id) REFERENCES prompt_version(id)
        )
    """)

    # User-defined tags
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Document-tag junction (many-to-many)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_tag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id),
            FOREIGN KEY (tag_id) REFERENCES tag(id),
            UNIQUE(document_id, tag_id)
        )
    """)

    # Create indexes for common queries
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_search ON document(search_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_entry_type ON document(entry_type)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_included ON review(included)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pass_review_document ON pass_review(document_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pass_review_pass ON pass_review(pass_number)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompt_version_name ON prompt_version(prompt_name)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_request_log_document ON llm_request_log(document_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_tag_document ON document_tag(document_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_tag_tag ON document_tag(tag_id)"
    )
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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_duplicate_group ON document(duplicate_group_id)"
    )
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
            "UPDATE document SET duplicate_group_id = ? WHERE doi = ?", (group_id, doi)
        )

    conn.commit()


def migrate_pass_review_support(conn: sqlite3.Connection) -> None:
    """Add pass_review support and populate default exclusion codes and settings."""
    cursor = conn.cursor()

    # Add description column to exclusion_code if it doesn't exist
    cursor.execute("PRAGMA table_info(exclusion_code)")
    columns = [row[1] for row in cursor.fetchall()]
    if "description" not in columns:
        cursor.execute("ALTER TABLE exclusion_code ADD COLUMN description TEXT")

    # Default exclusion codes with descriptions
    default_exclusion_codes = [
        (
            "EX1",
            "High-power and/or high-dimensional data processing (image, video, audio, RF; >=500mW; macroprocessor-based)",
        ),
        (
            "EX2",
            "Commercial off the shelf (COTS) use or repurpose (smartphones, smartwatches, commercial devices)",
        ),
        (
            "EX3",
            "Out-of-scope platform or applications (non-medical/ecological; vehicles, UAVs, drones, VR/AR, entertainment)",
        ),
        (
            "EX5",
            "Application-agnostic (no targeted application, e.g., novel wireless protocol, general security)",
        ),
        (
            "EX6",
            "No specific embedded artifact (no system built/designed by authors, e.g., public dataset analysis, simulation)",
        ),
    ]

    for code, description in default_exclusion_codes:
        cursor.execute(
            "INSERT OR IGNORE INTO exclusion_code (code, description) VALUES (?, ?)",
            (code, description),
        )
        # Update description if code already exists but has no description
        cursor.execute(
            "UPDATE exclusion_code SET description = ? WHERE code = ? AND description IS NULL",
            (description, code),
        )

    # Default settings
    default_settings = [
        ("llm_auto_suggest", "false"),
        ("llm_thinking_mode", "true"),
        ("llm_model", "qwen3:8b"),
        ("llm_host", "http://localhost:11434"),
    ]

    for key, value in default_settings:
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )

    conn.commit()


def migrate_llm_audit_and_tagging(conn: sqlite3.Connection) -> None:
    """Add llm_request_log_id column to pass_review for existing databases."""
    cursor = conn.cursor()

    # Check if llm_request_log_id column exists in pass_review
    cursor.execute("PRAGMA table_info(pass_review)")
    columns = [row[1] for row in cursor.fetchall()]

    if "llm_request_log_id" not in columns:
        cursor.execute("""
            ALTER TABLE pass_review
            ADD COLUMN llm_request_log_id INTEGER REFERENCES llm_request_log(id)
        """)

    conn.commit()


def migrate_llm_domain_column(conn: sqlite3.Connection) -> None:
    """Add domain column to llm_request_log and backfill from raw_response."""
    cursor = conn.cursor()

    # Check if domain column exists in llm_request_log
    cursor.execute("PRAGMA table_info(llm_request_log)")
    columns = [row[1] for row in cursor.fetchall()]

    if "domain" not in columns:
        cursor.execute("""
            ALTER TABLE llm_request_log
            ADD COLUMN domain TEXT CHECK(domain IN ('health', 'ecological') OR domain IS NULL)
        """)

        # Backfill domain from raw_response JSON
        cursor.execute("SELECT id, raw_response FROM llm_request_log WHERE raw_response IS NOT NULL")
        rows = cursor.fetchall()

        for row in rows:
            log_id = row[0]
            raw_response = row[1]
            try:
                data = json.loads(raw_response)
                domain = data.get("domain")
                if domain in ("health", "ecological"):
                    cursor.execute(
                        "UPDATE llm_request_log SET domain = ? WHERE id = ?",
                        (domain, log_id)
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        conn.commit()


def migrate_backfill_llm_metadata(conn: sqlite3.Connection) -> None:
    """Backfill llm_suggestion JSON with metadata from llm_request_log."""
    cursor = conn.cursor()

    # Find pass_review rows with llm_suggestion missing metadata
    cursor.execute("""
        SELECT pr.id, pr.document_id, pr.pass_number, pr.llm_suggestion
        FROM pass_review pr
        WHERE pr.llm_suggestion IS NOT NULL
    """)
    rows = cursor.fetchall()

    updated = 0
    for row in rows:
        pr_id = row[0]
        doc_id = row[1]
        pass_num = row[2]
        llm_json = row[3]

        try:
            data = json.loads(llm_json)
        except (json.JSONDecodeError, TypeError):
            continue

        # Skip if already has metadata
        if data.get("model") is not None:
            continue

        # Find matching llm_request_log entry
        cursor.execute("""
            SELECT model, thinking_mode, domain, requested_at, response_time_ms
            FROM llm_request_log
            WHERE document_id = ? AND pass_number = ?
            ORDER BY requested_at DESC
            LIMIT 1
        """, (doc_id, pass_num))
        log_row = cursor.fetchone()

        if log_row:
            data["model"] = log_row[0]
            data["thinking_mode"] = bool(log_row[1])
            data["domain"] = log_row[2]
            data["requested_at"] = log_row[3]
            data["response_time_ms"] = log_row[4]

            cursor.execute(
                "UPDATE pass_review SET llm_suggestion = ? WHERE id = ?",
                (json.dumps(data), pr_id)
            )
            updated += 1

    if updated > 0:
        conn.commit()


def init_db() -> sqlite3.Connection:
    """Initialize database and return connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    migrate_duplicate_support(conn)
    migrate_pass_review_support(conn)
    migrate_llm_audit_and_tagging(conn)
    migrate_llm_domain_column(conn)
    migrate_backfill_llm_metadata(conn)
    return conn


if __name__ == "__main__":
    conn = init_db()
    print(f"Database created at {DB_PATH}")
    conn.close()
