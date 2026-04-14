"""Batch LLM chat for papers via vLLM server.

Runs a series of prompts (from a file, separated by ---) against multiple papers.
Each paper gets one chat session with all prompts sent sequentially.
Results are saved to the DB and viewable in the UI.

Usage:
    uv run python batch_chat.py --prompt prompts.txt --papers 1051 1125 1137
    uv run python batch_chat.py --prompt prompts.txt --all
    uv run python batch_chat.py --prompt prompts.txt --all --dry-run
"""

import argparse
import json
import sys
import time
from pathlib import Path

import db
import llm as llm_providers

PDF_DIR = Path(__file__).parent / "pdfs"


def parse_prompts(prompt_file: Path) -> list[str]:
    """Parse prompt file into list of prompts, split by --- delimiter."""
    text = prompt_file.read_text().strip()
    prompts = [p.strip() for p in text.split("---")]
    return [p for p in prompts if p]


def build_system_prompt(conn, doc_id: int) -> str:
    """Build system prompt with paper context — mirrors app.py _build_system_prompt."""
    paper = db.get_paper(conn, doc_id)
    pages = db.get_pdf_text(doc_id, PDF_DIR)
    codes = db.get_codes(conn)
    columns = db.get_matrix_columns(conn)
    annotations = db.get_annotations(conn, doc_id)

    parts = [
        "You are a research assistant helping with qualitative coding of an academic paper.",
        "You have the full text of the paper below.",
        "Format responses using markdown (headers, lists, tables, bold, etc.). Do not use LaTeX notation — use plain text arrows (→) and symbols instead.",
        "",
        "When referencing specific passages, use page references: [[p.{page_number}]] where page_number is an integer (e.g. [[p.5]], NOT section numbers like p.4.1).",
        "For multiple pages, use separate refs: [[p.9]] [[p.10]] (NOT [[p.9], [p.10]]).",
        "STRONGLY PREFER quoting over plain page refs — quotes allow the reader to locate the exact passage on the page.",
        "When quoting from the paper, use: [[quote:\"exact text from paper\" p.{page_number}]]",
        "Even if the quote is not the full context of your point, include a short exact excerpt so the reader can find it. Examples:",
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


def build_prompt_summary(conn, doc_id: int) -> str:
    """Build compact summary for DB storage — mirrors app.py _build_prompt_summary."""
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


def get_all_paper_ids(conn) -> list[int]:
    """Get all included papers that have PDFs."""
    papers = db.get_phase3_papers(conn, status="include,has_pdf")
    return [p["id"] for p in papers]


def run_batch(paper_ids: list[int], prompts: list[str], model: str,
              max_tokens: int, dry_run: bool):
    config_path = Path(__file__).parent / "gpu_server_config.json"
    with open(config_path) as f:
        config = json.load(f)
    default_model = config.get("served_model_name", "qwen3.5-35b-a3b")
    model = model or default_model

    params = {
        "num_predict": max_tokens,
        "temperature": 0.0,
        "top_p": 0.95,
        "presence_penalty": 1.5,
    }

    print(f"Model: {model}")
    print(f"Max tokens: {max_tokens}")
    print(f"Papers: {len(paper_ids)}")
    print(f"Prompts per paper: {len(prompts)}")
    for i, p in enumerate(prompts, 1):
        preview = p[:80] + "..." if len(p) > 80 else p
        print(f"  [{i}] {preview}")
    print()

    if dry_run:
        with db.connect() as conn:
            for doc_id in paper_ids:
                paper = db.get_paper(conn, doc_id)
                if not paper:
                    print(f"  [{doc_id}] NOT FOUND")
                    continue
                pdf_path = PDF_DIR / f"{doc_id}.pdf"
                has_pdf = "✓" if pdf_path.exists() else "✗ NO PDF"
                print(f"  [{doc_id}] {paper['title'][:70]} ({has_pdf})")
        print("\nDry run — no chats created.")
        return

    # Check vLLM server
    status = llm_providers.get_vllm_status()
    if status["vllm"] != "ready":
        print(f"ERROR: vLLM server not ready (status: {status['vllm']})")
        sys.exit(1)
    print(f"vLLM server ready, available models: {status['models']}")
    print()

    succeeded = 0
    failed = 0

    for idx, doc_id in enumerate(paper_ids, 1):
        with db.connect() as conn:
            paper = db.get_paper(conn, doc_id)
            if not paper:
                print(f"[{idx}/{len(paper_ids)}] Doc {doc_id}: NOT FOUND — skipping")
                failed += 1
                continue

            pdf_path = PDF_DIR / f"{doc_id}.pdf"
            if not pdf_path.exists():
                print(f"[{idx}/{len(paper_ids)}] Doc {doc_id}: NO PDF — skipping")
                failed += 1
                continue

            title = paper['title'][:60]
            print(f"[{idx}/{len(paper_ids)}] {title} (id={doc_id})")

            try:
                system_prompt = build_system_prompt(conn, doc_id)
                prompt_summary = build_prompt_summary(conn, doc_id)
                params_json = json.dumps(params)

                existing = db.get_chats(conn, doc_id)
                chat_title = f"batch-{doc_id}-{len(existing) + 1}"
                chat = db.create_chat(
                    conn, doc_id, title=chat_title, provider="vllm",
                    model=model, params=params_json,
                    system_prompt=prompt_summary,
                )
                chat_id = chat["id"]
                messages = []

                for pi, prompt_text in enumerate(prompts, 1):
                    print(f"  Prompt {pi}/{len(prompts)}...", end=" ", flush=True)
                    t0 = time.time()

                    messages.append({"role": "user", "content": prompt_text})
                    db.save_message(conn, chat_id, "user", prompt_text)

                    full_response = ""
                    metrics = {}
                    for chunk in llm_providers.stream_vllm(model, system_prompt, messages, params):
                        if isinstance(chunk, dict):
                            metrics = chunk
                        else:
                            full_response += chunk

                    messages.append({"role": "assistant", "content": full_response})
                    db.save_message(conn, chat_id, "assistant", full_response)

                    elapsed = time.time() - t0
                    tok_info = ""
                    if metrics:
                        tok_in = metrics.get("prompt_eval_count", "?")
                        tok_out = metrics.get("eval_count", "?")
                        tok_info = f" ({tok_in} in / {tok_out} out)"
                    print(f"done in {elapsed:.1f}s{tok_info}")

                succeeded += 1

            except Exception as e:
                print(f"  ERROR: {e}")
                failed += 1
                continue

    print(f"\nDone: {succeeded} succeeded, {failed} failed out of {len(paper_ids)} papers")


def main():
    parser = argparse.ArgumentParser(description="Batch LLM chat for papers via vLLM")
    parser.add_argument("--prompt", required=True, type=Path,
                        help="Path to prompt file (prompts separated by ---)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--papers", nargs="+", type=int,
                       help="Document IDs to process")
    group.add_argument("--all", action="store_true", dest="all_papers",
                       help="Process all included papers with PDFs")
    parser.add_argument("--model", default=None,
                        help="Model name (default: from gpu_server_config.json)")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="Max output tokens (default: 2048)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without calling LLM")
    args = parser.parse_args()

    if not args.prompt.exists():
        print(f"ERROR: Prompt file not found: {args.prompt}")
        sys.exit(1)

    prompts = parse_prompts(args.prompt)
    if not prompts:
        print("ERROR: No prompts found in file")
        sys.exit(1)

    if args.all_papers:
        with db.connect() as conn:
            paper_ids = get_all_paper_ids(conn)
        if not paper_ids:
            print("No included papers with PDFs found")
            sys.exit(1)
    else:
        paper_ids = args.papers

    run_batch(paper_ids, prompts, args.model, args.max_tokens, args.dry_run)


if __name__ == "__main__":
    main()
