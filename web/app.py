"""Flask web application for literature review."""

import argparse
import os
import random
from functools import wraps

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import db

app = Flask(__name__)
app.secret_key = os.urandom(32)

# Passcode from environment or set at runtime
PASSCODE: str | None = os.environ.get("LIT_REVIEW_PASSCODE")


def set_passcode(code: str) -> None:
    """Set the passcode at runtime."""
    global PASSCODE
    PASSCODE = code


def require_auth(f):
    """Decorator to require authentication."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


# --- Auth Routes ---


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page with numeric keypad."""
    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        passcode = data.get("passcode", "")
        if PASSCODE and passcode == PASSCODE:
            session["authenticated"] = True
            session.permanent = True
            return jsonify({"success": True}) if request.is_json else redirect(url_for("index"))
        return jsonify({"success": False, "error": "Invalid passcode"}) if request.is_json else render_template(
            "login.html", error="Invalid passcode"
        )
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for("login"))


# --- Page Routes ---


@app.route("/")
@require_auth
def index():
    """Main menu with search selection."""
    searches = db.get_searches()
    return render_template("index.html", searches=searches)


@app.route("/review/<int:search_id>")
@require_auth
def review(search_id: int):
    """Review screen for a search."""
    pass_number = request.args.get("pass", 1, type=int)
    doc_id = request.args.get("doc", None, type=int)

    documents = db.get_documents_for_pass(search_id, pass_number)
    if not documents:
        return redirect(url_for("index"))

    # Get all pass reviews for this search to track progress
    all_reviews = db.get_all_pass_reviews()

    # Find first unreviewed or use specified doc
    current_doc = None
    current_index = 0

    if doc_id:
        for i, doc in enumerate(documents):
            if doc.id == doc_id:
                current_doc = doc
                current_index = i
                break

    if not current_doc:
        # Find first unreviewed
        for i, doc in enumerate(documents):
            if (doc.id, pass_number) not in all_reviews:
                current_doc = doc
                current_index = i
                break
        if not current_doc:
            current_doc = documents[0]
            current_index = 0

    # Get pass review for current document
    pass_review = db.get_pass_review(current_doc.id, pass_number)

    # Get progress
    progress = db.get_pass_progress(search_id)
    reviewed_count = progress["pass1"]["human_reviewed"] if pass_number == 1 else progress["pass2"]["human_reviewed"]
    total_count = progress["total"] if pass_number == 1 else progress["pass2"]["eligible"]

    # Get exclusion codes
    exclusion_codes = db.get_exclusion_codes()

    # Get document tags
    tags = db.get_document_tags(current_doc.id)

    # Get duplicates if any
    duplicates = []
    if current_doc.duplicate_group_id:
        duplicates = db.get_duplicate_searches(current_doc.id, current_doc.duplicate_group_id)

    # Get search info
    searches = db.get_searches()
    search_info = next((s for s in searches if s["id"] == search_id), None)

    return render_template(
        "review.html",
        document=current_doc,
        pass_number=pass_number,
        pass_review=pass_review,
        current_index=current_index,
        total_documents=len(documents),
        reviewed_count=reviewed_count,
        total_count=total_count,
        exclusion_codes=exclusion_codes,
        tags=tags,
        duplicates=duplicates,
        search_info=search_info,
        search_id=search_id,
    )


@app.route("/browse")
@require_auth
def browse():
    """Browse all papers with filters."""
    searches = db.get_searches()
    exclusion_codes = db.get_exclusion_codes()
    all_tags = db.get_all_tags()
    venues = db.get_all_venues()
    return render_template(
        "browse.html",
        searches=searches,
        exclusion_codes=exclusion_codes,
        all_tags=all_tags,
        venues=venues,
    )


# --- API Routes ---


@app.route("/api/searches")
@require_auth
def api_searches():
    """Get all searches with progress."""
    return jsonify(db.get_searches())


@app.route("/api/documents/<int:doc_id>")
@require_auth
def api_document(doc_id: int):
    """Get a single document with reviews."""
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404

    pass1 = db.get_pass_review(doc_id, 1)
    pass2 = db.get_pass_review(doc_id, 2)
    tags = db.get_document_tags(doc_id)
    duplicates = []
    if doc.duplicate_group_id:
        duplicates = db.get_duplicate_searches(doc_id, doc.duplicate_group_id)

    return jsonify({
        "id": doc.id,
        "bibtex_key": doc.bibtex_key,
        "entry_type": doc.entry_type,
        "title": doc.title,
        "doi": doc.doi,
        "url": doc.url,
        "search_id": doc.search_id,
        "search_source": doc.search_source,
        "author": doc.author,
        "year": doc.year,
        "abstract": doc.abstract,
        "keywords": doc.keywords,
        "journal": doc.journal,
        "booktitle": doc.booktitle,
        "tags": tags,
        "duplicates": duplicates,
        "pass1": {
            "decision": pass1.decision if pass1 else None,
            "notes": pass1.notes if pass1 else None,
            "exclusion_codes": pass1.exclusion_codes if pass1 else [],
            "llm_suggestion": {
                "decision": pass1.llm_suggestion.decision,
                "reasoning": pass1.llm_suggestion.reasoning,
                "confidence": pass1.llm_suggestion.confidence,
                "exclusion_codes": pass1.llm_suggestion.exclusion_codes,
                "domain": pass1.llm_suggestion.domain,
                "model": pass1.llm_suggestion.model,
            } if pass1 and pass1.llm_suggestion else None,
            "llm_accepted": pass1.llm_accepted if pass1 else None,
        } if pass1 else None,
        "pass2": {
            "decision": pass2.decision if pass2 else None,
            "notes": pass2.notes if pass2 else None,
            "exclusion_codes": pass2.exclusion_codes if pass2 else [],
            "llm_suggestion": {
                "decision": pass2.llm_suggestion.decision,
                "reasoning": pass2.llm_suggestion.reasoning,
                "confidence": pass2.llm_suggestion.confidence,
                "exclusion_codes": pass2.llm_suggestion.exclusion_codes,
                "domain": pass2.llm_suggestion.domain,
                "model": pass2.llm_suggestion.model,
            } if pass2 and pass2.llm_suggestion else None,
            "llm_accepted": pass2.llm_accepted if pass2 else None,
        } if pass2 else None,
    })


@app.route("/api/documents/random")
@require_auth
def api_random_document():
    """Get a random unreviewed document."""
    search_id = request.args.get("search_id", type=int)
    pass_number = request.args.get("pass", 1, type=int)

    if not search_id:
        return jsonify({"error": "search_id required"}), 400

    documents = db.get_documents_for_pass(search_id, pass_number)
    all_reviews = db.get_all_pass_reviews()

    unreviewed = [d for d in documents if (d.id, pass_number) not in all_reviews]

    if unreviewed:
        doc = random.choice(unreviewed)
        return jsonify({"document_id": doc.id})
    return jsonify({"document_id": None, "message": "All papers reviewed"})


@app.route("/api/documents/<int:doc_id>/review", methods=["POST"])
@require_auth
def api_save_review(doc_id: int):
    """Save a review decision."""
    data = request.get_json()
    pass_number = data.get("pass_number", 1)
    decision = data.get("decision")
    notes = data.get("notes")
    exclusion_codes = data.get("exclusion_codes")

    if decision not in ("include", "exclude", "uncertain", None):
        return jsonify({"error": "Invalid decision"}), 400

    pass_review_id = db.save_pass_review(
        document_id=doc_id,
        pass_number=pass_number,
        decision=decision,
        notes=notes,
        exclusion_codes=exclusion_codes,
    )

    return jsonify({"success": True, "pass_review_id": pass_review_id})


@app.route("/api/documents/<int:doc_id>/llm-accept", methods=["POST"])
@require_auth
def api_llm_accept(doc_id: int):
    """Accept or reject LLM suggestion."""
    data = request.get_json()
    pass_number = data.get("pass_number", 1)
    accepted = data.get("accepted", False)

    db.update_llm_accepted(doc_id, pass_number, accepted)
    return jsonify({"success": True})


@app.route("/api/documents/<int:doc_id>/tags", methods=["POST"])
@require_auth
def api_set_tags(doc_id: int):
    """Set tags for a document."""
    data = request.get_json()
    tag_names = data.get("tags", [])
    db.set_document_tags(doc_id, tag_names)
    return jsonify({"success": True})


@app.route("/api/exclusion-codes")
@require_auth
def api_exclusion_codes():
    """Get all exclusion codes."""
    return jsonify(db.get_exclusion_codes())


@app.route("/api/tags")
@require_auth
def api_tags():
    """Get all tags."""
    return jsonify(db.get_all_tags())


@app.route("/api/browse")
@require_auth
def api_browse():
    """Get documents for browse view with filters."""
    documents = db.get_all_documents_for_browse()
    all_reviews = db.get_all_pass_reviews(human_only=False)
    all_tags = db.get_all_document_tags()

    # Add review info to documents
    for doc in documents:
        p1 = all_reviews.get((doc["id"], 1))
        p2 = all_reviews.get((doc["id"], 2))
        doc["pass1"] = p1["decision"] if p1 else None
        doc["pass1_codes"] = p1["exclusion_codes"] if p1 else []
        doc["pass2"] = p2["decision"] if p2 else None
        doc["pass2_codes"] = p2["exclusion_codes"] if p2 else []
        doc["tags"] = all_tags.get(doc["id"], [])

    return jsonify(documents)


@app.route("/api/venues")
@require_auth
def api_venues():
    """Get all venues."""
    return jsonify(db.get_all_venues())


@app.route("/api/documents/nav")
@require_auth
def api_nav():
    """Get navigation info (prev/next document IDs)."""
    search_id = request.args.get("search_id", type=int)
    pass_number = request.args.get("pass", 1, type=int)
    current_id = request.args.get("current", type=int)

    if not search_id or not current_id:
        return jsonify({"error": "search_id and current required"}), 400

    documents = db.get_documents_for_pass(search_id, pass_number)
    doc_ids = [d.id for d in documents]

    try:
        current_index = doc_ids.index(current_id)
    except ValueError:
        return jsonify({"prev": None, "next": None, "index": 0, "total": len(doc_ids)})

    prev_id = doc_ids[current_index - 1] if current_index > 0 else None
    next_id = doc_ids[current_index + 1] if current_index < len(doc_ids) - 1 else None

    return jsonify({
        "prev": prev_id,
        "next": next_id,
        "index": current_index,
        "total": len(doc_ids),
    })


def main():
    """Run the Flask development server."""
    parser = argparse.ArgumentParser(description="Literature Review Web App")
    parser.add_argument("--passcode", help="Passcode for authentication")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    if args.passcode:
        set_passcode(args.passcode)
    elif not PASSCODE:
        print("Warning: No passcode set. Use --passcode or LIT_REVIEW_PASSCODE env var.")
        print("Running without authentication for development.")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
