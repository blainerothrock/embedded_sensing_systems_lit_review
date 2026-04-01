"""Lit Review Coding — Flask web application."""

import argparse
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import db
import schema

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload

SCRIPT_NAME = os.environ.get("SCRIPT_NAME", "")
if SCRIPT_NAME:
    class PrefixMiddleware:
        def __init__(self, app, prefix):
            self.app = app
            self.prefix = prefix
        def __call__(self, environ, start_response):
            environ["SCRIPT_NAME"] = self.prefix
            return self.app(environ, start_response)
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, SCRIPT_NAME)

PDF_DIR = Path(__file__).parent / "pdfs"
PDF_DIR.mkdir(exist_ok=True)


# --- Startup ---

def init_db():
    with db.connect() as conn:
        schema.migrate(conn)


# --- Page ---

@app.route("/")
def index():
    return render_template("index.html")


# --- API: Papers ---

@app.route("/api/papers")
def api_papers():
    search = request.args.get("search", "")
    status = request.args.get("status", "all")
    with db.connect() as conn:
        papers = db.get_phase3_papers(conn, search=search, status=status)
    return jsonify(papers)


@app.route("/api/papers/<int:doc_id>")
def api_paper(doc_id):
    with db.connect() as conn:
        paper = db.get_paper(conn, doc_id)
    if paper is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(paper)


@app.route("/api/exclusion-codes")
def api_exclusion_codes():
    with db.connect() as conn:
        codes = db.get_exclusion_codes(conn)
    return jsonify(codes)


# --- API: PDF management ---

@app.route("/api/papers/<int:doc_id>/upload-pdf", methods=["POST"])
def api_upload_pdf(doc_id):
    if "pdf" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["pdf"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF"}), 400

    pdf_filename = f"{doc_id}.pdf"
    pdf_path = PDF_DIR / pdf_filename
    file.save(pdf_path)

    with db.connect() as conn:
        db.save_pdf_reference(conn, doc_id, pdf_filename)

    return jsonify({"success": True, "pdf_path": pdf_filename})


@app.route("/api/papers/<int:doc_id>/pdf")
def api_serve_pdf(doc_id):
    with db.connect() as conn:
        pdf_path = db.get_pdf_path(conn, doc_id)
    if pdf_path is None:
        return jsonify({"error": "No PDF"}), 404
    full_path = PDF_DIR / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF file missing"}), 404
    return send_file(full_path, mimetype="application/pdf")


# --- API: Phase 3 Review ---

@app.route("/api/papers/<int:doc_id>/review", methods=["POST"])
def api_save_review(doc_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    decision = data.get("decision")
    notes = data.get("notes", "")
    exclusion_code_ids = data.get("exclusion_code_ids", [])

    if decision not in ("include", "exclude", "uncertain"):
        return jsonify({"error": "Invalid decision"}), 400

    with db.connect() as conn:
        db.save_phase3_review(conn, doc_id, decision, notes, exclusion_code_ids)
    return jsonify({"success": True})


# --- API: Codes (hierarchical) ---

@app.route("/api/codes")
def api_codes():
    with db.connect() as conn:
        codes = db.get_codes(conn)
    return jsonify(codes)


@app.route("/api/codes", methods=["POST"])
def api_create_code():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "name required"}), 400
    with db.connect() as conn:
        try:
            code = db.create_code(
                conn, data["name"], data.get("parent_id"),
                data.get("description", ""), data.get("color", "#FFEB3B"),
                data.get("sort_order", 0),
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    return jsonify(code), 201


@app.route("/api/codes/<int:code_id>", methods=["PUT"])
def api_update_code(code_id):
    data = request.get_json()
    with db.connect() as conn:
        code = db.update_code(conn, code_id, **data)
    if code is None:
        return jsonify({"error": "Not found or no changes"}), 404
    return jsonify(code)


@app.route("/api/codes/<int:code_id>", methods=["DELETE"])
def api_delete_code(code_id):
    with db.connect() as conn:
        ok = db.delete_code(conn, code_id)
    if not ok:
        return jsonify({"error": "Code has annotations or sub-codes"}), 400
    return jsonify({"success": True})


# --- API: Annotations ---

@app.route("/api/papers/<int:doc_id>/annotations")
def api_annotations(doc_id):
    with db.connect() as conn:
        annotations = db.get_annotations(conn, doc_id)
    return jsonify(annotations)


@app.route("/api/papers/<int:doc_id>/annotations", methods=["POST"])
def api_create_annotation(doc_id):
    data = request.get_json()
    if not data or not data.get("rects_json"):
        return jsonify({"error": "rects_json required"}), 400
    with db.connect() as conn:
        ann = db.create_annotation(
            conn, doc_id, data.get("annotation_type", "highlight"),
            data.get("page_number", 1), data["rects_json"],
            data.get("selected_text"), data.get("note"), data.get("color"),
            data.get("code_ids"),
        )
    return jsonify(ann), 201


@app.route("/api/annotations/<int:ann_id>", methods=["PUT"])
def api_update_annotation(ann_id):
    data = request.get_json()
    with db.connect() as conn:
        ann = db.update_annotation(conn, ann_id, **data)
    if ann is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(ann)


@app.route("/api/annotations/<int:ann_id>", methods=["DELETE"])
def api_delete_annotation(ann_id):
    with db.connect() as conn:
        ok = db.delete_annotation(conn, ann_id)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/annotations/<int:ann_id>/codes/<int:code_id>", methods=["POST"])
def api_add_annotation_code(ann_id, code_id):
    data = request.get_json(silent=True) or {}
    with db.connect() as conn:
        db.add_annotation_code(conn, ann_id, code_id, data.get("note"))
    return jsonify({"success": True})


@app.route("/api/annotations/<int:ann_id>/codes/<int:code_id>/note", methods=["PUT"])
def api_update_annotation_code_note(ann_id, code_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    with db.connect() as conn:
        db.update_annotation_code_note(conn, ann_id, code_id, data.get("note", ""))
    return jsonify({"success": True})


@app.route("/api/annotations/<int:ann_id>/codes/<int:code_id>", methods=["DELETE"])
def api_remove_annotation_code(ann_id, code_id):
    with db.connect() as conn:
        db.remove_annotation_code(conn, ann_id, code_id)
    return jsonify({"success": True})


@app.route("/api/codes/usage")
def api_code_usage_counts():
    with db.connect() as conn:
        counts = db.get_code_usage_counts(conn)
    return jsonify(counts)


# --- API: Matrix Columns ---

@app.route("/api/matrix-columns")
def api_matrix_columns():
    with db.connect() as conn:
        columns = db.get_matrix_columns(conn)
    return jsonify(columns)


@app.route("/api/matrix-columns", methods=["POST"])
def api_create_matrix_column():
    data = request.get_json()
    if not data or not data.get("name") or not data.get("column_type"):
        return jsonify({"error": "name and column_type required"}), 400
    with db.connect() as conn:
        col = db.create_matrix_column(
            conn, data["name"], data["column_type"],
            data.get("description", ""), data.get("color", "#FFEB3B"),
            data.get("sort_order", 0),
        )
    return jsonify(col), 201


@app.route("/api/matrix-columns/<int:col_id>", methods=["PUT"])
def api_update_matrix_column(col_id):
    data = request.get_json()
    with db.connect() as conn:
        col = db.update_matrix_column(conn, col_id, **data)
    if col is None:
        return jsonify({"error": "Not found or no changes"}), 404
    return jsonify(col)


@app.route("/api/matrix-columns/<int:col_id>", methods=["DELETE"])
def api_delete_matrix_column(col_id):
    with db.connect() as conn:
        ok = db.delete_matrix_column(conn, col_id)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/matrix-columns/<int:col_id>/options", methods=["POST"])
def api_create_column_option(col_id):
    data = request.get_json()
    if not data or not data.get("value"):
        return jsonify({"error": "value required"}), 400
    with db.connect() as conn:
        opt = db.create_column_option(conn, col_id, data["value"], data.get("sort_order", 0))
    return jsonify(opt), 201


@app.route("/api/matrix-column-options/<int:opt_id>", methods=["DELETE"])
def api_delete_column_option(opt_id):
    with db.connect() as conn:
        ok = db.delete_column_option(conn, opt_id)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/matrix-columns/<int:col_id>/codes/<int:code_id>", methods=["POST"])
def api_link_column_code(col_id, code_id):
    with db.connect() as conn:
        db.link_column_code(conn, col_id, code_id)
    return jsonify({"success": True})


@app.route("/api/matrix-columns/<int:col_id>/codes/<int:code_id>", methods=["DELETE"])
def api_unlink_column_code(col_id, code_id):
    with db.connect() as conn:
        db.unlink_column_code(conn, col_id, code_id)
    return jsonify({"success": True})


# --- API: Matrix Data ---

@app.route("/api/matrix")
def api_matrix():
    with db.connect() as conn:
        matrix = db.get_matrix(conn)
    return jsonify(matrix)


@app.route("/api/papers/<int:doc_id>/matrix-cells")
def api_paper_matrix_cells(doc_id):
    with db.connect() as conn:
        cells = db.get_paper_matrix_cells(conn, doc_id)
    return jsonify(cells)


@app.route("/api/matrix/cell", methods=["POST"])
def api_save_matrix_cell():
    data = request.get_json()
    if not data or not data.get("document_id") or not data.get("column_id"):
        return jsonify({"error": "document_id and column_id required"}), 400
    with db.connect() as conn:
        cell = db.save_matrix_cell(
            conn, data["document_id"], data["column_id"],
            data.get("value"), data.get("notes"),
        )
    return jsonify(cell)


# --- API: Coding Completeness ---

@app.route("/api/coding/completeness")
def api_coding_completeness():
    with db.connect() as conn:
        completeness = db.get_coding_completeness(conn)
    return jsonify(completeness)


# --- API: Themes & Summary ---

@app.route("/api/themes/<int:code_id>")
def api_themes(code_id):
    with db.connect() as conn:
        annotations = db.get_annotations_by_code(conn, code_id)
    return jsonify(annotations)


@app.route("/api/papers/<int:doc_id>/summary")
def api_paper_summary(doc_id):
    with db.connect() as conn:
        summary = db.get_paper_annotation_summary(conn, doc_id)
    return jsonify(summary)


# --- API: Stats ---

@app.route("/api/stats")
def api_stats():
    with db.connect() as conn:
        stats = db.get_stats(conn)
    return jsonify(stats)


# --- Main ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--desktop", action="store_true", help="Launch as desktop app (pywebview)")
    args = parser.parse_args()

    init_db()

    if args.desktop:
        import threading
        import webview

        server = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=args.port, debug=False),
            daemon=True,
        )
        server.start()
        webview.create_window(
            "Lit Review Coding",
            f"http://127.0.0.1:{args.port}",
            width=1400,
            height=900,
        )
        webview.start()
    else:
        app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
