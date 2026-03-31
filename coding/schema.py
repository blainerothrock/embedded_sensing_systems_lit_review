"""Database schema migrations for lit-review-coding.

Adds new tables to the shared lit_review.db and modifies the pass_review
CHECK constraint to allow pass_number=3 for Phase 3 full-text screening.
"""

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    """Run all migrations."""
    _migrate_pass_review_check(conn)
    _create_document_pdf(conn)
    _create_coding_tables(conn)
    _migrate_annotation_code_note(conn)
    conn.commit()


def _migrate_annotation_code_note(conn: sqlite3.Connection) -> None:
    """Add note column to annotation_code if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(annotation_code)")
    columns = [row[1] for row in cursor.fetchall()]
    if "note" not in columns:
        conn.execute("ALTER TABLE annotation_code ADD COLUMN note TEXT")


def _migrate_pass_review_check(conn: sqlite3.Connection) -> None:
    """Relax pass_review.pass_number CHECK to allow 3.

    SQLite doesn't support ALTER CHECK, so we recreate the table.
    This is idempotent — skips if pass_number=3 is already allowed.
    """
    cursor = conn.cursor()

    # Test if pass_number=3 is already allowed by checking the schema
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='pass_review'"
    )
    row = cursor.fetchone()
    if row is None:
        return  # table doesn't exist, nothing to migrate
    schema_sql = row[0]
    if "1, 2, 3" in schema_sql:
        return  # already migrated

    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("""
        CREATE TABLE pass_review_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            pass_number INTEGER NOT NULL CHECK(pass_number IN (1, 2, 3)),
            decision TEXT CHECK(decision IN ('include', 'exclude', 'uncertain')),
            notes TEXT,
            llm_suggestion TEXT,
            llm_accepted INTEGER,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            llm_request_log_id INTEGER REFERENCES llm_request_log(id),
            FOREIGN KEY (document_id) REFERENCES document(id),
            UNIQUE(document_id, pass_number)
        )
    """)
    cursor.execute("""
        INSERT INTO pass_review_new
            (id, document_id, pass_number, decision, notes,
             llm_suggestion, llm_accepted, reviewed_at, llm_request_log_id)
        SELECT id, document_id, pass_number, decision, notes,
               llm_suggestion, llm_accepted, reviewed_at, llm_request_log_id
        FROM pass_review
    """)
    cursor.execute("DROP TABLE pass_review")
    cursor.execute("ALTER TABLE pass_review_new RENAME TO pass_review")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pass_review_document ON pass_review(document_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pass_review_pass ON pass_review(pass_number)"
    )
    cursor.execute("PRAGMA foreign_keys = ON")


def _create_document_pdf(conn: sqlite3.Connection) -> None:
    """Create table for tracking uploaded PDFs."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_pdf (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER UNIQUE NOT NULL,
            pdf_path TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)


def _create_coding_tables(conn: sqlite3.Connection) -> None:
    """Create tables for qualitative coding and annotations.

    v2 schema: codes are hierarchical tags on annotations.
    Top-level codes = matrix columns. Sub-codes = predefined cell value options.
    """
    # Drop old v1 tables if they exist (early dev, no production data)
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in ("document_code", "code_category"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")

    # Check if old code table has category_id (v1) and needs replacement
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='code'")
    row = cursor.fetchone()
    if row and "category_id" in row[0]:
        conn.execute("DROP TABLE IF EXISTS annotation")  # old annotation refs document_code
        conn.execute("DROP TABLE IF EXISTS code")
    conn.execute("PRAGMA foreign_keys = ON")

    # Codes: hierarchical tags. Top-level (parent_id=NULL) = matrix columns.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS code (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#FFEB3B',
            parent_id INTEGER,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES code(id)
        )
    """)

    # Annotations: highlighted text/areas in PDFs
    conn.execute("""
        CREATE TABLE IF NOT EXISTS annotation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            annotation_type TEXT NOT NULL CHECK(annotation_type IN ('highlight', 'note', 'area')),
            page_number INTEGER NOT NULL,
            selected_text TEXT,
            note TEXT,
            color TEXT,
            rects_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)

    # Junction: annotations tagged with codes (many-to-many)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS annotation_code (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annotation_id INTEGER NOT NULL,
            code_id INTEGER NOT NULL,
            FOREIGN KEY (annotation_id) REFERENCES annotation(id) ON DELETE CASCADE,
            FOREIGN KEY (code_id) REFERENCES code(id),
            UNIQUE(annotation_id, code_id)
        )
    """)

    # Matrix cells: paper × top-level code → inferred value
    conn.execute("""
        CREATE TABLE IF NOT EXISTS matrix_cell (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            code_id INTEGER NOT NULL,
            value TEXT,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id),
            FOREIGN KEY (code_id) REFERENCES code(id),
            UNIQUE(document_id, code_id)
        )
    """)

    # Indexes
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotation_document ON annotation(document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotation_code_annotation ON annotation_code(annotation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotation_code_code ON annotation_code(code_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_matrix_cell_document ON matrix_cell(document_id)"
    )
