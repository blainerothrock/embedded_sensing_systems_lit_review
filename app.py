"""Literature Review TUI Application."""

import json
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    OptionList,
    Select,
    Static,
    Switch,
    TextArea,
)
from textual.widgets.option_list import Option

from db_schema import DB_PATH
from llm_assistant import LLMAssistant, LLMSuggestion


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
    # Type-specific details
    author: str | None = None
    year: str | None = None
    abstract: str | None = None
    keywords: str | None = None
    journal: str | None = None
    booktitle: str | None = None
    # Review fields
    review_id: int | None = None
    included: bool | None = None
    notes: str | None = None
    domain: str | None = None
    reference: bool | None = None
    # Duplicate tracking
    duplicate_group_id: int | None = None


def get_connection() -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_searches() -> list[tuple[int, str, int, int]]:
    """Get all searches with their progress stats."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            s.id,
            s.source,
            COUNT(d.id) as total,
            SUM(CASE WHEN r.included IS NOT NULL THEN 1 ELSE 0 END) as reviewed
        FROM search s
        LEFT JOIN document d ON d.search_id = s.id
        LEFT JOIN review r ON r.document_id = d.id
        GROUP BY s.id
    """)
    results = [
        (row["id"], row["source"], row["total"], row["reviewed"])
        for row in cursor.fetchall()
    ]
    conn.close()
    return results


def get_documents_for_search(search_id: int) -> list[Document]:
    """Get all documents for a search."""
    conn = get_connection()
    cursor = conn.cursor()
    # Use subquery to find review for duplicate groups
    # For documents in a duplicate group, find the review from any document in the group
    cursor.execute(
        """
        SELECT
            d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
            d.duplicate_group_id,
            COALESCE(r.id, group_review.id) as review_id,
            COALESCE(r.included, group_review.included) as included,
            COALESCE(r.notes, group_review.notes) as notes,
            COALESCE(r.domain, group_review.domain) as domain,
            COALESCE(r.reference, group_review.reference) as reference,
            COALESCE(a.author, i.author, ib.author) as author,
            COALESCE(a.year, i.year, ib.year) as year,
            COALESCE(a.abstract, i.abstract, ib.abstract) as abstract,
            COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
            a.journal,
            COALESCE(i.booktitle, ib.booktitle) as booktitle
        FROM document d
        LEFT JOIN review r ON r.document_id = d.id
        LEFT JOIN (
            SELECT r2.*, d2.duplicate_group_id as dup_group_id
            FROM review r2
            JOIN document d2 ON r2.document_id = d2.id
            WHERE d2.duplicate_group_id IS NOT NULL
        ) group_review ON d.duplicate_group_id = group_review.dup_group_id AND r.id IS NULL
        LEFT JOIN article a ON a.document_id = d.id
        LEFT JOIN inproceedings i ON i.document_id = d.id
        LEFT JOIN inbook ib ON ib.document_id = d.id
        WHERE d.search_id = ?
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
                review_id=row["review_id"],
                included=row["included"]
                if row["included"] is None
                else bool(row["included"]),
                notes=row["notes"],
                domain=row["domain"],
                reference=row["reference"]
                if row["reference"] is None
                else bool(row["reference"]),
                duplicate_group_id=row["duplicate_group_id"],
            )
        )
    conn.close()
    return documents


def get_all_documents() -> list[Document]:
    """Get all documents across all searches."""
    conn = get_connection()
    cursor = conn.cursor()
    # Use subquery to find review for duplicate groups
    cursor.execute("""
        SELECT
            d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
            d.duplicate_group_id,
            s.source as search_source,
            COALESCE(r.id, group_review.id) as review_id,
            COALESCE(r.included, group_review.included) as included,
            COALESCE(r.notes, group_review.notes) as notes,
            COALESCE(r.domain, group_review.domain) as domain,
            COALESCE(r.reference, group_review.reference) as reference,
            COALESCE(a.author, i.author, ib.author) as author,
            COALESCE(a.year, i.year, ib.year) as year,
            COALESCE(a.abstract, i.abstract, ib.abstract) as abstract,
            COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
            a.journal,
            COALESCE(i.booktitle, ib.booktitle) as booktitle
        FROM document d
        JOIN search s ON d.search_id = s.id
        LEFT JOIN review r ON r.document_id = d.id
        LEFT JOIN (
            SELECT r2.*, d2.duplicate_group_id as dup_group_id
            FROM review r2
            JOIN document d2 ON r2.document_id = d2.id
            WHERE d2.duplicate_group_id IS NOT NULL
        ) group_review ON d.duplicate_group_id = group_review.dup_group_id AND r.id IS NULL
        LEFT JOIN article a ON a.document_id = d.id
        LEFT JOIN inproceedings i ON i.document_id = d.id
        LEFT JOIN inbook ib ON ib.document_id = d.id
        ORDER BY d.id
    """)

    documents = []
    for row in cursor.fetchall():
        doc = Document(
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
            review_id=row["review_id"],
            included=row["included"]
            if row["included"] is None
            else bool(row["included"]),
            notes=row["notes"],
            domain=row["domain"],
            reference=row["reference"]
            if row["reference"] is None
            else bool(row["reference"]),
            duplicate_group_id=row["duplicate_group_id"],
        )
        # Store search source as an extra attribute for filtering
        doc._search_source = row["search_source"]
        documents.append(doc)
    conn.close()
    return documents


def get_all_venues() -> list[str]:
    """Get all unique venues (journals and booktitles) from the database."""
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


def get_duplicate_searches(
    doc_id: int, duplicate_group_id: int
) -> list[tuple[int, str]]:
    """Get other documents in the same duplicate group with their search names."""
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
    results = [(row["id"], row["source"]) for row in cursor.fetchall()]
    conn.close()
    return results


def get_exclusion_codes() -> list[tuple[int, str]]:
    """Get all exclusion codes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code FROM exclusion_code ORDER BY code")
    results = [(row["id"], row["code"]) for row in cursor.fetchall()]
    conn.close()
    return results


def get_review_exclusion_codes(review_id: int) -> list[str]:
    """Get exclusion codes for a review."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ec.code
        FROM review_exclusion_code rec
        JOIN exclusion_code ec ON ec.id = rec.exclusion_code_id
        WHERE rec.review_id = ?
    """,
        (review_id,),
    )
    results = [row["code"] for row in cursor.fetchall()]
    conn.close()
    return results


def save_review(
    review_id: int,
    included: bool | None,
    notes: str | None,
    domain: str | None,
    reference: bool | None,
) -> None:
    """Save review data."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE review
        SET included = ?, notes = ?, domain = ?, reference = ?
        WHERE id = ?
    """,
        (
            None if included is None else int(included),
            notes,
            domain,
            None if reference is None else int(reference),
            review_id,
        ),
    )
    conn.commit()
    conn.close()


def add_exclusion_code(code: str) -> int:
    """Add a new exclusion code, return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO exclusion_code (code) VALUES (?)", (code,))
    conn.commit()
    cursor.execute("SELECT id FROM exclusion_code WHERE code = ?", (code,))
    result = cursor.fetchone()["id"]
    conn.close()
    return result


def set_review_exclusion_codes(review_id: int, code_ids: list[int]) -> None:
    """Set exclusion codes for a review (replaces existing)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM review_exclusion_code WHERE review_id = ?", (review_id,)
    )
    for code_id in code_ids:
        cursor.execute(
            "INSERT INTO review_exclusion_code (review_id, exclusion_code_id) VALUES (?, ?)",
            (review_id, code_id),
        )
    conn.commit()
    conn.close()


# --- Settings Data Access ---


def get_setting(key: str, default: str = "") -> str:
    """Get a setting value by key."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    """Set a setting value."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def get_all_settings() -> dict[str, str]:
    """Get all settings as a dictionary."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings = {row["key"]: row["value"] for row in cursor.fetchall()}
    conn.close()
    return settings


# --- Pass Review Data Access ---


@dataclass
class PassReview:
    """Represents a pass-specific review."""

    id: int | None
    document_id: int
    pass_number: int
    decision: str | None = None  # 'include', 'exclude', 'uncertain'
    notes: str | None = None
    llm_suggestion: LLMSuggestion | None = None
    llm_accepted: bool | None = None
    exclusion_codes: list[str] = field(default_factory=list)


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

    # Get exclusion codes
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

    # Parse LLM suggestion if present
    llm_suggestion = None
    if row["llm_suggestion"]:
        try:
            data = json.loads(row["llm_suggestion"])
            llm_suggestion = LLMSuggestion(
                decision=data.get("decision", "uncertain"),
                reasoning=data.get("reasoning", ""),
                confidence=data.get("confidence", 0.0),
                exclusion_codes=data.get("exclusion_codes", []),
                raw_response=data.get("raw_response", ""),
                error=data.get("error"),
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


def get_all_pass_reviews() -> dict[tuple[int, int], PassReview]:
    """Get all pass reviews as a dict keyed by (document_id, pass_number)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get all pass reviews
    cursor.execute("""
        SELECT id, document_id, pass_number, decision, notes, llm_suggestion, llm_accepted
        FROM pass_review
    """)
    rows = cursor.fetchall()

    # Get all exclusion codes in one query
    cursor.execute("""
        SELECT prec.pass_review_id, ec.code
        FROM pass_review_exclusion_code prec
        JOIN exclusion_code ec ON ec.id = prec.exclusion_code_id
    """)
    codes_by_review: dict[int, list[str]] = {}
    for r in cursor.fetchall():
        codes_by_review.setdefault(r["pass_review_id"], []).append(r["code"])

    conn.close()

    result: dict[tuple[int, int], PassReview] = {}
    for row in rows:
        # Parse LLM suggestion if present
        llm_suggestion = None
        if row["llm_suggestion"]:
            try:
                data = json.loads(row["llm_suggestion"])
                llm_suggestion = LLMSuggestion(
                    decision=data.get("decision", "uncertain"),
                    reasoning=data.get("reasoning", ""),
                    confidence=data.get("confidence", 0.0),
                    exclusion_codes=data.get("exclusion_codes", []),
                    raw_response=data.get("raw_response", ""),
                    error=data.get("error"),
                    domain=data.get("domain"),
                    model=data.get("model"),
                    thinking_mode=data.get("thinking_mode"),
                    response_time_ms=data.get("response_time_ms"),
                    requested_at=data.get("requested_at"),
                )
            except json.JSONDecodeError:
                pass

        result[(row["document_id"], row["pass_number"])] = PassReview(
            id=row["id"],
            document_id=row["document_id"],
            pass_number=row["pass_number"],
            decision=row["decision"],
            notes=row["notes"],
            llm_suggestion=llm_suggestion,
            llm_accepted=None
            if row["llm_accepted"] is None
            else bool(row["llm_accepted"]),
            exclusion_codes=codes_by_review.get(row["id"], []),
        )

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


def save_pass_review(
    document_id: int,
    pass_number: int,
    decision: str | None,
    notes: str | None = None,
    llm_suggestion: LLMSuggestion | None = None,
    llm_accepted: bool | None = None,
) -> int:
    """Save or update a pass review. Returns the pass_review id."""
    conn = get_connection()
    cursor = conn.cursor()

    # Serialize LLM suggestion
    llm_json = None
    if llm_suggestion:
        llm_json = json.dumps(
            {
                "decision": llm_suggestion.decision,
                "reasoning": llm_suggestion.reasoning,
                "confidence": llm_suggestion.confidence,
                "exclusion_codes": llm_suggestion.exclusion_codes,
                "raw_response": llm_suggestion.raw_response,
                "error": llm_suggestion.error,
                "domain": llm_suggestion.domain,
                "model": llm_suggestion.model,
                "thinking_mode": llm_suggestion.thinking_mode,
                "response_time_ms": llm_suggestion.response_time_ms,
                "requested_at": llm_suggestion.requested_at,
            }
        )

    # Insert or update
    cursor.execute(
        """
        INSERT INTO pass_review (document_id, pass_number, decision, notes, llm_suggestion, llm_accepted)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id, pass_number) DO UPDATE SET
            decision = excluded.decision,
            notes = excluded.notes,
            llm_suggestion = excluded.llm_suggestion,
            llm_accepted = excluded.llm_accepted,
            reviewed_at = CURRENT_TIMESTAMP
    """,
        (
            document_id,
            pass_number,
            decision,
            notes,
            llm_json,
            None if llm_accepted is None else int(llm_accepted),
        ),
    )
    conn.commit()

    cursor.execute(
        "SELECT id FROM pass_review WHERE document_id = ? AND pass_number = ?",
        (document_id, pass_number),
    )
    pass_review_id = cursor.fetchone()["id"]
    conn.close()
    return pass_review_id


def set_pass_review_exclusion_codes(pass_review_id: int, code_ids: list[int]) -> None:
    """Set exclusion codes for a pass review (replaces existing)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM pass_review_exclusion_code WHERE pass_review_id = ?",
        (pass_review_id,),
    )
    for code_id in code_ids:
        cursor.execute(
            "INSERT INTO pass_review_exclusion_code (pass_review_id, exclusion_code_id) VALUES (?, ?)",
            (pass_review_id, code_id),
        )
    conn.commit()
    conn.close()


def get_documents_for_pass_review(search_id: int, pass_number: int) -> list[Document]:
    """Get documents eligible for review in a specific pass.

    Pass 1: All documents
    Pass 2: Only documents with Pass 1 decision of 'include' or 'uncertain'
    """
    conn = get_connection()
    cursor = conn.cursor()

    if pass_number == 1:
        # All documents in the search
        cursor.execute(
            """
            SELECT
                d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
                d.duplicate_group_id,
                r.id as review_id,
                r.included,
                r.notes,
                r.domain,
                r.reference,
                COALESCE(a.author, i.author, ib.author) as author,
                COALESCE(a.year, i.year, ib.year) as year,
                COALESCE(a.abstract, i.abstract, ib.abstract) as abstract,
                COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
                a.journal,
                COALESCE(i.booktitle, ib.booktitle) as booktitle
            FROM document d
            LEFT JOIN review r ON r.document_id = d.id
            LEFT JOIN article a ON a.document_id = d.id
            LEFT JOIN inproceedings i ON i.document_id = d.id
            LEFT JOIN inbook ib ON ib.document_id = d.id
            WHERE d.search_id = ?
            ORDER BY d.id
        """,
            (search_id,),
        )
    else:
        # Only documents with Pass 1 include or uncertain
        cursor.execute(
            """
            SELECT
                d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
                d.duplicate_group_id,
                r.id as review_id,
                r.included,
                r.notes,
                r.domain,
                r.reference,
                COALESCE(a.author, i.author, ib.author) as author,
                COALESCE(a.year, i.year, ib.year) as year,
                COALESCE(a.abstract, i.abstract, ib.abstract) as abstract,
                COALESCE(a.keywords, i.keywords, ib.keywords) as keywords,
                a.journal,
                COALESCE(i.booktitle, ib.booktitle) as booktitle
            FROM document d
            LEFT JOIN review r ON r.document_id = d.id
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
                review_id=row["review_id"],
                included=row["included"]
                if row["included"] is None
                else bool(row["included"]),
                notes=row["notes"],
                domain=row["domain"],
                reference=row["reference"]
                if row["reference"] is None
                else bool(row["reference"]),
            )
        )
    conn.close()
    return documents


def get_pass_progress(search_id: int) -> dict:
    """Get pass-specific progress stats for a search."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total documents in search
    cursor.execute(
        "SELECT COUNT(*) as total FROM document WHERE search_id = ?", (search_id,)
    )
    total = cursor.fetchone()["total"]

    # Pass 1 stats
    cursor.execute(
        """
        SELECT
            COUNT(*) as reviewed,
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

    # Pass 2 eligible (Pass 1 include or uncertain)
    pass2_eligible = (p1["included"] or 0) + (p1["uncertain"] or 0)

    # Pass 2 stats
    cursor.execute(
        """
        SELECT
            COUNT(*) as reviewed,
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
            "reviewed": p1["reviewed"] or 0,
            "included": p1["included"] or 0,
            "excluded": p1["excluded"] or 0,
            "uncertain": p1["uncertain"] or 0,
        },
        "pass2": {
            "eligible": pass2_eligible,
            "reviewed": p2["reviewed"] or 0,
            "included": p2["included"] or 0,
            "excluded": p2["excluded"] or 0,
            "uncertain": p2["uncertain"] or 0,
        },
    }


def get_exclusion_codes_with_descriptions() -> list[tuple[int, str, str | None]]:
    """Get all exclusion codes with descriptions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, code, description FROM exclusion_code ORDER BY code")
    results = [
        (row["id"], row["code"], row["description"]) for row in cursor.fetchall()
    ]
    conn.close()
    return results


# --- Tag Data Access ---


def get_all_tags() -> list[tuple[int, str]]:
    """Get all tags."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM tag ORDER BY name")
    results = [(row["id"], row["name"]) for row in cursor.fetchall()]
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


def add_tag(name: str) -> int:
    """Add a new tag, return its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO tag (name) VALUES (?)", (name,))
    conn.commit()
    cursor.execute("SELECT id FROM tag WHERE name = ?", (name,))
    result = cursor.fetchone()["id"]
    conn.close()
    return result


def set_document_tags(document_id: int, tag_ids: list[int]) -> None:
    """Set tags for a document (replaces existing)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM document_tag WHERE document_id = ?", (document_id,))
    for tag_id in tag_ids:
        cursor.execute(
            "INSERT INTO document_tag (document_id, tag_id) VALUES (?, ?)",
            (document_id, tag_id),
        )
    conn.commit()
    conn.close()


class ExclusionCodeModal(ModalScreen[list[int] | None]):
    """Modal for selecting exclusion codes with descriptions."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    CSS = """
    ExclusionCodeModal {
        align: center middle;
    }

    #modal-container {
        width: 80;
        height: auto;
        max-height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #code-list {
        height: auto;
        max-height: 18;
    }

    #selected-codes {
        margin-top: 1;
        height: auto;
        max-height: 5;
        color: $success;
    }

    #button-row {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
    }
    """

    def __init__(self, current_codes: list[str] | None = None) -> None:
        super().__init__()
        self.current_codes = current_codes or []
        self.selected_code_ids: list[int] = []
        self.all_codes: list[tuple[int, str, str | None]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("Select Exclusion Codes (type to search/add)")
            yield Input(placeholder="Search or type new code...", id="search-input")
            yield OptionList(id="code-list")
            yield Static("Selected: none", id="selected-codes")
            with Horizontal(id="button-row"):
                yield Button("Cancel", variant="default", id="cancel-btn")
                yield Button("Confirm", variant="primary", id="confirm-btn")

    def on_mount(self) -> None:
        self.all_codes = get_exclusion_codes_with_descriptions()
        # Pre-select current codes
        for code_id, code, _ in self.all_codes:
            if code in self.current_codes:
                self.selected_code_ids.append(code_id)
        self._refresh_code_list()
        self._update_selected_display()
        self.query_one("#search-input", Input).focus()

    def _refresh_code_list(self, filter_text: str = "") -> None:
        code_list = self.query_one("#code-list", OptionList)
        code_list.clear_options()

        filter_lower = filter_text.lower()
        for code_id, code, description in self.all_codes:
            # Search in code and description
            searchable = code.lower()
            if description:
                searchable += " " + description.lower()

            if filter_lower in searchable:
                prefix = "[X] " if code_id in self.selected_code_ids else "[ ] "
                # Format with description
                if description:
                    label = f"{prefix}{code}: {description}"
                else:
                    label = f"{prefix}{code}"
                code_list.add_option(Option(label, id=str(code_id)))

        # If no match and there's text, offer to create new
        if filter_text and not any(
            filter_lower == code.lower() for _, code, _ in self.all_codes
        ):
            code_list.add_option(
                Option(f"[+] Create: {filter_text}", id=f"new:{filter_text}")
            )

    def _update_selected_display(self) -> None:
        selected_names = [
            code
            for code_id, code, _ in self.all_codes
            if code_id in self.selected_code_ids
        ]
        display = self.query_one("#selected-codes", Static)
        if selected_names:
            display.update(f"Selected: {', '.join(selected_names)}")
        else:
            display.update("Selected: none")

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self._refresh_code_list(event.value)

    @on(OptionList.OptionSelected, "#code-list")
    def on_code_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id and option_id.startswith("new:"):
            # Create new code
            new_code = option_id[4:]
            code_id = add_exclusion_code(new_code)
            self.all_codes = get_exclusion_codes_with_descriptions()  # Refresh
            self.selected_code_ids.append(code_id)
            self.query_one("#search-input", Input).value = ""
        elif option_id:
            code_id = int(option_id)
            if code_id in self.selected_code_ids:
                self.selected_code_ids.remove(code_id)
            else:
                self.selected_code_ids.append(code_id)

        self._refresh_code_list(self.query_one("#search-input", Input).value)
        self._update_selected_display()

    @on(Button.Pressed, "#cancel-btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-btn")
    def action_confirm(self) -> None:
        self.dismiss(self.selected_code_ids)


class TagModal(ModalScreen[list[int] | None]):
    """Modal for selecting tags."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    CSS = """
    TagModal {
        align: center middle;
    }

    #tag-modal-container {
        width: 60;
        height: auto;
        max-height: 70%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #tag-search-input {
        width: 100%;
        margin-bottom: 1;
    }

    #tag-list {
        height: auto;
        max-height: 15;
    }

    #selected-tags {
        margin-top: 1;
        height: auto;
        max-height: 3;
        color: $success;
    }

    #tag-button-row {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    #tag-button-row Button {
        margin: 0 1;
    }
    """

    def __init__(self, document_id: int, current_tags: list[str] | None = None) -> None:
        super().__init__()
        self.document_id = document_id
        self.current_tags = current_tags or []
        self.selected_tag_ids: list[int] = []
        self.all_tags: list[tuple[int, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="tag-modal-container"):
            yield Label("Select Tags (type to search/add)")
            yield Input(placeholder="Search or type new tag...", id="tag-search-input")
            yield OptionList(id="tag-list")
            yield Static("Selected: none", id="selected-tags")
            with Horizontal(id="tag-button-row"):
                yield Button("Cancel", variant="default", id="tag-cancel-btn")
                yield Button("Confirm", variant="primary", id="tag-confirm-btn")

    def on_mount(self) -> None:
        self.all_tags = get_all_tags()
        # Pre-select current tags
        for tag_id, tag_name in self.all_tags:
            if tag_name in self.current_tags:
                self.selected_tag_ids.append(tag_id)
        self._refresh_tag_list()
        self._update_selected_display()
        self.query_one("#tag-search-input", Input).focus()

    def _refresh_tag_list(self, filter_text: str = "") -> None:
        tag_list = self.query_one("#tag-list", OptionList)
        tag_list.clear_options()

        filter_lower = filter_text.lower()
        for tag_id, tag_name in self.all_tags:
            if filter_lower in tag_name.lower():
                prefix = "[X] " if tag_id in self.selected_tag_ids else "[ ] "
                tag_list.add_option(Option(f"{prefix}{tag_name}", id=str(tag_id)))

        # If no match and there's text, offer to create new
        if filter_text and not any(
            filter_lower == name.lower() for _, name in self.all_tags
        ):
            tag_list.add_option(
                Option(f"[+] Create: {filter_text}", id=f"new:{filter_text}")
            )

    def _update_selected_display(self) -> None:
        selected_names = [
            name for tag_id, name in self.all_tags if tag_id in self.selected_tag_ids
        ]
        display = self.query_one("#selected-tags", Static)
        if selected_names:
            display.update(f"Selected: {', '.join(selected_names)}")
        else:
            display.update("Selected: none")

    @on(Input.Changed, "#tag-search-input")
    def on_tag_search_changed(self, event: Input.Changed) -> None:
        self._refresh_tag_list(event.value)

    @on(OptionList.OptionSelected, "#tag-list")
    def on_tag_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id and option_id.startswith("new:"):
            # Create new tag
            new_tag = option_id[4:]
            tag_id = add_tag(new_tag)
            self.all_tags = get_all_tags()  # Refresh
            self.selected_tag_ids.append(tag_id)
            self.query_one("#tag-search-input", Input).value = ""
        elif option_id:
            tag_id = int(option_id)
            if tag_id in self.selected_tag_ids:
                self.selected_tag_ids.remove(tag_id)
            else:
                self.selected_tag_ids.append(tag_id)

        self._refresh_tag_list(self.query_one("#tag-search-input", Input).value)
        self._update_selected_display()

    @on(Button.Pressed, "#tag-cancel-btn")
    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#tag-confirm-btn")
    def action_confirm(self) -> None:
        self.dismiss(self.selected_tag_ids)


class SettingsScreen(Screen):
    """Settings screen for LLM configuration."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("q", "go_back", "Back"),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-container {
        width: 70;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    .setting-row {
        height: 3;
        margin-bottom: 1;
    }

    .setting-label {
        width: 20;
        padding-top: 1;
    }

    .setting-input {
        width: 1fr;
    }

    #test-connection-row {
        height: auto;
        margin-top: 1;
    }

    #connection-status {
        margin-top: 1;
        height: 3;
    }

    #button-row {
        height: 3;
        min-height: 3;
        margin-top: 2;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="settings-container"):
            yield Label("[bold]LLM Settings[/bold]")
            yield Static("")

            with Horizontal(classes="setting-row"):
                yield Label("Auto-Suggest:", classes="setting-label")
                yield Switch(id="auto-suggest-switch")
                yield Label(
                    "Request LLM suggestion automatically", classes="setting-input"
                )

            with Horizontal(classes="setting-row"):
                yield Label("Thinking Mode:", classes="setting-label")
                yield Switch(id="thinking-switch")
                yield Label("Enable step-by-step reasoning", classes="setting-input")

            with Horizontal(classes="setting-row"):
                yield Label("Model:", classes="setting-label")
                yield Input(
                    placeholder="qwen3:8b", id="model-input", classes="setting-input"
                )

            with Horizontal(classes="setting-row"):
                yield Label("Ollama Host:", classes="setting-label")
                yield Input(
                    placeholder="http://localhost:11434",
                    id="host-input",
                    classes="setting-input",
                )

            with Horizontal(id="test-connection-row"):
                yield Button("Test Connection", id="test-btn")

            yield Static("", id="connection-status")

            with Horizontal(id="button-row"):
                yield Button("Cancel", variant="default", id="cancel-btn")
                yield Button("Save", variant="primary", id="save-btn")

        yield Footer()

    def on_mount(self) -> None:
        # Load current settings
        settings = get_all_settings()

        auto_suggest = settings.get("llm_auto_suggest", "false") == "true"
        thinking = settings.get("llm_thinking_mode", "true") == "true"
        model = settings.get("llm_model", "qwen3:8b")
        host = settings.get("llm_host", "http://localhost:11434")

        self.query_one("#auto-suggest-switch", Switch).value = auto_suggest
        self.query_one("#thinking-switch", Switch).value = thinking
        self.query_one("#model-input", Input).value = model
        self.query_one("#host-input", Input).value = host

    @on(Button.Pressed, "#test-btn")
    def on_test_connection(self) -> None:
        self._test_connection()

    @work(exclusive=True)
    async def _test_connection(self) -> None:
        status = self.query_one("#connection-status", Static)
        status.update("[yellow]Testing connection...[/yellow]")

        model = self.query_one("#model-input", Input).value or "qwen3:8b"
        host = self.query_one("#host-input", Input).value or "http://localhost:11434"

        assistant = LLMAssistant(host=host, model=model)
        success, message = await assistant.test_connection()

        if success:
            status.update(f"[green]{message}[/green]")
        else:
            status.update(f"[red]{message}[/red]")

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#save-btn")
    def on_save(self) -> None:
        auto_suggest = self.query_one("#auto-suggest-switch", Switch).value
        thinking = self.query_one("#thinking-switch", Switch).value
        model = self.query_one("#model-input", Input).value or "qwen3:8b"
        host = self.query_one("#host-input", Input).value or "http://localhost:11434"

        set_setting("llm_auto_suggest", "true" if auto_suggest else "false")
        set_setting("llm_thinking_mode", "true" if thinking else "false")
        set_setting("llm_model", model)
        set_setting("llm_host", host)

        self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()


class MainMenuScreen(Screen):
    """Main menu for selecting mode and search."""

    BINDINGS = [
        Binding("s", "open_settings", "Settings"),
    ]

    CSS = """
    MainMenuScreen {
        align: center middle;
    }

    #menu-container {
        width: 80;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #search-list {
        height: auto;
        max-height: 12;
        margin-bottom: 1;
    }

    #progress-display {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        background: $surface-darken-1;
    }

    #mode-buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #mode-buttons Button {
        margin: 0 1;
    }

    #secondary-buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #secondary-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.selected_search_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="menu-container"):
            yield Label("Select a Search:")
            yield OptionList(id="search-list")
            yield Static("", id="progress-display")
            yield Label("Choose review mode:")
            with Horizontal(id="mode-buttons"):
                yield Button("Pass 1", variant="primary", id="pass1-btn")
                yield Button("Pass 2", variant="primary", id="pass2-btn")
            with Horizontal(id="secondary-buttons"):
                yield Button("Browse All", variant="default", id="browse-btn")
                yield Button("Settings", variant="default", id="settings-btn")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_search_list()

    def _refresh_search_list(self) -> None:
        searches = get_searches()
        search_list = self.query_one("#search-list", OptionList)
        search_list.clear_options()

        for search_id, source, total, _ in searches:
            progress = get_pass_progress(search_id)
            p1_done = progress["pass1"]["reviewed"]
            p2_done = progress["pass2"]["reviewed"]
            p2_eligible = progress["pass2"]["eligible"]

            label = f"{source} | P1: {p1_done}/{total} | P2: {p2_done}/{p2_eligible}"
            search_list.add_option(Option(label, id=str(search_id)))

        # Select first by default
        if searches:
            self.selected_search_id = searches[0][0]
            search_list.highlighted = 0
            self._update_progress_display()

    def _update_progress_display(self) -> None:
        if not self.selected_search_id:
            return

        progress = get_pass_progress(self.selected_search_id)
        total = progress["total"]
        p1 = progress["pass1"]
        p2 = progress["pass2"]

        p1_pct = (p1["reviewed"] / total * 100) if total > 0 else 0
        p2_pct = (p2["reviewed"] / p2["eligible"] * 100) if p2["eligible"] > 0 else 0

        display = self.query_one("#progress-display", Static)
        display.update(
            f"[bold]Pass 1:[/bold] {p1['reviewed']}/{total} ({p1_pct:.0f}%) - "
            f"[green]Inc: {p1['included']}[/green] | [red]Exc: {p1['excluded']}[/red] | [yellow]Unc: {p1['uncertain']}[/yellow]\n"
            f"[bold]Pass 2:[/bold] {p2['reviewed']}/{p2['eligible']} ({p2_pct:.0f}%) - "
            f"[green]Inc: {p2['included']}[/green] | [red]Exc: {p2['excluded']}[/red] | [yellow]Unc: {p2['uncertain']}[/yellow]"
        )

    @on(OptionList.OptionHighlighted, "#search-list")
    def on_search_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            self.selected_search_id = int(event.option.id)
            self._update_progress_display()

    @on(Button.Pressed, "#pass1-btn")
    def on_pass1_pressed(self) -> None:
        if self.selected_search_id:
            self.app.push_screen(
                PassReviewScreen(self.selected_search_id, pass_number=1)
            )

    @on(Button.Pressed, "#pass2-btn")
    def on_pass2_pressed(self) -> None:
        if self.selected_search_id:
            self.app.push_screen(
                PassReviewScreen(self.selected_search_id, pass_number=2)
            )

    @on(Button.Pressed, "#browse-btn")
    def on_browse_pressed(self) -> None:
        self.app.push_screen(BrowseScreen())

    @on(Button.Pressed, "#settings-btn")
    def on_settings_pressed(self) -> None:
        self.app.push_screen(SettingsScreen())

    def action_open_settings(self) -> None:
        self.app.push_screen(SettingsScreen())


class BrowseScreen(Screen):
    """Screen for browsing and filtering all papers across all searches."""

    BINDINGS = [
        Binding("q", "go_back", "Back"),
        Binding("r", "reset_filters", "Reset Filters"),
    ]

    CSS = """
    BrowseScreen {
        layout: vertical;
    }

    #filter-bar {
        height: auto;
        padding: 0 1;
        background: $surface;
    }

    #filter-row-1, #filter-row-2 {
        height: 3;
        align: left middle;
    }

    #filter-bar Label {
        margin-right: 1;
        padding-top: 1;
    }

    #filter-bar Select {
        width: 18;
        margin-right: 1;
    }

    #venue-filter {
        width: 30;
    }

    #papers-table {
        height: 1fr;
    }

    #stats-bar {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.documents: list[Document] = []
        self.searches: list[tuple[int, str, int, int]] = []
        self.exclusion_codes: list[tuple[int, str]] = []
        self.venues: list[str] = []
        self.tags: list[tuple[int, str]] = []
        # Cached pass reviews and tags for performance
        self.pass_reviews: dict[tuple[int, int], PassReview] = {}
        self.document_tags: dict[int, list[str]] = {}
        # Filter states
        self.current_filter_code: str | None = None
        self.current_filter_search: int | None = None
        self.current_filter_venue: str | None = None
        self.current_filter_pass1: str | None = None
        self.current_filter_pass2: str | None = None
        self.current_filter_tag: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="filter-bar"):
            with Horizontal(id="filter-row-1"):
                yield Label("Pass 1:")
                yield Select(
                    [
                        ("All", "all"),
                        ("Pending", "pending"),
                        ("Include", "include"),
                        ("Exclude", "exclude"),
                        ("Uncertain", "uncertain"),
                    ],
                    value="all",
                    id="pass1-filter",
                    allow_blank=False,
                )
                yield Label("Pass 2:")
                yield Select(
                    [
                        ("All", "all"),
                        ("Pending", "pending"),
                        ("Include", "include"),
                        ("Exclude", "exclude"),
                        ("Uncertain", "uncertain"),
                    ],
                    value="all",
                    id="pass2-filter",
                    allow_blank=False,
                )
                yield Label("Search:")
                yield Select(
                    [("All", "all")],
                    value="all",
                    id="search-filter",
                    allow_blank=False,
                )
            with Horizontal(id="filter-row-2"):
                yield Label("Code:")
                yield Select(
                    [("All", "all")],
                    value="all",
                    id="code-filter",
                    allow_blank=False,
                )
                yield Label("Venue:")
                yield Select(
                    [("All", "all")],
                    value="all",
                    id="venue-filter",
                    allow_blank=False,
                )
                yield Label("Tag:")
                yield Select(
                    [("All", "all")],
                    value="all",
                    id="tag-filter",
                    allow_blank=False,
                )
        yield DataTable(id="papers-table")
        yield Static("", id="stats-bar")
        yield Footer()

    def on_mount(self) -> None:
        # Load all data
        self.documents = get_all_documents()
        self.searches = get_searches()
        self.exclusion_codes = get_exclusion_codes()
        self.venues = get_all_venues()
        self.tags = get_all_tags()
        # Batch load pass reviews and tags for performance
        self.pass_reviews = get_all_pass_reviews()
        self.document_tags = get_all_document_tags()

        # Populate exclusion code filter
        code_filter = self.query_one("#code-filter", Select)
        code_options = [("All", "all")] + [
            (code, code) for _, code in self.exclusion_codes
        ]
        code_filter.set_options(code_options)

        # Populate search filter
        search_filter = self.query_one("#search-filter", Select)
        search_options = [("All", "all")] + [
            (source, str(sid)) for sid, source, _, _ in self.searches
        ]
        search_filter.set_options(search_options)

        # Populate venue filter
        venue_filter = self.query_one("#venue-filter", Select)
        # Truncate long venue names for display
        venue_options = [("All", "all")]
        for venue in self.venues:
            display = venue if len(venue) <= 40 else venue[:37] + "..."
            venue_options.append((display, venue))
        venue_filter.set_options(venue_options)

        # Populate tag filter
        tag_filter = self.query_one("#tag-filter", Select)
        tag_options = [("All", "all")] + [(name, name) for _, name in self.tags]
        tag_filter.set_options(tag_options)

        # Setup table
        table = self.query_one("#papers-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("P1", "P2", "Title", "Year", "Search", "Venue")

        self._refresh_table()

    def _get_venue(self, doc: Document) -> str:
        """Get venue (journal or booktitle)."""
        venue = doc.journal or doc.booktitle or ""
        if len(venue) > 30:
            venue = venue[:27] + "..."
        return venue

    def _get_search_source(self, doc: Document) -> str:
        """Get search source name for document."""
        # Use the cached _search_source attribute
        source = getattr(doc, "_search_source", None)
        if source:
            if len(source) > 20:
                return source[:17] + "..."
            return source
        return ""

    def _get_pass_status_text(self, doc: Document, pass_number: int) -> Text:
        """Get styled pass status text."""
        review = self.pass_reviews.get((doc.id, pass_number))
        status = Text()
        if not review or review.decision is None:
            status.append("-", style="dim")
        elif review.decision == "include":
            status.append("Inc", style="green")
        elif review.decision == "exclude":
            status.append("Exc", style="red")
        else:  # uncertain
            status.append("Unc", style="yellow")
        return status

    def _filter_documents(self) -> list[Document]:
        """Filter documents based on current filters."""
        filtered = self.documents

        # Search filter
        if self.current_filter_search is not None:
            filtered = [
                d for d in filtered if d.search_id == self.current_filter_search
            ]

        # Venue filter
        if self.current_filter_venue and self.current_filter_venue != "all":
            filtered = [
                d
                for d in filtered
                if (
                    d.journal == self.current_filter_venue
                    or d.booktitle == self.current_filter_venue
                )
            ]

        # Pass 1 filter
        if self.current_filter_pass1:
            filtered_by_pass1 = []
            for doc in filtered:
                review = self.pass_reviews.get((doc.id, 1))
                if self.current_filter_pass1 == "pending":
                    if not review or review.decision is None:
                        filtered_by_pass1.append(doc)
                elif review and review.decision == self.current_filter_pass1:
                    filtered_by_pass1.append(doc)
            filtered = filtered_by_pass1

        # Pass 2 filter
        if self.current_filter_pass2:
            filtered_by_pass2 = []
            for doc in filtered:
                review = self.pass_reviews.get((doc.id, 2))
                if self.current_filter_pass2 == "pending":
                    if not review or review.decision is None:
                        filtered_by_pass2.append(doc)
                elif review and review.decision == self.current_filter_pass2:
                    filtered_by_pass2.append(doc)
            filtered = filtered_by_pass2

        # Exclusion code filter (from pass reviews)
        if self.current_filter_code and self.current_filter_code != "all":
            filtered_by_code = []
            for doc in filtered:
                # Check both pass 1 and pass 2 for exclusion codes
                p1 = self.pass_reviews.get((doc.id, 1))
                p2 = self.pass_reviews.get((doc.id, 2))
                codes = []
                if p1:
                    codes.extend(p1.exclusion_codes)
                if p2:
                    codes.extend(p2.exclusion_codes)
                if self.current_filter_code in codes:
                    filtered_by_code.append(doc)
            filtered = filtered_by_code

        # Tag filter
        if self.current_filter_tag and self.current_filter_tag != "all":
            filtered_by_tag = []
            for doc in filtered:
                tags = self.document_tags.get(doc.id, [])
                if self.current_filter_tag in tags:
                    filtered_by_tag.append(doc)
            filtered = filtered_by_tag

        return filtered

    def _refresh_table(self) -> None:
        """Refresh the table with current filters."""
        table = self.query_one("#papers-table", DataTable)
        table.clear()

        filtered_docs = self._filter_documents()

        for doc in filtered_docs:
            # Wrap title
            title = doc.title or "No title"
            if len(title) > 50:
                title = title[:47] + "..."

            table.add_row(
                self._get_pass_status_text(doc, 1),
                self._get_pass_status_text(doc, 2),
                title,
                doc.year or "",
                self._get_search_source(doc),
                self._get_venue(doc),
                key=str(doc.id),
            )

        # Update stats based on pass reviews
        total = len(self.documents)
        showing = len(filtered_docs)

        # Count pass 1 stats using cached data
        p1_inc = sum(
            1
            for d in self.documents
            if (r := self.pass_reviews.get((d.id, 1))) and r.decision == "include"
        )
        p1_exc = sum(
            1
            for d in self.documents
            if (r := self.pass_reviews.get((d.id, 1))) and r.decision == "exclude"
        )

        stats = self.query_one("#stats-bar", Static)
        stats.update(f"Showing {showing}/{total} | P1 Inc: {p1_inc} | P1 Exc: {p1_exc}")

    @on(Select.Changed, "#pass1-filter")
    def on_pass1_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_pass1 = None if value == "all" else value
        self._refresh_table()

    @on(Select.Changed, "#pass2-filter")
    def on_pass2_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_pass2 = None if value == "all" else value
        self._refresh_table()

    @on(Select.Changed, "#search-filter")
    def on_search_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_search = None if value == "all" else int(value)
        self._refresh_table()

    @on(Select.Changed, "#code-filter")
    def on_code_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_code = None if value == "all" else value
        self._refresh_table()

    @on(Select.Changed, "#venue-filter")
    def on_venue_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_venue = None if value == "all" else value
        self._refresh_table()

    @on(Select.Changed, "#tag-filter")
    def on_tag_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_tag = None if value == "all" else value
        self._refresh_table()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_reset_filters(self) -> None:
        self.query_one("#pass1-filter", Select).value = "all"
        self.query_one("#pass2-filter", Select).value = "all"
        self.query_one("#search-filter", Select).value = "all"
        self.query_one("#code-filter", Select).value = "all"
        self.query_one("#venue-filter", Select).value = "all"
        self.query_one("#tag-filter", Select).value = "all"
        self.current_filter_pass1 = None
        self.current_filter_pass2 = None
        self.current_filter_search = None
        self.current_filter_code = None
        self.current_filter_venue = None
        self.current_filter_tag = None
        self._refresh_table()

    @on(DataTable.RowSelected, "#papers-table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open the selected paper in pass 1 review screen."""
        if event.row_key and event.row_key.value:
            doc_id = int(event.row_key.value)
            # Find the document to get its search_id
            doc = next((d for d in self.documents if d.id == doc_id), None)
            if doc:
                # Check if pass 1 is done, if so open pass 2
                p1 = self.pass_reviews.get((doc.id, 1))
                pass_num = 2 if p1 and p1.decision else 1
                self.app.push_screen(
                    PassReviewScreen(
                        doc.search_id, pass_number=pass_num, start_doc_id=doc_id
                    )
                )


class PassReviewScreen(Screen):
    """Screen for pass-specific paper review with LLM assistance."""

    BINDINGS = [
        Binding("j", "next_paper", "Next"),
        Binding("k", "prev_paper", "Previous"),
        Binding("i", "include", "Include"),
        Binding("x", "exclude", "Exclude"),
        Binding("?", "uncertain", "Uncertain"),
        Binding("l", "request_llm", "LLM Suggest"),
        Binding("y", "accept_llm", "Accept LLM"),
        Binding("n", "reject_llm", "Reject LLM"),
        Binding("t", "edit_tags", "Tags"),
        Binding("h", "set_health", "Health"),
        Binding("e", "set_environmental", "Environmental"),
        Binding("g", "random_unreviewed", "Random"),
        Binding("q", "go_back", "Back"),
    ]

    CSS = """
    PassReviewScreen {
        layout: horizontal;
    }

    #main-content {
        width: 2fr;
        height: 100%;
        padding: 1;
    }

    #sidebar {
        width: 1fr;
        height: 100%;
        background: $surface;
        border-left: thick $primary;
        padding: 1;
    }

    #pass-header {
        height: 3;
        background: $primary;
        padding: 0 1;
        text-style: bold;
    }

    #progress-bar {
        height: 3;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #paper-display {
        height: 1fr;
        padding: 1;
    }

    #title-display {
        text-style: bold;
        margin-bottom: 1;
        height: auto;
    }

    #metadata-display {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }

    #abstract-container {
        height: auto;
        margin-top: 1;
    }

    #abstract-label {
        text-style: bold;
        margin-bottom: 1;
    }

    #abstract-display {
        height: auto;
    }

    .abstract-hidden {
        display: none;
    }

    #status-row {
        height: 3;
        padding: 0 1;
    }

    #action-row {
        height: 5;
        padding: 1;
    }

    #action-row Button {
        margin: 0 1;
    }

    #notes-area {
        height: 6;
        margin-top: 1;
    }

    #llm-panel {
        height: auto;
        margin-top: 1;
        padding: 1;
        background: $surface-darken-1;
        border: solid $primary;
    }

    #llm-status {
        height: auto;
    }

    #llm-decision {
        margin-top: 1;
        height: auto;
    }

    #llm-reasoning {
        margin-top: 1;
        height: auto;
        max-height: 15;
        overflow-y: auto;
    }

    #llm-codes {
        margin-top: 1;
        height: auto;
    }

    #llm-buttons {
        margin-top: 1;
        height: 3;
        min-height: 3;
    }

    #llm-buttons Button {
        margin-right: 1;
    }

    .llm-include {
        color: $success;
    }

    .llm-exclude {
        color: $error;
    }

    .llm-uncertain {
        color: $warning;
    }
    """

    def __init__(
        self, search_id: int, pass_number: int, start_doc_id: int | None = None
    ) -> None:
        super().__init__()
        self.search_id = search_id
        self.pass_number = pass_number
        self.start_doc_id = start_doc_id
        self.documents: list[Document] = []
        self.current_index = 0
        self.current_llm_suggestion: LLMSuggestion | None = None
        self.llm_loading = False
        # Cached pass reviews for performance
        self.pass_reviews_cache: dict[int, PassReview | None] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="main-content"):
                yield Static("", id="pass-header")
                yield Static("", id="progress-bar")
                with VerticalScroll(id="paper-display"):
                    yield Static("", id="title-display")
                    yield Static("", id="metadata-display")
                    with Vertical(id="abstract-container"):
                        yield Static("[bold]Abstract[/bold]", id="abstract-label")
                        yield Static("", id="abstract-display")
                yield Static("", id="status-row")
                with Horizontal(id="action-row"):
                    yield Button("Include [i]", variant="success", id="include-btn")
                    yield Button("Exclude [x]", variant="error", id="exclude-btn")
                    yield Button("Uncertain [?]", variant="warning", id="uncertain-btn")
                yield TextArea(id="notes-area")
            with VerticalScroll(id="sidebar"):
                yield Static("", id="sidebar-content")
                with Vertical(id="llm-panel"):
                    yield Static("[bold]LLM Assistant[/bold]", id="llm-status")
                    yield Static("", id="llm-metadata")
                    yield Static("", id="llm-decision")
                    yield Static("", id="llm-reasoning")
                    yield Static("", id="llm-codes")
                    with Horizontal(id="llm-buttons"):
                        yield Button(
                            "Request [l]", variant="default", id="llm-request-btn"
                        )
                        yield Button(
                            "Accept [y]", variant="success", id="llm-accept-btn"
                        )
                        yield Button("Reject [n]", variant="error", id="llm-reject-btn")
        yield Footer()

    def _load_pass_reviews_cache(self) -> None:
        """Batch load pass reviews for all documents in this search."""
        all_reviews = get_all_pass_reviews()
        self.pass_reviews_cache = {}
        for doc in self.documents:
            self.pass_reviews_cache[doc.id] = all_reviews.get(
                (doc.id, self.pass_number)
            )

    def _get_cached_review(self, doc_id: int) -> PassReview | None:
        """Get pass review from cache, falling back to DB if not cached."""
        if doc_id in self.pass_reviews_cache:
            return self.pass_reviews_cache[doc_id]
        # Fallback for any uncached documents
        review = get_pass_review(doc_id, self.pass_number)
        self.pass_reviews_cache[doc_id] = review
        return review

    def _invalidate_cache(self, doc_id: int) -> None:
        """Invalidate cache for a document after saving."""
        if doc_id in self.pass_reviews_cache:
            del self.pass_reviews_cache[doc_id]

    def on_mount(self) -> None:
        self.documents = get_documents_for_pass_review(self.search_id, self.pass_number)

        # Batch load pass reviews for performance
        self._load_pass_reviews_cache()

        # Update pass header
        pass_type = "Title/Metadata" if self.pass_number == 1 else "Abstract Review"
        self.query_one("#pass-header", Static).update(
            f"PASS {self.pass_number}: {pass_type}"
        )

        # Hide abstract in Pass 1
        if self.pass_number == 1:
            self.query_one("#abstract-container").add_class("abstract-hidden")

        # If a specific document was requested, find it
        if self.start_doc_id is not None:
            for i, doc in enumerate(self.documents):
                if doc.id == self.start_doc_id:
                    self.current_index = i
                    break
        else:
            # Find first unreviewed document
            for i, doc in enumerate(self.documents):
                review = self._get_cached_review(doc.id)
                if review is None or review.decision is None:
                    self.current_index = i
                    break

        self._update_display()

        # Check if auto-suggest is enabled
        if get_setting("llm_auto_suggest", "false") == "true":
            self._request_llm_suggestion()

    def _get_current_doc(self) -> Document | None:
        if 0 <= self.current_index < len(self.documents):
            return self.documents[self.current_index]
        return None

    def _update_display(self) -> None:
        doc = self._get_current_doc()
        if not doc:
            self.query_one("#title-display", Static).update("No papers to review")
            return

        # Get current review
        review = self._get_cached_review(doc.id)

        # Progress bar
        total = len(self.documents)
        reviewed = sum(
            1
            for d in self.documents
            if (r := self._get_cached_review(d.id)) and r.decision is not None
        )
        progress = self.query_one("#progress-bar", Static)
        progress.update(
            f"Paper {self.current_index + 1}/{total} | Reviewed: {reviewed}/{total} ({reviewed / total * 100:.0f}%)"
        )

        # Title
        title_display = self.query_one("#title-display", Static)
        title_text = doc.title or "No title"
        if doc.year:
            title_text += f" ({doc.year})"
        title_display.update(title_text)

        # Metadata
        metadata_parts = []
        if doc.author:
            authors = doc.author
            if len(authors) > 80:
                authors = authors[:77] + "..."
            metadata_parts.append(f"Authors: {authors}")
        venue = doc.journal or doc.booktitle
        if venue:
            metadata_parts.append(f"Venue: {venue}")
        if doc.keywords:
            metadata_parts.append(f"Keywords: {doc.keywords}")

        self.query_one("#metadata-display", Static).update("\n".join(metadata_parts))

        # Abstract (only in Pass 2)
        if self.pass_number == 2:
            self.query_one("#abstract-display", Static).update(
                doc.abstract or "No abstract available"
            )

        # Status row
        status_row = self.query_one("#status-row", Static)
        if review and review.decision:
            decision_colors = {
                "include": "green",
                "exclude": "red",
                "uncertain": "yellow",
            }
            color = decision_colors.get(review.decision, "white")
            status_parts = [f"[{color}]{review.decision.upper()}[/{color}]"]
            if review.exclusion_codes:
                status_parts.append(f"Codes: {', '.join(review.exclusion_codes)}")
            status_row.update(" | ".join(status_parts))
        else:
            status_row.update("[yellow]PENDING[/yellow]")

        # Notes
        notes_area = self.query_one("#notes-area", TextArea)
        notes_area.text = review.notes if review and review.notes else ""

        # Sidebar
        self._update_sidebar()

        # LLM panel
        self._update_llm_panel(review)

    def _update_sidebar(self) -> None:
        doc = self._get_current_doc()
        if not doc:
            return

        sidebar = self.query_one("#sidebar-content", Static)
        parts = []

        parts.append("[bold]Details[/bold]")
        parts.append(f"[dim]Type:[/dim] {doc.entry_type}")

        if doc.doi:
            parts.append(f"[dim]DOI:[/dim] {doc.doi}")

        parts.append("")
        parts.append("[bold]Bibtex Key[/bold]")
        parts.append(doc.bibtex_key)

        # Show domain
        if doc.domain:
            parts.append("")
            color = "green" if doc.domain == "health" else "yellow"
            parts.append(f"[bold {color}]Domain: {doc.domain.upper()}[/bold {color}]")

        # Show tags
        tags = get_document_tags(doc.id)
        if tags:
            parts.append("")
            parts.append("[bold cyan]Tags[/bold cyan]")
            parts.append(", ".join(tags))

        # Show duplicate info
        if doc.duplicate_group_id:
            duplicates = get_duplicate_searches(doc.id, doc.duplicate_group_id)
            if duplicates:
                parts.append("")
                parts.append("[bold yellow]DUPLICATE[/bold yellow]")
                parts.append("Also in:")
                for _, source in duplicates:
                    parts.append(f"  - {source}")

        sidebar.update("\n\n".join(parts))

    def _update_llm_panel(self, review: PassReview | None = None) -> None:
        status = self.query_one("#llm-status", Static)
        metadata = self.query_one("#llm-metadata", Static)
        decision = self.query_one("#llm-decision", Static)
        reasoning = self.query_one("#llm-reasoning", Static)
        codes = self.query_one("#llm-codes", Static)

        if self.llm_loading:
            status.update("[bold]LLM Assistant[/bold] [yellow](loading...)[/yellow]")
            metadata.update("")
            decision.update("")
            reasoning.update("")
            codes.update("")
            return

        # Check for existing suggestion from review or current session
        suggestion = self.current_llm_suggestion
        if not suggestion and review and review.llm_suggestion:
            suggestion = review.llm_suggestion

        if suggestion:
            if suggestion.error:
                status.update(f"[bold]LLM Assistant[/bold] [red](error)[/red]")
                metadata.update(self._format_llm_metadata(suggestion))
                reasoning.update(f"[red]{suggestion.error}[/red]")
                decision.update("")
                codes.update("")
            else:
                decision_class = f"llm-{suggestion.decision}"
                status.update(
                    f"[bold]LLM Assistant[/bold] (confidence: {suggestion.confidence:.0%})"
                )
                metadata.update(self._format_llm_metadata(suggestion))
                decision.update(
                    f"[{decision_class}]Suggestion: {suggestion.decision.upper()}[/{decision_class}]"
                )
                reasoning.update(f"[dim]Reasoning:[/dim]\n{suggestion.reasoning}")
                if suggestion.exclusion_codes:
                    codes.update(
                        f"[dim]Codes:[/dim] {', '.join(suggestion.exclusion_codes)}"
                    )
                else:
                    codes.update("")
        else:
            status.update("[bold]LLM Assistant[/bold]")
            metadata.update("")
            decision.update("[dim]Press 'l' to request suggestion[/dim]")
            reasoning.update("")
            codes.update("")

    def _format_llm_metadata(self, suggestion: LLMSuggestion) -> str:
        """Format LLM run metadata for display."""
        parts = []
        if suggestion.domain:
            domain_color = "green" if suggestion.domain == "health" else "blue"
            parts.append(f"[{domain_color}]Domain: {suggestion.domain}[/{domain_color}]")
        if suggestion.model:
            parts.append(f"[dim]Model:[/dim] {suggestion.model}")
        if suggestion.thinking_mode is not None:
            thinking_str = "on" if suggestion.thinking_mode else "off"
            parts.append(f"[dim]Thinking:[/dim] {thinking_str}")
        if suggestion.response_time_ms is not None:
            time_sec = suggestion.response_time_ms / 1000
            parts.append(f"[dim]Time:[/dim] {time_sec:.1f}s")
        if suggestion.requested_at:
            # Parse ISO format and display nicely
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(suggestion.requested_at)
                parts.append(f"[dim]At:[/dim] {dt.strftime('%Y-%m-%d %H:%M')}")
            except (ValueError, TypeError):
                parts.append(f"[dim]At:[/dim] {suggestion.requested_at}")
        return " | ".join(parts) if parts else ""

    def _save_current(self) -> None:
        """Save current document's review data."""
        doc = self._get_current_doc()
        if not doc:
            return

        review = self._get_cached_review(doc.id)
        notes = self.query_one("#notes-area", TextArea).text or None

        if review:
            save_pass_review(
                doc.id,
                self.pass_number,
                review.decision,
                notes,
                self.current_llm_suggestion or review.llm_suggestion,
                review.llm_accepted,
            )

    def _make_decision(self, decision: str, code_ids: list[int] | None = None) -> None:
        """Make a review decision."""
        doc = self._get_current_doc()
        if not doc:
            return

        notes = self.query_one("#notes-area", TextArea).text or None
        review = self._get_cached_review(doc.id)

        # Determine if LLM suggestion was accepted
        llm_accepted = None
        if self.current_llm_suggestion or (review and review.llm_suggestion):
            suggestion = self.current_llm_suggestion or review.llm_suggestion
            llm_accepted = suggestion.decision == decision

        pass_review_id = save_pass_review(
            doc.id,
            self.pass_number,
            decision,
            notes,
            self.current_llm_suggestion or (review.llm_suggestion if review else None),
            llm_accepted,
        )

        if code_ids:
            set_pass_review_exclusion_codes(pass_review_id, code_ids)

        # Invalidate cache for this document since we just saved
        self._invalidate_cache(doc.id)

        # Clear current LLM suggestion and advance
        self.current_llm_suggestion = None
        self._advance_to_next_unreviewed()

    def _advance_to_next_unreviewed(self) -> None:
        """Advance to next unreviewed paper."""
        start = self.current_index
        for i in range(start + 1, len(self.documents)):
            review = self._get_cached_review(self.documents[i].id)
            if not review or review.decision is None:
                self.current_index = i
                self._update_display()
                # Auto-suggest if enabled
                if get_setting("llm_auto_suggest", "false") == "true":
                    self._request_llm_suggestion()
                return
        # Wrap around
        for i in range(0, start):
            review = self._get_cached_review(self.documents[i].id)
            if not review or review.decision is None:
                self.current_index = i
                self._update_display()
                if get_setting("llm_auto_suggest", "false") == "true":
                    self._request_llm_suggestion()
                return
        # All reviewed - stay on current
        self._update_display()

    def action_next_paper(self) -> None:
        self._save_current()
        if self.current_index < len(self.documents) - 1:
            self.current_index += 1
            self.current_llm_suggestion = None
            self._update_display()
            if get_setting("llm_auto_suggest", "false") == "true":
                self._request_llm_suggestion()

    def action_prev_paper(self) -> None:
        self._save_current()
        if self.current_index > 0:
            self.current_index -= 1
            self.current_llm_suggestion = None
            self._update_display()
            if get_setting("llm_auto_suggest", "false") == "true":
                self._request_llm_suggestion()

    def action_include(self) -> None:
        self._make_decision("include")

    def action_exclude(self) -> None:
        doc = self._get_current_doc()
        if not doc:
            return

        review = self._get_cached_review(doc.id)
        current_codes = review.exclusion_codes if review else []

        def handle_codes(code_ids: list[int] | None) -> None:
            if code_ids is not None and len(code_ids) > 0:
                self._make_decision("exclude", code_ids)

        self.app.push_screen(ExclusionCodeModal(current_codes), handle_codes)

    def action_uncertain(self) -> None:
        self._make_decision("uncertain")

    def action_request_llm(self) -> None:
        self._request_llm_suggestion()

    @work(exclusive=True, group="llm")
    async def _request_llm_suggestion(self) -> None:
        doc = self._get_current_doc()
        if not doc:
            return

        self.llm_loading = True
        self._update_llm_panel()

        settings = get_all_settings()
        host = settings.get("llm_host", "http://localhost:11434")
        model = settings.get("llm_model", "qwen3:8b")
        thinking = settings.get("llm_thinking_mode", "true") == "true"

        assistant = LLMAssistant(host=host, model=model)
        venue = doc.journal or doc.booktitle

        if self.pass_number == 1:
            suggestion = await assistant.suggest_pass1(
                document_id=doc.id,
                title=doc.title or "",
                year=doc.year,
                keywords=doc.keywords,
                venue=venue,
                thinking_mode=thinking,
            )
        else:
            suggestion = await assistant.suggest_pass2(
                document_id=doc.id,
                title=doc.title or "",
                year=doc.year,
                keywords=doc.keywords,
                venue=venue,
                abstract=doc.abstract,
                thinking_mode=thinking,
            )

        self.current_llm_suggestion = suggestion
        self.llm_loading = False
        self._update_llm_panel()

    def action_accept_llm(self) -> None:
        """Accept the LLM suggestion."""
        doc = self._get_current_doc()
        if not doc:
            return

        review = self._get_cached_review(doc.id)
        suggestion = self.current_llm_suggestion or (
            review.llm_suggestion if review else None
        )

        if not suggestion or suggestion.error:
            return

        if suggestion.decision == "exclude":
            # Need to get code IDs for the suggested exclusion codes
            all_codes = get_exclusion_codes_with_descriptions()
            code_ids = [
                cid for cid, code, _ in all_codes if code in suggestion.exclusion_codes
            ]
            self._make_decision("exclude", code_ids if code_ids else None)
        else:
            self._make_decision(suggestion.decision)

    def action_reject_llm(self) -> None:
        """Reject LLM suggestion - clear it from display."""
        self.current_llm_suggestion = None
        self._update_llm_panel()

    def action_edit_tags(self) -> None:
        """Open tag editing modal."""
        doc = self._get_current_doc()
        if not doc:
            return

        current_tags = get_document_tags(doc.id)

        def handle_tags(tag_ids: list[int] | None) -> None:
            if tag_ids is not None:
                set_document_tags(doc.id, tag_ids)
                self._update_sidebar()

        self.app.push_screen(TagModal(doc.id, current_tags), handle_tags)

    def action_set_health(self) -> None:
        """Toggle health domain."""
        doc = self._get_current_doc()
        if not doc:
            return
        doc.domain = "health" if doc.domain != "health" else None
        if doc.review_id:
            save_review(
                doc.review_id, doc.included, doc.notes, doc.domain, doc.reference
            )
        self._update_sidebar()

    def action_set_environmental(self) -> None:
        """Toggle environmental domain."""
        doc = self._get_current_doc()
        if not doc:
            return
        doc.domain = "environmental" if doc.domain != "environmental" else None
        if doc.review_id:
            save_review(
                doc.review_id, doc.included, doc.notes, doc.domain, doc.reference
            )
        self._update_sidebar()

    def action_random_unreviewed(self) -> None:
        """Jump to a random unreviewed paper."""
        self._save_current()
        unreviewed_indices = []
        for i, doc in enumerate(self.documents):
            review = self._get_cached_review(doc.id)
            if not review or review.decision is None:
                unreviewed_indices.append(i)

        if unreviewed_indices:
            self.current_index = random.choice(unreviewed_indices)
            self.current_llm_suggestion = None
            self._update_display()
            if get_setting("llm_auto_suggest", "false") == "true":
                self._request_llm_suggestion()

    def action_go_back(self) -> None:
        self._save_current()
        self.app.pop_screen()

    @on(Button.Pressed, "#include-btn")
    def on_include_btn(self) -> None:
        self.action_include()

    @on(Button.Pressed, "#exclude-btn")
    def on_exclude_btn(self) -> None:
        self.action_exclude()

    @on(Button.Pressed, "#uncertain-btn")
    def on_uncertain_btn(self) -> None:
        self.action_uncertain()

    @on(Button.Pressed, "#llm-request-btn")
    def on_llm_request_btn(self) -> None:
        self.action_request_llm()

    @on(Button.Pressed, "#llm-accept-btn")
    def on_llm_accept_btn(self) -> None:
        self.action_accept_llm()

    @on(Button.Pressed, "#llm-reject-btn")
    def on_llm_reject_btn(self) -> None:
        self.action_reject_llm()


class ReviewScreen(Screen):
    """Main review screen."""

    BINDINGS = [
        Binding("j", "next_paper", "Next"),
        Binding("k", "prev_paper", "Previous"),
        Binding("a", "accept", "Accept"),
        Binding("x", "reject", "Reject"),
        Binding("r", "toggle_reference", "Toggle Reference"),
        Binding("h", "set_health", "Set Health"),
        Binding("e", "set_environmental", "Set Environmental"),
        Binding("n", "focus_notes", "Edit Notes"),
        Binding("q", "go_back", "Back"),
        Binding("u", "undo_decision", "Undo Decision"),
        Binding("g", "random_unreviewed", "Random"),
    ]

    CSS = """
    ReviewScreen {
        layout: horizontal;
    }

    #main-content {
        width: 2fr;
        height: 100%;
        padding: 1;
    }

    #sidebar {
        width: 1fr;
        height: 100%;
        background: $surface;
        border-left: thick $primary;
        padding: 1;
    }

    #progress-bar {
        height: 3;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #paper-display {
        height: 1fr;
        padding: 1;
    }

    #title-display {
        text-style: bold;
        margin-bottom: 1;
        height: auto;
    }

    #abstract-display {
        height: auto;
    }

    #status-row {
        height: 3;
        padding: 0 1;
    }

    #action-row {
        height: 5;
        padding: 1;
    }

    #action-row Button {
        margin: 0 1;
    }

    #notes-area {
        height: 8;
        margin-top: 1;
    }

    .sidebar-section {
        margin-bottom: 1;
    }

    .sidebar-label {
        text-style: bold;
        color: $primary;
    }

    .status-included {
        color: $success;
    }

    .status-excluded {
        color: $error;
    }

    .status-pending {
        color: $warning;
    }

    .tag-reference {
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    .tag-health {
        background: $success-darken-2;
        color: $text;
        padding: 0 1;
    }

    .tag-environmental {
        background: $warning-darken-2;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, search_id: int, start_doc_id: int | None = None) -> None:
        super().__init__()
        self.search_id = search_id
        self.start_doc_id = start_doc_id
        self.documents: list[Document] = []
        self.current_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="main-content"):
                yield Static("", id="progress-bar")
                with VerticalScroll(id="paper-display"):
                    yield Static("", id="title-display")
                    yield Static("", id="abstract-display")
                yield Static("", id="status-row")
                with Horizontal(id="action-row"):
                    yield Button("Accept [a]", variant="success", id="accept-btn")
                    yield Button("Reject [x]", variant="error", id="reject-btn")
                    yield Button("Undo [u]", variant="default", id="undo-btn")
                yield TextArea(id="notes-area")
            with VerticalScroll(id="sidebar"):
                yield Static("", id="sidebar-content")
        yield Footer()

    def on_mount(self) -> None:
        self.documents = get_documents_for_search(self.search_id)

        # If a specific document was requested, find it
        if self.start_doc_id is not None:
            for i, doc in enumerate(self.documents):
                if doc.id == self.start_doc_id:
                    self.current_index = i
                    break
        else:
            # Find first unreviewed document
            for i, doc in enumerate(self.documents):
                if doc.included is None:
                    self.current_index = i
                    break
        self._update_display()

    def _get_current_doc(self) -> Document | None:
        if 0 <= self.current_index < len(self.documents):
            return self.documents[self.current_index]
        return None

    def _update_display(self) -> None:
        doc = self._get_current_doc()
        if not doc:
            return

        # Progress bar
        total = len(self.documents)
        reviewed = sum(1 for d in self.documents if d.included is not None)
        included = sum(1 for d in self.documents if d.included is True)
        excluded = sum(1 for d in self.documents if d.included is False)
        progress = self.query_one("#progress-bar", Static)
        progress.update(
            f"Paper {self.current_index + 1}/{total} | "
            f"Reviewed: {reviewed}/{total} ({reviewed / total * 100:.0f}%) | "
            f"Included: {included} | Excluded: {excluded}"
        )

        # Title
        title_display = self.query_one("#title-display", Static)
        title_text = doc.title or "No title"
        if doc.year:
            title_text += f" ({doc.year})"
        title_display.update(title_text)

        # Abstract
        abstract_display = self.query_one("#abstract-display", Static)
        abstract_display.update(doc.abstract or "No abstract available")

        # Status row with tags
        status_row = self.query_one("#status-row", Static)
        status_parts = []

        if doc.included is None:
            status_parts.append("[yellow]PENDING[/yellow]")
        elif doc.included:
            status_parts.append("[green]INCLUDED[/green]")
        else:
            status_parts.append("[red]EXCLUDED[/red]")
            if doc.review_id:
                codes = get_review_exclusion_codes(doc.review_id)
                if codes:
                    status_parts.append(f"Codes: {', '.join(codes)}")

        if doc.reference:
            status_parts.append("[blue]REF[/blue]")
        if doc.domain:
            color = "green" if doc.domain == "health" else "yellow"
            status_parts.append(f"[{color}]{doc.domain.upper()}[/{color}]")

        status_row.update(" | ".join(status_parts))

        # Notes
        notes_area = self.query_one("#notes-area", TextArea)
        notes_area.text = doc.notes or ""

        # Sidebar
        self._update_sidebar()

    def _update_sidebar(self) -> None:
        doc = self._get_current_doc()
        if not doc:
            return

        sidebar = self.query_one("#sidebar-content", Static)
        parts = []

        parts.append("[bold]Details[/bold]")
        parts.append(f"[dim]Type:[/dim] {doc.entry_type}")

        if doc.author:
            # Truncate long author lists
            authors = doc.author
            if len(authors) > 100:
                authors = authors[:100] + "..."
            parts.append(f"[dim]Authors:[/dim]\n{authors}")

        if doc.journal:
            parts.append(f"[dim]Journal:[/dim] {doc.journal}")
        if doc.booktitle:
            parts.append(f"[dim]Venue:[/dim] {doc.booktitle}")
        if doc.year:
            parts.append(f"[dim]Year:[/dim] {doc.year}")
        if doc.doi:
            parts.append(f"[dim]DOI:[/dim] {doc.doi}")
        if doc.keywords:
            parts.append(f"[dim]Keywords:[/dim]\n{doc.keywords}")

        parts.append("")
        parts.append("[bold]Bibtex Key[/bold]")
        parts.append(doc.bibtex_key)

        # Show duplicate info
        if doc.duplicate_group_id:
            duplicates = get_duplicate_searches(doc.id, doc.duplicate_group_id)
            if duplicates:
                parts.append("")
                parts.append("[bold yellow]DUPLICATE[/bold yellow]")
                parts.append("Also in:")
                for _, source in duplicates:
                    parts.append(f"  - {source}")

        sidebar.update("\n\n".join(parts))

    def _save_current(self) -> None:
        """Save current document's review data."""
        doc = self._get_current_doc()
        if doc and doc.review_id:
            notes = self.query_one("#notes-area", TextArea).text
            save_review(
                doc.review_id, doc.included, notes or None, doc.domain, doc.reference
            )
            doc.notes = notes or None

    def action_next_paper(self) -> None:
        self._save_current()
        if self.current_index < len(self.documents) - 1:
            self.current_index += 1
            self._update_display()

    def action_prev_paper(self) -> None:
        self._save_current()
        if self.current_index > 0:
            self.current_index -= 1
            self._update_display()

    def action_accept(self) -> None:
        doc = self._get_current_doc()
        if doc:
            doc.included = True
            self._save_current()
            self._update_display()
            # Auto-advance to next unreviewed
            self._advance_to_next_unreviewed()

    def _advance_to_next_unreviewed(self) -> None:
        """Advance to next unreviewed paper."""
        start = self.current_index
        for i in range(start + 1, len(self.documents)):
            if self.documents[i].included is None:
                self.current_index = i
                self._update_display()
                return
        # Wrap around
        for i in range(0, start):
            if self.documents[i].included is None:
                self.current_index = i
                self._update_display()
                return

    def action_reject(self) -> None:
        doc = self._get_current_doc()
        if doc and doc.review_id:
            current_codes = get_review_exclusion_codes(doc.review_id)

            def handle_codes(code_ids: list[int] | None) -> None:
                if code_ids is not None and len(code_ids) > 0:
                    doc.included = False
                    set_review_exclusion_codes(doc.review_id, code_ids)
                    self._save_current()
                    self._update_display()
                    self._advance_to_next_unreviewed()

            self.app.push_screen(ExclusionCodeModal(current_codes), handle_codes)

    def action_toggle_reference(self) -> None:
        doc = self._get_current_doc()
        if doc:
            doc.reference = not doc.reference if doc.reference else True
            self._save_current()
            self._update_display()

    def action_set_health(self) -> None:
        doc = self._get_current_doc()
        if doc:
            doc.domain = "health" if doc.domain != "health" else None
            self._save_current()
            self._update_display()

    def action_set_environmental(self) -> None:
        doc = self._get_current_doc()
        if doc:
            doc.domain = "environmental" if doc.domain != "environmental" else None
            self._save_current()
            self._update_display()

    def action_focus_notes(self) -> None:
        self.query_one("#notes-area", TextArea).focus()

    def action_go_back(self) -> None:
        self._save_current()
        self.app.pop_screen()

    def action_undo_decision(self) -> None:
        doc = self._get_current_doc()
        if doc and doc.review_id:
            doc.included = None
            set_review_exclusion_codes(doc.review_id, [])
            self._save_current()
            self._update_display()

    def action_random_unreviewed(self) -> None:
        """Jump to a random unreviewed paper."""
        self._save_current()
        unreviewed_indices = [
            i for i, doc in enumerate(self.documents) if doc.included is None
        ]
        if unreviewed_indices:
            self.current_index = random.choice(unreviewed_indices)
            self._update_display()

    @on(Button.Pressed, "#accept-btn")
    def on_accept_btn(self) -> None:
        self.action_accept()

    @on(Button.Pressed, "#reject-btn")
    def on_reject_btn(self) -> None:
        self.action_reject()

    @on(Button.Pressed, "#undo-btn")
    def on_undo_btn(self) -> None:
        self.action_undo_decision()


class LitReviewApp(App):
    """Literature Review Application."""

    TITLE = "Literature Review"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())


def main() -> None:
    app = LitReviewApp()
    app.run()


if __name__ == "__main__":
    main()
