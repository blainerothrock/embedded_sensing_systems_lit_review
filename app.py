"""Literature Review TUI Application."""

import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from textual import on
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
    OptionList,
    Select,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option
from rich.text import Text

from db_schema import DB_PATH


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
    results = [(row["id"], row["source"], row["total"], row["reviewed"]) for row in cursor.fetchall()]
    conn.close()
    return results


def get_documents_for_search(search_id: int) -> list[Document]:
    """Get all documents for a search."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            d.id, d.bibtex_key, d.entry_type, d.title, d.doi, d.url, d.search_id,
            r.id as review_id, r.included, r.notes, r.domain, r.reference,
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
    """, (search_id,))

    documents = []
    for row in cursor.fetchall():
        documents.append(Document(
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
            included=row["included"] if row["included"] is None else bool(row["included"]),
            notes=row["notes"],
            domain=row["domain"],
            reference=row["reference"] if row["reference"] is None else bool(row["reference"]),
        ))
    conn.close()
    return documents


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
    cursor.execute("""
        SELECT ec.code
        FROM review_exclusion_code rec
        JOIN exclusion_code ec ON ec.id = rec.exclusion_code_id
        WHERE rec.review_id = ?
    """, (review_id,))
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
    cursor.execute("""
        UPDATE review
        SET included = ?, notes = ?, domain = ?, reference = ?
        WHERE id = ?
    """, (
        None if included is None else int(included),
        notes,
        domain,
        None if reference is None else int(reference),
        review_id
    ))
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
    cursor.execute("DELETE FROM review_exclusion_code WHERE review_id = ?", (review_id,))
    for code_id in code_ids:
        cursor.execute(
            "INSERT INTO review_exclusion_code (review_id, exclusion_code_id) VALUES (?, ?)",
            (review_id, code_id)
        )
    conn.commit()
    conn.close()


class ExclusionCodeModal(ModalScreen[list[int] | None]):
    """Modal for selecting exclusion codes with fuzzy search."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    CSS = """
    ExclusionCodeModal {
        align: center middle;
    }

    #modal-container {
        width: 60;
        height: auto;
        max-height: 80%;
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
        max-height: 15;
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
        self.all_codes: list[tuple[int, str]] = []

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
        self.all_codes = get_exclusion_codes()
        # Pre-select current codes
        for code_id, code in self.all_codes:
            if code in self.current_codes:
                self.selected_code_ids.append(code_id)
        self._refresh_code_list()
        self._update_selected_display()
        self.query_one("#search-input", Input).focus()

    def _refresh_code_list(self, filter_text: str = "") -> None:
        code_list = self.query_one("#code-list", OptionList)
        code_list.clear_options()

        filter_lower = filter_text.lower()
        for code_id, code in self.all_codes:
            if filter_lower in code.lower():
                prefix = "[X] " if code_id in self.selected_code_ids else "[ ] "
                code_list.add_option(Option(prefix + code, id=str(code_id)))

        # If no match and there's text, offer to create new
        if filter_text and not any(filter_lower == code.lower() for _, code in self.all_codes):
            code_list.add_option(Option(f"[+] Create: {filter_text}", id=f"new:{filter_text}"))

    def _update_selected_display(self) -> None:
        selected_names = [code for code_id, code in self.all_codes if code_id in self.selected_code_ids]
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
            self.all_codes = get_exclusion_codes()  # Refresh
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


class MainMenuScreen(Screen):
    """Main menu for selecting mode and search."""

    CSS = """
    MainMenuScreen {
        align: center middle;
    }

    #menu-container {
        width: 70;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 2;
    }

    #search-list {
        height: auto;
        max-height: 15;
        margin-bottom: 1;
    }

    #mode-buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #mode-buttons Button {
        margin: 0 2;
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
            yield Label("Then choose a mode:")
            with Horizontal(id="mode-buttons"):
                yield Button("Review Papers", variant="primary", id="review-btn")
                yield Button("Browse All", variant="default", id="browse-btn")
        yield Footer()

    def on_mount(self) -> None:
        searches = get_searches()
        search_list = self.query_one("#search-list", OptionList)
        for search_id, source, total, reviewed in searches:
            progress = f"{reviewed}/{total}"
            pct = (reviewed / total * 100) if total > 0 else 0
            search_list.add_option(
                Option(f"{source} ({progress} - {pct:.0f}%)", id=str(search_id))
            )
        # Select first by default
        if searches:
            self.selected_search_id = searches[0][0]
            search_list.highlighted = 0

    @on(OptionList.OptionHighlighted, "#search-list")
    def on_search_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id:
            self.selected_search_id = int(event.option.id)

    @on(Button.Pressed, "#review-btn")
    def on_review_pressed(self) -> None:
        if self.selected_search_id:
            self.app.push_screen(ReviewScreen(self.selected_search_id))

    @on(Button.Pressed, "#browse-btn")
    def on_browse_pressed(self) -> None:
        if self.selected_search_id:
            self.app.push_screen(BrowseScreen(self.selected_search_id))


class BrowseScreen(Screen):
    """Screen for browsing and filtering all papers."""

    BINDINGS = [
        Binding("q", "go_back", "Back"),
        Binding("r", "reset_filters", "Reset Filters"),
    ]

    CSS = """
    BrowseScreen {
        layout: vertical;
    }

    #filter-bar {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    #filter-bar Horizontal {
        height: 100%;
        align: left middle;
    }

    #filter-bar Label {
        margin-right: 1;
        padding-top: 1;
    }

    #filter-bar Select {
        width: 20;
        margin-right: 2;
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

    def __init__(self, search_id: int) -> None:
        super().__init__()
        self.search_id = search_id
        self.documents: list[Document] = []
        self.exclusion_codes: list[tuple[int, str]] = []
        self.current_filter_status: str | None = None
        self.current_filter_code: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="filter-bar"):
            yield Label("Status:")
            yield Select(
                [
                    ("All", "all"),
                    ("Pending", "pending"),
                    ("Included", "included"),
                    ("Excluded", "excluded"),
                ],
                value="all",
                id="status-filter",
                allow_blank=False,
            )
            yield Label("Exclusion Code:")
            yield Select(
                [("All", "all")],
                value="all",
                id="code-filter",
                allow_blank=False,
            )
        yield DataTable(id="papers-table")
        yield Static("", id="stats-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.documents = get_documents_for_search(self.search_id)
        self.exclusion_codes = get_exclusion_codes()

        # Populate exclusion code filter
        code_filter = self.query_one("#code-filter", Select)
        code_options = [("All", "all")] + [(code, code) for _, code in self.exclusion_codes]
        code_filter.set_options(code_options)

        # Setup table
        table = self.query_one("#papers-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Status", "Title", "Year", "Venue", "Codes")

        self._refresh_table()

    def _get_venue(self, doc: Document) -> str:
        """Get venue (journal or booktitle)."""
        venue = doc.journal or doc.booktitle or ""
        if len(venue) > 40:
            venue = venue[:37] + "..."
        return venue

    def _get_status_text(self, doc: Document) -> Text:
        """Get styled status text."""
        if doc.included is None:
            return Text("PENDING", style="yellow")
        elif doc.included:
            return Text("INCLUDED", style="green")
        else:
            return Text("EXCLUDED", style="red")

    def _get_exclusion_codes_for_doc(self, doc: Document) -> str:
        """Get exclusion codes for a document."""
        if doc.review_id and doc.included is False:
            codes = get_review_exclusion_codes(doc.review_id)
            return ", ".join(codes) if codes else ""
        return ""

    def _filter_documents(self) -> list[Document]:
        """Filter documents based on current filters."""
        filtered = self.documents

        # Status filter
        if self.current_filter_status == "pending":
            filtered = [d for d in filtered if d.included is None]
        elif self.current_filter_status == "included":
            filtered = [d for d in filtered if d.included is True]
        elif self.current_filter_status == "excluded":
            filtered = [d for d in filtered if d.included is False]

        # Exclusion code filter
        if self.current_filter_code and self.current_filter_code != "all":
            filtered_by_code = []
            for doc in filtered:
                if doc.review_id:
                    codes = get_review_exclusion_codes(doc.review_id)
                    if self.current_filter_code in codes:
                        filtered_by_code.append(doc)
            filtered = filtered_by_code

        return filtered

    def _refresh_table(self) -> None:
        """Refresh the table with current filters."""
        table = self.query_one("#papers-table", DataTable)
        table.clear()

        filtered_docs = self._filter_documents()

        for doc in filtered_docs:
            # Wrap title
            title = doc.title or "No title"
            if len(title) > 80:
                title = title[:77] + "..."

            table.add_row(
                self._get_status_text(doc),
                title,
                doc.year or "",
                self._get_venue(doc),
                self._get_exclusion_codes_for_doc(doc),
                key=str(doc.id),
            )

        # Update stats
        total = len(self.documents)
        showing = len(filtered_docs)
        included = sum(1 for d in self.documents if d.included is True)
        excluded = sum(1 for d in self.documents if d.included is False)
        pending = sum(1 for d in self.documents if d.included is None)

        stats = self.query_one("#stats-bar", Static)
        stats.update(
            f"Showing {showing}/{total} | "
            f"Included: {included} | Excluded: {excluded} | Pending: {pending}"
        )

    @on(Select.Changed, "#status-filter")
    def on_status_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_status = None if value == "all" else value
        self._refresh_table()

    @on(Select.Changed, "#code-filter")
    def on_code_filter_changed(self, event: Select.Changed) -> None:
        value = event.value
        self.current_filter_code = None if value == "all" else value
        self._refresh_table()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_reset_filters(self) -> None:
        self.query_one("#status-filter", Select).value = "all"
        self.query_one("#code-filter", Select).value = "all"
        self.current_filter_status = None
        self.current_filter_code = None
        self._refresh_table()

    @on(DataTable.RowSelected, "#papers-table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open the selected paper in the review screen."""
        if event.row_key and event.row_key.value:
            doc_id = int(event.row_key.value)
            self.app.push_screen(ReviewScreen(self.search_id, start_doc_id=doc_id))


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
            f"Reviewed: {reviewed}/{total} ({reviewed/total*100:.0f}%) | "
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

        sidebar.update("\n\n".join(parts))

    def _save_current(self) -> None:
        """Save current document's review data."""
        doc = self._get_current_doc()
        if doc and doc.review_id:
            notes = self.query_one("#notes-area", TextArea).text
            save_review(doc.review_id, doc.included, notes or None, doc.domain, doc.reference)
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
            i for i, doc in enumerate(self.documents)
            if doc.included is None
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
