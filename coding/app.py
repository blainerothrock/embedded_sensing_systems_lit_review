"""Lit Review Coding — Flask web application."""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory

import db
import schema

load_dotenv()

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

DIST_DIR = Path(__file__).parent / "static" / "dist"


@app.route("/")
def index():
    return send_from_directory(DIST_DIR, "index.html")


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(DIST_DIR / "assets", filename)


# --- API: Papers ---

@app.route("/api/papers")
def api_papers():
    search = request.args.get("search", "")
    status = request.args.get("status", "all")
    sort = request.args.get("sort", "title")
    with db.connect() as conn:
        papers = db.get_phase3_papers(conn, search=search, status=status, sort=sort)
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


@app.route("/api/papers/<int:doc_id>/coding-status", methods=["POST"])
def api_save_coding_status(doc_id):
    data = request.get_json()
    status = data.get("coding_status")  # 'coding', 'complete', or null
    with db.connect() as conn:
        conn.execute("""
            UPDATE pass_review SET coding_status = ?
            WHERE document_id = ? AND pass_number = 3
        """, (status, doc_id))
        conn.commit()
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


@app.route("/api/matrix-column-options/<int:opt_id>", methods=["PUT"])
def api_update_column_option(opt_id):
    data = request.get_json()
    with db.connect() as conn:
        opt = db.update_column_option(conn, opt_id, **data)
    if opt is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(opt)


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
    status = request.args.get("status", "all")
    with db.connect() as conn:
        matrix = db.get_matrix(conn, status=status)
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


# --- API: Chat ---

import llm as llm_providers


def _build_system_prompt(conn, doc_id: int) -> str:
    """Build system prompt with paper context, codes, columns, and annotations."""
    paper = db.get_paper(conn, doc_id)
    pages = db.get_pdf_text(doc_id, PDF_DIR)
    codes = db.get_codes(conn)
    columns = db.get_matrix_columns(conn)
    annotations = db.get_annotations(conn, doc_id)

    parts = [
        "You are a research assistant helping with qualitative coding of an academic paper.",
        "You have the full text of the paper below.",
        "",
        "When referencing specific passages, use page references: [[p.{page_number}]]",
        "When quoting directly from the paper, use this format: [[quote:\"exact text from paper\" p.{page_number}]]",
        "The quote text should be a short exact excerpt (1-2 sentences max). Examples:",
        '- "The authors describe their BLE implementation [[p.5]]"',
        '- [[quote:"We deployed 12 sensor nodes across the hillside over a 6-month period" p.3]]',
        '- The evaluation methodology [[quote:"used a controlled lab environment with 5 participants" p.7]] suggests limited ecological validity.',
        "",
        "## Paper Metadata",
        f"Title: {paper['title'] or 'Unknown'}",
        f"Authors: {paper['author'] or 'Unknown'}",
        f"Year: {paper['year'] or 'Unknown'}",
        f"Venue: {paper['venue'] or 'Unknown'}",
    ]

    if codes:
        parts.append("\n## Annotation Codes")
        parts.append("The researcher uses these codes to tag passages in papers:")
        for code in codes:
            desc = f" — {code['description']}" if code.get('description') else ""
            parts.append(f"- **{code['name']}**{desc}")
            for child in code.get("children", []):
                cdesc = f" — {child['description']}" if child.get('description') else ""
                parts.append(f"  - {child['name']}{cdesc}")

    if columns:
        parts.append("\n## Synthesis Matrix Columns")
        parts.append("The synthesis matrix tracks these dimensions per paper:")
        for col in columns:
            opts = ""
            if col.get("options"):
                opts = f" (options: {', '.join(o['value'] for o in col['options'])})"
            cdesc = f" — {col['description']}" if col.get('description') else ""
            parts.append(f"- **{col['name']}** [{col['column_type']}]{opts}{cdesc}")

    if annotations:
        parts.append("\n## Current Annotations on This Paper")
        for ann in annotations:
            code_names = ", ".join(c["name"] for c in ann.get("codes", []))
            text = ann.get("selected_text", "") or ann.get("note", "") or "(area)"
            preview = text[:200] + "..." if len(text) > 200 else text
            parts.append(f"- p.{ann['page_number']} [{code_names}]: \"{preview}\"")

    if pages:
        parts.append("\n## Full Paper Text")
        parts.append(db.format_pdf_for_prompt(pages))

    return "\n".join(parts)


def _build_prompt_summary(conn, doc_id: int) -> str:
    """Build a compact summary of the system prompt for storage (no full text)."""
    paper = db.get_paper(conn, doc_id)
    pages = db.get_pdf_text(doc_id, PDF_DIR)
    codes = db.get_codes(conn)
    columns = db.get_matrix_columns(conn)
    annotations = db.get_annotations(conn, doc_id)

    parts = [
        "[System instructions + page reference / quote format]",
        "",
        "## Paper Metadata",
        f"Title: {paper['title'] or 'Unknown'}",
        f"Authors: {paper['author'] or 'Unknown'}",
        f"Year: {paper['year'] or 'Unknown'}",
        f"Venue: {paper['venue'] or 'Unknown'}",
    ]

    if codes:
        parts.append(f"\n## Annotation Codes ({sum(1 + len(c.get('children', [])) for c in codes)} total)")
        for code in codes:
            desc = f" — {code['description']}" if code.get('description') else ""
            parts.append(f"- {code['name']}{desc}")
            for child in code.get("children", []):
                cdesc = f" — {child['description']}" if child.get('description') else ""
                parts.append(f"  - {child['name']}{cdesc}")

    if columns:
        parts.append(f"\n## Matrix Columns ({len(columns)} total)")
        for col in columns:
            opts = ""
            if col.get("options"):
                opts = f" (options: {', '.join(o['value'] for o in col['options'])})"
            parts.append(f"- {col['name']} [{col['column_type']}]{opts}")

    if annotations:
        parts.append(f"\n## Annotations on Paper ({len(annotations)} total)")
        parts.append("[annotation details included]")

    if pages:
        total_chars = sum(len(t) for t in pages.values())
        parts.append(f"\n## Full Paper Text ({len(pages)} pages, ~{total_chars:,} chars)")
        parts.append("[full text included]")

    return "\n".join(parts)


@app.route("/api/papers/<int:doc_id>/chats")
def api_get_chats(doc_id):
    with db.connect() as conn:
        chats = db.get_chats(conn, doc_id)
    return jsonify(chats)


@app.route("/api/chats/<int:chat_id>/messages")
def api_get_chat_messages(chat_id):
    with db.connect() as conn:
        messages = db.get_chat_messages(conn, chat_id)
    return jsonify(messages)


@app.route("/api/chats/<int:chat_id>", methods=["PUT"])
def api_update_chat(chat_id):
    data = request.get_json()
    with db.connect() as conn:
        chat = db.update_chat(conn, chat_id, **data)
    if chat is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(chat)


@app.route("/api/chats/<int:chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    with db.connect() as conn:
        ok = db.delete_chat(conn, chat_id)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/llm/models")
def api_llm_models():
    """Get available LLM providers and models."""
    ollama_models = llm_providers.get_ollama_models()
    return jsonify({
        "ollama": ollama_models,
        "claude": True,  # always available if CLI is installed
        "default_params": llm_providers.DEFAULT_OLLAMA_PARAMS,
    })


@app.route("/api/papers/<int:doc_id>/chat", methods=["POST"])
def api_chat(doc_id):
    """Send a message and stream LLM response via SSE."""
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "message required"}), 400

    user_message = data["message"]
    chat_id = data.get("chat_id")
    provider = data.get("provider", "ollama")
    model = data.get("model", "qwen3.5:9b")
    params = data.get("params")

    with db.connect() as conn:
        # Create or get chat
        if chat_id:
            chat = db.get_chat(conn, chat_id)
            if not chat:
                return jsonify({"error": "Chat not found"}), 404
            provider = chat["provider"]
            model = chat["model"]
            if chat["params"]:
                params = json.loads(chat["params"])
        else:
            params_json = json.dumps(params) if params else None
            chat_model = model if provider == "ollama" else "claude"
            prompt_summary = _build_prompt_summary(conn, doc_id)
            chat = db.create_chat(
                conn, doc_id, provider=provider, model=chat_model,
                params=params_json, system_prompt=prompt_summary,
            )
            chat_id = chat["id"]

        # Build system prompt
        system_prompt = _build_system_prompt(conn, doc_id)

        # Load conversation history
        history = db.get_chat_messages(conn, chat_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": user_message})

        # Save user message
        db.save_message(conn, chat_id, "user", user_message)

    def generate():
        full_response = ""
        try:
            yield f"data: {json.dumps({'type': 'chat_id', 'chat_id': chat_id})}\n\n"

            if provider == "ollama":
                stream = llm_providers.stream_ollama(model, system_prompt, messages, params)
            elif provider == "claude":
                stream = llm_providers.stream_claude(system_prompt, messages)
            else:
                yield f"data: {json.dumps({'type': 'error', 'error': f'Unknown provider: {provider}'})}\n\n"
                return

            for text in stream:
                full_response += text
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"

            with db.connect() as conn:
                db.save_message(conn, chat_id, "assistant", full_response)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


# --- API: Paper Notes ---

@app.route("/api/papers/<int:doc_id>/notes")
def api_get_paper_note(doc_id):
    with db.connect() as conn:
        content = db.get_paper_note(conn, doc_id)
    return jsonify({"content": content})


@app.route("/api/papers/<int:doc_id>/notes", methods=["PUT"])
def api_save_paper_note(doc_id):
    data = request.get_json()
    with db.connect() as conn:
        db.save_paper_note(conn, doc_id, data.get("content", ""))
    return jsonify({"success": True})


# --- API: Settings ---

@app.route("/api/settings")
def api_get_settings():
    with db.connect() as conn:
        settings = db.get_all_settings(conn)
    return jsonify(settings)


@app.route("/api/settings", methods=["PUT"])
def api_save_settings():
    data = request.get_json()
    with db.connect() as conn:
        for key, value in data.items():
            db.save_setting(conn, key, str(value))
    return jsonify({"success": True})


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
    parser.add_argument("--dev-url", default=None, help="Vite dev server URL for desktop mode (e.g. http://localhost:5173)")
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
        url = args.dev_url or f"http://127.0.0.1:{args.port}"
        webview.create_window(
            "Lit Review Coding",
            url,
            width=1400,
            height=900,
            text_select=True,
            easy_drag=False,
        )
        webview.start()
    else:
        app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
