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
    _create_matrix_column_tables(conn)
    _create_chat_tables(conn)
    _create_paper_notes(conn)
    _migrate_matrix_column_checkbox(conn)
    _migrate_code_type(conn)
    _migrate_coding_status(conn)
    _create_user_settings(conn)
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


def _create_matrix_column_tables(conn: sqlite3.Connection) -> None:
    """Decouple matrix columns from codes.

    Matrix columns are now independent entities with typed inputs.
    They can optionally link to codes for evidence tracking.
    """
    # Check if migration already done (matrix_column table exists)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='matrix_column'"
    ).fetchone()
    if row is not None:
        return  # already migrated

    # Create matrix column definition table
    conn.execute("""
        CREATE TABLE matrix_column (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            column_type TEXT NOT NULL CHECK(column_type IN ('enum_single', 'enum_multi', 'text', 'checkbox')),
            sort_order INTEGER DEFAULT 0,
            color TEXT DEFAULT '#FFEB3B',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Enum options for matrix columns
    conn.execute("""
        CREATE TABLE matrix_column_option (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            column_id INTEGER NOT NULL,
            value TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (column_id) REFERENCES matrix_column(id) ON DELETE CASCADE
        )
    """)

    # Link matrix columns to codes for evidence tracking
    conn.execute("""
        CREATE TABLE matrix_column_code (
            column_id INTEGER NOT NULL,
            code_id INTEGER NOT NULL,
            PRIMARY KEY (column_id, code_id),
            FOREIGN KEY (column_id) REFERENCES matrix_column(id) ON DELETE CASCADE,
            FOREIGN KEY (code_id) REFERENCES code(id) ON DELETE CASCADE
        )
    """)

    # Drop old matrix_cell (uses code_id) and create new one (uses column_id)
    conn.execute("DROP TABLE IF EXISTS matrix_cell")
    conn.execute("""
        CREATE TABLE matrix_cell (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            column_id INTEGER NOT NULL,
            value TEXT,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id),
            FOREIGN KEY (column_id) REFERENCES matrix_column(id),
            UNIQUE(document_id, column_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_matrix_cell_v2_document ON matrix_cell(document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_matrix_cell_doc_col ON matrix_cell(document_id, column_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_annotation_code_code_id ON annotation_code(code_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_code_parent ON code(parent_id)"
    )


def _create_chat_tables(conn: sqlite3.Connection) -> None:
    """Create tables for per-paper chat conversations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            title TEXT,
            provider TEXT NOT NULL DEFAULT 'ollama',
            model TEXT NOT NULL DEFAULT 'qwen3.5:9b',
            params TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)
    # Migrate existing paper_chat rows if provider column missing
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(paper_chat)")
    columns = [row[1] for row in cursor.fetchall()]
    if "provider" not in columns:
        conn.execute("ALTER TABLE paper_chat ADD COLUMN provider TEXT NOT NULL DEFAULT 'ollama'")
    if "params" not in columns:
        conn.execute("ALTER TABLE paper_chat ADD COLUMN params TEXT")
    if "system_prompt" not in columns:
        conn.execute("ALTER TABLE paper_chat ADD COLUMN system_prompt TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES paper_chat(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_paper_chat_document ON paper_chat(document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_message_chat ON chat_message(chat_id)"
    )


def _migrate_coding_status(conn: sqlite3.Connection) -> None:
    """Add coding_status column to pass_review for Phase 3 progress tracking."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(pass_review)")
    columns = [row[1] for row in cursor.fetchall()]
    if "coding_status" not in columns:
        conn.execute("ALTER TABLE pass_review ADD COLUMN coding_status TEXT")


def _create_user_settings(conn: sqlite3.Connection) -> None:
    """Create key-value table for persisting UI settings."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)


def _migrate_code_type(conn: sqlite3.Connection) -> None:
    """Add code_type column to code table if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(code)")
    columns = [row[1] for row in cursor.fetchall()]
    if "code_type" not in columns:
        conn.execute("ALTER TABLE code ADD COLUMN code_type TEXT")


def _migrate_matrix_column_checkbox(conn: sqlite3.Connection) -> None:
    """Add 'checkbox' to matrix_column.column_type CHECK constraint.

    SQLite doesn't support ALTER CHECK, so we recreate the table.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='matrix_column'"
    )
    row = cursor.fetchone()
    if row is None:
        return
    if "checkbox" in row[0]:
        return  # already migrated

    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("""
        CREATE TABLE matrix_column_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            column_type TEXT NOT NULL CHECK(column_type IN ('enum_single', 'enum_multi', 'text', 'checkbox')),
            sort_order INTEGER DEFAULT 0,
            color TEXT DEFAULT '#FFEB3B',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT INTO matrix_column_new (id, name, description, column_type, sort_order, color, created_at)
        SELECT id, name, description, column_type, sort_order, color, created_at FROM matrix_column
    """)
    cursor.execute("DROP TABLE matrix_column")
    cursor.execute("ALTER TABLE matrix_column_new RENAME TO matrix_column")
    cursor.execute("PRAGMA foreign_keys = ON")


def _create_paper_notes(conn: sqlite3.Connection) -> None:
    """Create table for paper-level notes (separate from review notes)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_note (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER UNIQUE NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES document(id)
        )
    """)
