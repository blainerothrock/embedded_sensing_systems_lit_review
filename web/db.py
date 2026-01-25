"""Database access layer for the web application."""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "lit_review.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@dataclass
class Document:
    """Represents a document for review."""

    id: int
    bibtex_key: str
    entry_type: str
    title: str | None
    doi: str | None
    url: str | None
    search_id: int
    author: str | None = None
    year: str | None = None
    abstract: str | None = None
    keywords: str | None = None
    journal: str | None = None
    booktitle: str | None = None
    duplicate_group_id: int | None = None
    search_source: str | None = None


@dataclass
class LLMSuggestion:
    """Represents an LLM suggestion for a paper."""

    decision: str
    reasoning: str
    confidence: float
    exclusion_codes: list[str] = field(default_factory=list)
    domain: str | None = None
    model: str | None = None
    thinking_mode: bool | None = None
    response_time_ms: int | None = None
    requested_at: str | None = None


@dataclass
class PassReview:
    """Represents a pass-specific review."""

    id: int | None
    document_id: int
    pass_number: int
    decision: str | None = None
    notes: str | None = None
    llm_suggestion: LLMSuggestion | None = None
    llm_accepted: bool | None = None
    exclusion_codes: list[str] = field(default_factory=list)


def get_searches() -> list[dict]:
    """Get all searches with their progress stats."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, source FROM search ORDER BY id")
    searches = []
    for row in cursor.fetchall():
        progress = get_pass_progress(row["id"])
        searches.append({
            "id": row["id"],
            "source": row["source"],
            **progress,
        })
    conn.close()
    return searches


def get_pass_progress(search_id: int) -> dict:
    """Get pass-specific progress stats for a search.

    Separates human reviews (decision IS NOT NULL) from LLM suggestions.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) as total FROM document WHERE search_id = ?", (search_id,)
    )
    total = cursor.fetchone()["total"]

    # Pass 1 stats - separate human reviews from LLM suggestions
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN decision IS NOT NULL THEN 1 ELSE 0 END) as human_reviewed,
            SUM(CASE WHEN llm_suggestion IS NOT NULL THEN 1 ELSE 0 END) as llm_reviewed,
            SUM(CASE WHEN decision = 'include' THEN 1 ELSE 0 END) as included,
            SUM(CASE WHEN decision = 'exclude' THEN 1 ELSE 0 END) as excluded,
            SUM(CASE WHEN decision = 'uncertain' THEN 1 ELSE 0 END) as uncertain
        FROM pass_review pr
        JOIN document d ON d.id = pr.document_id
        WHERE d.search_id = ? AND pr.pass_number = 1
    """,
        (search_id,),
    )
    p1 = cursor.fetchone()

    pass2_eligible = (p1["included"] or 0) + (p1["uncertain"] or 0)

    # Pass 2 stats
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN decision IS NOT NULL THEN 1 ELSE 0 END) as human_reviewed,
            SUM(CASE WHEN llm_suggestion IS NOT NULL THEN 1 ELSE 0 END) as llm_reviewed,
            SUM(CASE WHEN decision = 'include' THEN 1 ELSE 0 END) as included,
            SUM(CASE WHEN decision = 'exclude' THEN 1 ELSE 0 END) as excluded,
            SUM(CASE WHEN decision = 'uncertain' THEN 1 ELSE 0 END) as uncertain
        FROM pass_review pr
        JOIN document d ON d.id = pr.document_id
        WHERE d.search_id = ? AND pr.pass_number = 2
    """,
        (search_id,),
    )
    p2 = cursor.fetchone()

    conn.close()

    return {
        "total": total,
        "pass1": {
            "human_reviewed": p1["human_reviewed"] or 0,
            "llm_reviewed": p1["llm_reviewed"] or 0,
            "included": p1["included"] or 0,
            "excluded": p1["excluded"] or 0,
            "uncertain": p1["uncertain"] or 0,
        },
        "pass2": {
            "eligible": pass2_eligible,
            "human_reviewed": p2["human_reviewed"] or 0,
            "llm_reviewed": p2["llm_reviewed"] or 0,
            "included": p2["included"] or 0,
            "excluded": p2["excluded"] or 0,
            "uncertain": p2["uncertain"] or 0,
        },
    }


def get_documents_for_pass(search_id: int, pass_number: int) -> list[Document]:
    """Get documents eligible for review in a specific pass."""
    conn = get_connection()
    cursor = conn.cursor()

    if pass_number == 1:
        cursor.execute(
            """
            SELECT
                d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
                d.duplicate_group_id,
                COALESCE(a.author, i.author, ib.author) as author,
                COALESCE(a.year, i.year, ib.year) as year,
                COALESCE(a.abstract, i.abstract, ib.abstract) as abstract,
                COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
                a.journal,
                COALESCE(i.booktitle, ib.booktitle) as booktitle
            FROM document d
            LEFT JOIN article a ON a.document_id = d.id
            LEFT JOIN inproceedings i ON i.document_id = d.id
            LEFT JOIN inbook ib ON ib.document_id = d.id
            WHERE d.search_id = ?
            ORDER BY d.id
        """,
            (search_id,),
        )
    else:
        cursor.execute(
            """
            SELECT
                d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
                d.duplicate_group_id,
                COALESCE(a.author, i.author, ib.author) as author,
                COALESCE(a.year, i.year, ib.year) as year,
                COALESCE(a.abstract, i.abstract, ib.abstract) as abstract,
                COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
                a.journal,
                COALESCE(i.booktitle, ib.booktitle) as booktitle
            FROM document d
            LEFT JOIN article a ON a.document_id = d.id
            LEFT JOIN inproceedings i ON i.document_id = d.id
            LEFT JOIN inbook ib ON ib.document_id = d.id
            JOIN pass_review pr ON pr.document_id = d.id AND pr.pass_number = 1
            WHERE d.search_id = ? AND pr.decision IN ('include', 'uncertain')
            ORDER BY d.id
        """,
            (search_id,),
        )

    documents = []
    for row in cursor.fetchall():
        documents.append(
            Document(
                id=row["id"],
                bibtex_key=row["bibtex_key"],
                entry_type=row["entry_type"],
                title=row["title"],
                doi=row["doi"],
                url=row["url"],
                search_id=row["search_id"],
                author=row["author"],
                year=row["year"],
                abstract=row["abstract"],
                keywords=row["keywords"],
                journal=row["journal"],
                booktitle=row["booktitle"],
                duplicate_group_id=row["duplicate_group_id"],
            )
        )
    conn.close()
    return documents


def get_document(document_id: int) -> Document | None:
    """Get a single document by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
            d.duplicate_group_id,
            s.source as search_source,
            COALESCE(a.author, i.author, ib.author) as author,
            COALESCE(a.year, i.year, ib.year) as year,
            COALESCE(a.abstract, i.abstract, ib.abstract) as abstract,
            COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
            a.journal,
            COALESCE(i.booktitle, ib.booktitle) as booktitle
        FROM document d
        JOIN search s ON d.search_id = s.id
        LEFT JOIN article a ON a.document_id = d.id
        LEFT JOIN inproceedings i ON i.document_id = d.id
        LEFT JOIN inbook ib ON ib.document_id = d.id
        WHERE d.id = ?
    """,
        (document_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return Document(
        id=row["id"],
        bibtex_key=row["bibtex_key"],
        entry_type=row["entry_type"],
        title=row["title"],
        doi=row["doi"],
        url=row["url"],
        search_id=row["search_id"],
        author=row["author"],
        year=row["year"],
        abstract=row["abstract"],
        keywords=row["keywords"],
        journal=row["journal"],
        booktitle=row["booktitle"],
        duplicate_group_id=row["duplicate_group_id"],
        search_source=row["search_source"],
    )


def get_pass_review(document_id: int, pass_number: int) -> PassReview | None:
    """Get pass review for a document."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, document_id, pass_number, decision, notes, llm_suggestion, llm_accepted
        FROM pass_review
        WHERE document_id = ? AND pass_number = ?
    """,
        (document_id, pass_number),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    cursor.execute(
        """
        SELECT ec.code
        FROM pass_review_exclusion_code prec
        JOIN exclusion_code ec ON ec.id = prec.exclusion_code_id
        WHERE prec.pass_review_id = ?
    """,
        (row["id"],),
    )
    codes = [r["code"] for r in cursor.fetchall()]

    llm_suggestion = None
    if row["llm_suggestion"]:
        try:
            data = json.loads(row["llm_suggestion"])
            llm_suggestion = LLMSuggestion(
                decision=data.get("decision", "uncertain"),
                reasoning=data.get("reasoning", ""),
                confidence=data.get("confidence", 0.0),
                exclusion_codes=data.get("exclusion_codes", []),
                domain=data.get("domain"),
                model=data.get("model"),
                thinking_mode=data.get("thinking_mode"),
                response_time_ms=data.get("response_time_ms"),
                requested_at=data.get("requested_at"),
            )
        except json.JSONDecodeError:
            pass

    conn.close()
    return PassReview(
        id=row["id"],
        document_id=row["document_id"],
        pass_number=row["pass_number"],
        decision=row["decision"],
        notes=row["notes"],
        llm_suggestion=llm_suggestion,
        llm_accepted=None if row["llm_accepted"] is None else bool(row["llm_accepted"]),
        exclusion_codes=codes,
    )


def save_pass_review(
    document_id: int,
    pass_number: int,
    decision: str | None,
    notes: str | None = None,
    exclusion_codes: list[str] | None = None,
) -> int:
    """Save or update a pass review. Returns the pass_review id."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get existing LLM suggestion to preserve it
    cursor.execute(
        "SELECT llm_suggestion, llm_accepted FROM pass_review WHERE document_id = ? AND pass_number = ?",
        (document_id, pass_number),
    )
    existing = cursor.fetchone()
    llm_suggestion = existing["llm_suggestion"] if existing else None
    llm_accepted = existing["llm_accepted"] if existing else None

    cursor.execute(
        """
        INSERT INTO pass_review (document_id, pass_number, decision, notes, llm_suggestion, llm_accepted)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id, pass_number) DO UPDATE SET
            decision = excluded.decision,
            notes = excluded.notes,
            reviewed_at = CURRENT_TIMESTAMP
    """,
        (document_id, pass_number, decision, notes, llm_suggestion, llm_accepted),
    )
    conn.commit()

    cursor.execute(
        "SELECT id FROM pass_review WHERE document_id = ? AND pass_number = ?",
        (document_id, pass_number),
    )
    pass_review_id = cursor.fetchone()["id"]

    # Update exclusion codes if provided
    if exclusion_codes is not None:
        cursor.execute(
            "DELETE FROM pass_review_exclusion_code WHERE pass_review_id = ?",
            (pass_review_id,),
        )
        for code in exclusion_codes:
            cursor.execute("SELECT id FROM exclusion_code WHERE code = ?", (code,))
            code_row = cursor.fetchone()
            if code_row:
                cursor.execute(
                    "INSERT INTO pass_review_exclusion_code (pass_review_id, exclusion_code_id) VALUES (?, ?)",
                    (pass_review_id, code_row["id"]),
                )
        conn.commit()

    conn.close()
    return pass_review_id


def update_llm_accepted(document_id: int, pass_number: int, accepted: bool) -> None:
    """Update the llm_accepted field for a pass review."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE pass_review
        SET llm_accepted = ?
        WHERE document_id = ? AND pass_number = ?
    """,
        (int(accepted), document_id, pass_number),
    )
    conn.commit()
    conn.close()


def get_exclusion_codes() -> list[dict]:
    """Get all exclusion codes with descriptions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, description FROM exclusion_code ORDER BY code")
    results = [
        {"id": row["id"], "code": row["code"], "description": row["description"]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return results


def get_all_tags() -> list[dict]:
    """Get all tags."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM tag ORDER BY name")
    results = [{"id": row["id"], "name": row["name"]} for row in cursor.fetchall()]
    conn.close()
    return results


def get_document_tags(document_id: int) -> list[str]:
    """Get tag names for a document."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.name
        FROM document_tag dt
        JOIN tag t ON t.id = dt.tag_id
        WHERE dt.document_id = ?
        ORDER BY t.name
    """,
        (document_id,),
    )
    results = [row["name"] for row in cursor.fetchall()]
    conn.close()
    return results


def set_document_tags(document_id: int, tag_names: list[str]) -> None:
    """Set tags for a document (replaces existing)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM document_tag WHERE document_id = ?", (document_id,))

    for name in tag_names:
        # Get or create tag
        cursor.execute("SELECT id FROM tag WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            tag_id = row["id"]
        else:
            cursor.execute("INSERT INTO tag (name) VALUES (?)", (name,))
            tag_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO document_tag (document_id, tag_id) VALUES (?, ?)",
            (document_id, tag_id),
        )

    conn.commit()
    conn.close()


def get_duplicate_searches(doc_id: int, duplicate_group_id: int) -> list[dict]:
    """Get other documents in the same duplicate group."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT d.id, s.source
        FROM document d
        JOIN search s ON d.search_id = s.id
        WHERE d.duplicate_group_id = ? AND d.id != ?
    """,
        (duplicate_group_id, doc_id),
    )
    results = [{"id": row["id"], "source": row["source"]} for row in cursor.fetchall()]
    conn.close()
    return results


def get_all_documents_for_browse() -> list[dict]:
    """Get all documents for browse view."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            d.id, d.title, d.search_id,
            s.source as search_source,
            COALESCE(a.year, i.year, ib.year) as year,
            a.journal,
            COALESCE(i.booktitle, ib.booktitle) as booktitle
        FROM document d
        JOIN search s ON d.search_id = s.id
        LEFT JOIN article a ON a.document_id = d.id
        LEFT JOIN inproceedings i ON i.document_id = d.id
        LEFT JOIN inbook ib ON ib.document_id = d.id
        ORDER BY d.id
    """)

    documents = []
    for row in cursor.fetchall():
        documents.append({
            "id": row["id"],
            "title": row["title"],
            "year": row["year"],
            "search_id": row["search_id"],
            "search_source": row["search_source"],
            "venue": row["journal"] or row["booktitle"],
        })
    conn.close()
    return documents


def get_all_pass_reviews(human_only: bool = True) -> dict[tuple[int, int], dict]:
    """Get all pass reviews as a dict keyed by (document_id, pass_number).

    Args:
        human_only: If True, only return reviews with human decisions (decision IS NOT NULL).
                   If False, return all reviews including those with only LLM suggestions.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if human_only:
        cursor.execute("""
            SELECT id, document_id, pass_number, decision
            FROM pass_review
            WHERE decision IS NOT NULL
        """)
    else:
        cursor.execute("""
            SELECT id, document_id, pass_number, decision
            FROM pass_review
        """)
    rows = cursor.fetchall()

    cursor.execute("""
        SELECT prec.pass_review_id, ec.code
        FROM pass_review_exclusion_code prec
        JOIN exclusion_code ec ON ec.id = prec.exclusion_code_id
    """)
    codes_by_review: dict[int, list[str]] = {}
    for r in cursor.fetchall():
        codes_by_review.setdefault(r["pass_review_id"], []).append(r["code"])

    conn.close()

    result: dict[tuple[int, int], dict] = {}
    for row in rows:
        result[(row["document_id"], row["pass_number"])] = {
            "decision": row["decision"],
            "exclusion_codes": codes_by_review.get(row["id"], []),
        }

    return result


def get_all_document_tags() -> dict[int, list[str]]:
    """Get all document tags as a dict keyed by document_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT dt.document_id, t.name
        FROM document_tag dt
        JOIN tag t ON t.id = dt.tag_id
        ORDER BY dt.document_id, t.name
    """)
    result: dict[int, list[str]] = {}
    for row in cursor.fetchall():
        result.setdefault(row["document_id"], []).append(row["name"])
    conn.close()
    return result


def get_all_venues() -> list[str]:
    """Get all unique venues."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT venue FROM (
            SELECT journal as venue FROM article WHERE journal IS NOT NULL AND journal != ''
            UNION
            SELECT booktitle as venue FROM inproceedings WHERE booktitle IS NOT NULL AND booktitle != ''
            UNION
            SELECT booktitle as venue FROM inbook WHERE booktitle IS NOT NULL AND booktitle != ''
        ) ORDER BY venue
    """)
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results
