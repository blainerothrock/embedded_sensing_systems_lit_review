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
    conn = db.get_connection()
    schema.migrate(conn)
    conn.close()


# --- Page ---

@app.route("/")
def index():
    return render_template("index.html")


# --- API: Papers ---

@app.route("/api/papers")
def api_papers():
    search = request.args.get("search", "")
    status = request.args.get("status", "all")
    conn = db.get_connection()
    papers = db.get_phase3_papers(conn, search=search, status=status)
    conn.close()
    return jsonify(papers)


@app.route("/api/papers/<int:doc_id>")
def api_paper(doc_id):
    conn = db.get_connection()
    paper = db.get_paper(conn, doc_id)
    conn.close()
    if paper is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(paper)


@app.route("/api/exclusion-codes")
def api_exclusion_codes():
    conn = db.get_connection()
    codes = db.get_exclusion_codes(conn)
    conn.close()
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

    conn = db.get_connection()
    db.save_pdf_reference(conn, doc_id, pdf_filename)
    conn.close()

    return jsonify({"success": True, "pdf_path": pdf_filename})


@app.route("/api/papers/<int:doc_id>/pdf")
def api_serve_pdf(doc_id):
    conn = db.get_connection()
    pdf_path = db.get_pdf_path(conn, doc_id)
    conn.close()
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

    conn = db.get_connection()
    db.save_phase3_review(conn, doc_id, decision, notes, exclusion_code_ids)
    conn.close()
    return jsonify({"success": True})


# --- API: Codes (hierarchical) ---

@app.route("/api/codes")
def api_codes():
    conn = db.get_connection()
    codes = db.get_codes(conn)
    conn.close()
    return jsonify(codes)


@app.route("/api/codes", methods=["POST"])
def api_create_code():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "name required"}), 400
    conn = db.get_connection()
    try:
        code = db.create_code(
            conn, data["name"], data.get("parent_id"),
            data.get("description", ""), data.get("color", "#FFEB3B"),
            data.get("sort_order", 0),
        )
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 400
    conn.close()
    return jsonify(code), 201


@app.route("/api/codes/<int:code_id>", methods=["PUT"])
def api_update_code(code_id):
    data = request.get_json()
    conn = db.get_connection()
    code = db.update_code(conn, code_id, **data)
    conn.close()
    if code is None:
        return jsonify({"error": "Not found or no changes"}), 404
    return jsonify(code)


@app.route("/api/codes/<int:code_id>", methods=["DELETE"])
def api_delete_code(code_id):
    conn = db.get_connection()
    ok = db.delete_code(conn, code_id)
    conn.close()
    if not ok:
        return jsonify({"error": "Code has annotations or sub-codes"}), 400
    return jsonify({"success": True})


# --- API: Annotations ---

@app.route("/api/papers/<int:doc_id>/annotations")
def api_annotations(doc_id):
    conn = db.get_connection()
    annotations = db.get_annotations(conn, doc_id)
    conn.close()
    return jsonify(annotations)


@app.route("/api/papers/<int:doc_id>/annotations", methods=["POST"])
def api_create_annotation(doc_id):
    data = request.get_json()
    if not data or not data.get("rects_json"):
        return jsonify({"error": "rects_json required"}), 400
    conn = db.get_connection()
    ann = db.create_annotation(
        conn, doc_id, data.get("annotation_type", "highlight"),
        data.get("page_number", 1), data["rects_json"],
        data.get("selected_text"), data.get("note"), data.get("color"),
        data.get("code_ids"),
    )
    conn.close()
    return jsonify(ann), 201


@app.route("/api/annotations/<int:ann_id>", methods=["PUT"])
def api_update_annotation(ann_id):
    data = request.get_json()
    conn = db.get_connection()
    ann = db.update_annotation(conn, ann_id, **data)
    conn.close()
    if ann is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(ann)


@app.route("/api/annotations/<int:ann_id>", methods=["DELETE"])
def api_delete_annotation(ann_id):
    conn = db.get_connection()
    ok = db.delete_annotation(conn, ann_id)
    conn.close()
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/annotations/<int:ann_id>/codes/<int:code_id>", methods=["POST"])
def api_add_annotation_code(ann_id, code_id):
    data = request.get_json(silent=True) or {}
    conn = db.get_connection()
    db.add_annotation_code(conn, ann_id, code_id, data.get("note"))
    conn.close()
    return jsonify({"success": True})


@app.route("/api/annotations/<int:ann_id>/codes/<int:code_id>/note", methods=["PUT"])
def api_update_annotation_code_note(ann_id, code_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    conn = db.get_connection()
    db.update_annotation_code_note(conn, ann_id, code_id, data.get("note", ""))
    conn.close()
    return jsonify({"success": True})


@app.route("/api/annotations/<int:ann_id>/codes/<int:code_id>", methods=["DELETE"])
def api_remove_annotation_code(ann_id, code_id):
    conn = db.get_connection()
    db.remove_annotation_code(conn, ann_id, code_id)
    conn.close()
    return jsonify({"success": True})


@app.route("/api/codes/usage")
def api_code_usage_counts():
    conn = db.get_connection()
    counts = db.get_code_usage_counts(conn)
    conn.close()
    return jsonify(counts)


# --- API: Matrix ---

@app.route("/api/matrix")
def api_matrix():
    conn = db.get_connection()
    matrix = db.get_matrix(conn)
    conn.close()
    return jsonify(matrix)


@app.route("/api/papers/<int:doc_id>/matrix-cells")
def api_paper_matrix_cells(doc_id):
    conn = db.get_connection()
    cells = db.get_paper_matrix_cells(conn, doc_id)
    conn.close()
    return jsonify(cells)


@app.route("/api/matrix/cell", methods=["POST"])
def api_save_matrix_cell():
    data = request.get_json()
    if not data or not data.get("document_id") or not data.get("code_id"):
        return jsonify({"error": "document_id and code_id required"}), 400
    conn = db.get_connection()
    cell = db.save_matrix_cell(
        conn, data["document_id"], data["code_id"],
        data.get("value"), data.get("notes"),
    )
    conn.close()
    return jsonify(cell)


# --- API: Coding Completeness ---

@app.route("/api/coding/completeness")
def api_coding_completeness():
    conn = db.get_connection()
    completeness = db.get_coding_completeness(conn)
    conn.close()
    return jsonify(completeness)


# --- API: Stats ---

@app.route("/api/stats")
def api_stats():
    conn = db.get_connection()
    stats = db.get_stats(conn)
    conn.close()
    return jsonify(stats)


# --- Main ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    init_db()
    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
