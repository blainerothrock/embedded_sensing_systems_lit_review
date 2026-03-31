"""Database access layer for lit-review-coding."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "lit_review.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --- Papers (read from existing tables) ---


def _paper_select() -> str:
    """Common SELECT + JOIN fragment for getting papers with type-specific metadata."""
    return """
        SELECT
            d.id, d.title, d.doi, d.url, d.entry_type, d.bibtex_key,
            COALESCE(a.author, ip.author, ib.author) as author,
            COALESCE(a.year, ip.year, ib.year) as year,
            COALESCE(a.abstract, ip.abstract, ib.abstract) as abstract,
            COALESCE(a.keywords, ip.keywords, ib.keywords) as keywords,
            COALESCE(a.journal, ip.booktitle, ib.booktitle) as venue,
            dp.pdf_path,
            pr3.decision as phase3_decision,
            pr3.notes as phase3_notes
        FROM document d
        LEFT JOIN article a ON a.document_id = d.id
        LEFT JOIN inproceedings ip ON ip.document_id = d.id
        LEFT JOIN inbook ib ON ib.document_id = d.id
        LEFT JOIN document_pdf dp ON dp.document_id = d.id
        LEFT JOIN pass_review pr3 ON pr3.document_id = d.id AND pr3.pass_number = 3
    """


def get_phase3_papers(conn: sqlite3.Connection, search: str = "", status: str = "all") -> list[dict]:
    """Get all Pass 2 included papers with Phase 3 status and PDF info."""
    query = _paper_select() + """
        INNER JOIN pass_review pr2 ON pr2.document_id = d.id
            AND pr2.pass_number = 2 AND pr2.decision = 'include'
    """
    conditions = []
    params = []

    if search:
        conditions.append("""(d.title LIKE ? OR
            COALESCE(a.author, ip.author, ib.author) LIKE ? OR
            COALESCE(a.keywords, ip.keywords, ib.keywords) LIKE ?)""")
        params.extend([f"%{search}%"] * 3)

    if status == "pending":
        conditions.append("pr3.decision IS NULL")
    elif status == "include":
        conditions.append("pr3.decision = 'include'")
    elif status == "exclude":
        conditions.append("pr3.decision = 'exclude'")
    elif status == "has_pdf":
        conditions.append("dp.pdf_path IS NOT NULL")
    elif status == "no_pdf":
        conditions.append("dp.pdf_path IS NULL")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY d.title"

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_paper(conn: sqlite3.Connection, document_id: int) -> dict | None:
    """Get a single paper with all metadata."""
    row = conn.execute("""
        SELECT
            d.id, d.title, d.doi, d.url, d.entry_type, d.bibtex_key,
            COALESCE(a.author, ip.author, ib.author) as author,
            COALESCE(a.year, ip.year, ib.year) as year,
            COALESCE(a.abstract, ip.abstract, ib.abstract) as abstract,
            COALESCE(a.keywords, ip.keywords, ib.keywords) as keywords,
            COALESCE(a.journal, ip.booktitle, ib.booktitle) as venue,
            dp.pdf_path,
            pr3.id as phase3_review_id,
            pr3.decision as phase3_decision,
            pr3.notes as phase3_notes
        FROM document d
        LEFT JOIN article a ON a.document_id = d.id
        LEFT JOIN inproceedings ip ON ip.document_id = d.id
        LEFT JOIN inbook ib ON ib.document_id = d.id
        LEFT JOIN document_pdf dp ON dp.document_id = d.id
        LEFT JOIN pass_review pr3 ON pr3.document_id = d.id AND pr3.pass_number = 3
        WHERE d.id = ?
    """, (document_id,)).fetchone()
    if row is None:
        return None

    paper = dict(row)

    # Get exclusion codes for phase 3 review if it exists
    if paper["phase3_review_id"]:
        codes = conn.execute("""
            SELECT ec.id, ec.code, ec.description
            FROM pass_review_exclusion_code prec
            JOIN exclusion_code ec ON ec.id = prec.exclusion_code_id
            WHERE prec.pass_review_id = ?
        """, (paper["phase3_review_id"],)).fetchall()
        paper["exclusion_codes"] = [dict(c) for c in codes]
    else:
        paper["exclusion_codes"] = []

    return paper


def get_exclusion_codes(conn: sqlite3.Connection) -> list[dict]:
    """Get all exclusion codes."""
    rows = conn.execute("SELECT id, code, description FROM exclusion_code ORDER BY code").fetchall()
    return [dict(r) for r in rows]


# --- PDF management ---


def save_pdf_reference(conn: sqlite3.Connection, document_id: int, pdf_path: str) -> None:
    conn.execute("""
        INSERT INTO document_pdf (document_id, pdf_path)
        VALUES (?, ?)
        ON CONFLICT(document_id) DO UPDATE SET pdf_path = excluded.pdf_path, uploaded_at = CURRENT_TIMESTAMP
    """, (document_id, pdf_path))
    conn.commit()


def get_pdf_path(conn: sqlite3.Connection, document_id: int) -> str | None:
    row = conn.execute(
        "SELECT pdf_path FROM document_pdf WHERE document_id = ?", (document_id,)
    ).fetchone()
    return row["pdf_path"] if row else None


# --- Phase 3 screening ---


def save_phase3_review(
    conn: sqlite3.Connection,
    document_id: int,
    decision: str,
    notes: str,
    exclusion_code_ids: list[int],
) -> None:
    """Save or update a Phase 3 review decision."""
    # Upsert pass_review for pass_number=3
    conn.execute("""
        INSERT INTO pass_review (document_id, pass_number, decision, notes, reviewed_at)
        VALUES (?, 3, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(document_id, pass_number)
        DO UPDATE SET decision = excluded.decision, notes = excluded.notes,
                      reviewed_at = CURRENT_TIMESTAMP
    """, (document_id, decision, notes))

    # Get the review id
    row = conn.execute(
        "SELECT id FROM pass_review WHERE document_id = ? AND pass_number = 3",
        (document_id,)
    ).fetchone()
    review_id = row["id"]

    # Replace exclusion codes
    conn.execute(
        "DELETE FROM pass_review_exclusion_code WHERE pass_review_id = ?", (review_id,)
    )
    for code_id in exclusion_code_ids:
        conn.execute(
            "INSERT INTO pass_review_exclusion_code (pass_review_id, exclusion_code_id) VALUES (?, ?)",
            (review_id, code_id)
        )

    conn.commit()


# --- Stats ---


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get Phase 3 progress stats."""
    total = conn.execute("""
        SELECT COUNT(*) as n FROM pass_review WHERE pass_number = 2 AND decision = 'include'
    """).fetchone()["n"]

    reviewed = conn.execute("""
        SELECT COUNT(*) as n FROM pass_review WHERE pass_number = 3 AND decision IS NOT NULL
    """).fetchone()["n"]

    included = conn.execute("""
        SELECT COUNT(*) as n FROM pass_review WHERE pass_number = 3 AND decision = 'include'
    """).fetchone()["n"]

    excluded = conn.execute("""
        SELECT COUNT(*) as n FROM pass_review WHERE pass_number = 3 AND decision = 'exclude'
    """).fetchone()["n"]

    has_pdf = conn.execute("SELECT COUNT(*) as n FROM document_pdf").fetchone()["n"]

    return {
        "total": total,
        "reviewed": reviewed,
        "included": included,
        "excluded": excluded,
        "pending": total - reviewed,
        "has_pdf": has_pdf,
    }


# --- Codes (hierarchical: top-level + sub-codes) ---


def get_codes(conn: sqlite3.Connection) -> list[dict]:
    """Get all codes as a tree: top-level codes with children."""
    rows = conn.execute(
        "SELECT * FROM code ORDER BY sort_order, id"
    ).fetchall()
    codes = [dict(r) for r in rows]

    # Build tree
    top_level = []
    children_map = {}  # parent_id -> [children]
    for c in codes:
        pid = c["parent_id"]
        if pid is None:
            c["children"] = []
            top_level.append(c)
        else:
            children_map.setdefault(pid, []).append(c)

    for c in top_level:
        c["children"] = children_map.get(c["id"], [])

    return top_level


def create_code(
    conn: sqlite3.Connection, name: str,
    parent_id: int | None = None, description: str = "",
    color: str = "#FFEB3B", sort_order: int = 0,
) -> dict:
    cursor = conn.execute("""
        INSERT INTO code (name, parent_id, description, color, sort_order)
        VALUES (?, ?, ?, ?, ?)
    """, (name, parent_id, description, color, sort_order))
    conn.commit()
    row = conn.execute("SELECT * FROM code WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_code(conn: sqlite3.Connection, code_id: int, **kwargs) -> dict | None:
    allowed = {"name", "description", "color", "sort_order", "parent_id"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return None
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE code SET {set_clause} WHERE id = ?",
        (*updates.values(), code_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM code WHERE id = ?", (code_id,)).fetchone()
    return dict(row) if row else None


def delete_code(conn: sqlite3.Connection, code_id: int) -> bool:
    """Delete a code. Fails if it has annotations or sub-codes."""
    # Check for annotation_code references
    count = conn.execute(
        "SELECT COUNT(*) as n FROM annotation_code WHERE code_id = ?", (code_id,)
    ).fetchone()["n"]
    if count > 0:
        return False
    # Check for children
    count = conn.execute(
        "SELECT COUNT(*) as n FROM code WHERE parent_id = ?", (code_id,)
    ).fetchone()["n"]
    if count > 0:
        return False
    # Also clean up matrix_cell references
    conn.execute("DELETE FROM matrix_cell WHERE code_id = ?", (code_id,))
    conn.execute("DELETE FROM code WHERE id = ?", (code_id,))
    conn.commit()
    return True


# --- Annotations ---


def get_annotations(conn: sqlite3.Connection, document_id: int) -> list[dict]:
    """Get all annotations for a document with their codes."""
    rows = conn.execute("""
        SELECT * FROM annotation WHERE document_id = ? ORDER BY page_number, id
    """, (document_id,)).fetchall()

    result = []
    for row in rows:
        ann = dict(row)
        codes = conn.execute("""
            SELECT c.id, c.name, c.color, c.parent_id, ac.note as ac_note
            FROM annotation_code ac
            JOIN code c ON c.id = ac.code_id
            WHERE ac.annotation_id = ?
            ORDER BY c.name
        """, (ann["id"],)).fetchall()
        ann["codes"] = [dict(c) for c in codes]
        result.append(ann)
    return result


def create_annotation(
    conn: sqlite3.Connection, document_id: int, annotation_type: str,
    page_number: int, rects_json: str, selected_text: str | None = None,
    note: str | None = None, color: str | None = None,
    code_ids: list[int] | None = None,
) -> dict:
    cursor = conn.execute("""
        INSERT INTO annotation (document_id, annotation_type, page_number,
                                selected_text, note, color, rects_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (document_id, annotation_type, page_number, selected_text, note, color, rects_json))
    ann_id = cursor.lastrowid

    if code_ids:
        for code_id in code_ids:
            conn.execute(
                "INSERT INTO annotation_code (annotation_id, code_id) VALUES (?, ?)",
                (ann_id, code_id)
            )

    conn.commit()
    return get_annotation(conn, ann_id)


def get_annotation(conn: sqlite3.Connection, annotation_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM annotation WHERE id = ?", (annotation_id,)).fetchone()
    if not row:
        return None
    ann = dict(row)
    codes = conn.execute("""
        SELECT c.id, c.name, c.color, c.parent_id, ac.note as ac_note
        FROM annotation_code ac JOIN code c ON c.id = ac.code_id
        WHERE ac.annotation_id = ?
    """, (annotation_id,)).fetchall()
    ann["codes"] = [dict(c) for c in codes]
    return ann


def update_annotation(conn: sqlite3.Connection, annotation_id: int, **kwargs) -> dict | None:
    allowed = {"note", "color", "selected_text", "rects_json", "page_number", "annotation_type"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE annotation SET {set_clause} WHERE id = ?",
            (*updates.values(), annotation_id)
        )
    conn.commit()
    return get_annotation(conn, annotation_id)


def delete_annotation(conn: sqlite3.Connection, annotation_id: int) -> bool:
    conn.execute("DELETE FROM annotation_code WHERE annotation_id = ?", (annotation_id,))
    cursor = conn.execute("DELETE FROM annotation WHERE id = ?", (annotation_id,))
    conn.commit()
    return cursor.rowcount > 0


def add_annotation_code(
    conn: sqlite3.Connection, annotation_id: int, code_id: int,
    note: str | None = None,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO annotation_code (annotation_id, code_id, note) VALUES (?, ?, ?)",
        (annotation_id, code_id, note)
    )
    conn.commit()


def update_annotation_code_note(
    conn: sqlite3.Connection, annotation_id: int, code_id: int, note: str,
) -> None:
    conn.execute(
        "UPDATE annotation_code SET note = ? WHERE annotation_id = ? AND code_id = ?",
        (note, annotation_id, code_id)
    )
    conn.commit()


def remove_annotation_code(conn: sqlite3.Connection, annotation_id: int, code_id: int) -> None:
    conn.execute(
        "DELETE FROM annotation_code WHERE annotation_id = ? AND code_id = ?",
        (annotation_id, code_id)
    )
    conn.commit()


def get_code_usage_counts(conn: sqlite3.Connection) -> dict[int, int]:
    """Get annotation count per code: {code_id: count}."""
    rows = conn.execute("""
        SELECT code_id, COUNT(*) as n FROM annotation_code GROUP BY code_id
    """).fetchall()
    return {row["code_id"]: row["n"] for row in rows}


# --- Matrix ---


def get_matrix(conn: sqlite3.Connection) -> dict:
    """Get the coding matrix: papers × top-level codes with cell values and evidence counts."""
    codes = get_codes(conn)  # top-level codes with children

    papers = conn.execute("""
        SELECT d.id, d.title,
            COALESCE(a.author, ip.author, ib.author) as author,
            COALESCE(a.year, ip.year, ib.year) as year
        FROM document d
        INNER JOIN pass_review pr2 ON pr2.document_id = d.id
            AND pr2.pass_number = 2 AND pr2.decision = 'include'
        LEFT JOIN article a ON a.document_id = d.id
        LEFT JOIN inproceedings ip ON ip.document_id = d.id
        LEFT JOIN inbook ib ON ib.document_id = d.id
        ORDER BY d.title
    """).fetchall()

    # Get matrix cell values
    cells = conn.execute("SELECT * FROM matrix_cell").fetchall()
    cell_map = {}  # {doc_id: {code_id: {value, notes}}}
    for c in cells:
        cell_map.setdefault(c["document_id"], {})[c["code_id"]] = {
            "value": c["value"],
            "notes": c["notes"],
        }

    # Get annotation evidence counts per paper × top-level code
    # A top-level code's evidence = annotations tagged with it OR any of its sub-codes
    evidence_map = {}  # {doc_id: {top_code_id: count}}
    for code in codes:
        code_ids = [code["id"]] + [ch["id"] for ch in code["children"]]
        placeholders = ",".join("?" * len(code_ids))
        rows = conn.execute(f"""
            SELECT ann.document_id, COUNT(DISTINCT ann.id) as n
            FROM annotation ann
            JOIN annotation_code ac ON ac.annotation_id = ann.id
            WHERE ac.code_id IN ({placeholders})
            GROUP BY ann.document_id
        """, code_ids).fetchall()
        for r in rows:
            evidence_map.setdefault(r["document_id"], {})[code["id"]] = r["n"]

    return {
        "codes": codes,
        "papers": [dict(p) for p in papers],
        "cells": cell_map,
        "evidence": evidence_map,
    }


def save_matrix_cell(
    conn: sqlite3.Connection, document_id: int, code_id: int,
    value: str | None = None, notes: str | None = None,
) -> dict:
    conn.execute("""
        INSERT INTO matrix_cell (document_id, code_id, value, notes, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(document_id, code_id)
        DO UPDATE SET value = excluded.value, notes = excluded.notes,
                      updated_at = CURRENT_TIMESTAMP
    """, (document_id, code_id, value, notes))
    conn.commit()
    row = conn.execute(
        "SELECT * FROM matrix_cell WHERE document_id = ? AND code_id = ?",
        (document_id, code_id)
    ).fetchone()
    return dict(row)


# --- Coding Completeness ---


def get_coding_completeness(conn: sqlite3.Connection) -> dict[int, dict]:
    """Get matrix completeness per paper: {document_id: {filled: N, total: N}}."""
    total_columns = conn.execute(
        "SELECT COUNT(*) as n FROM code WHERE parent_id IS NULL"
    ).fetchone()["n"]

    if total_columns == 0:
        return {}

    rows = conn.execute("""
        SELECT document_id, COUNT(*) as filled
        FROM matrix_cell
        WHERE value IS NOT NULL AND value != ''
        GROUP BY document_id
    """).fetchall()

    return {
        row["document_id"]: {"filled": row["filled"], "total": total_columns}
        for row in rows
    }
