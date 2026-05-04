#!/usr/bin/env python3
"""Generate LaTeX \newcommand counts for Chapter 2 coding tables.

Reads the coding SQLite database and writes a single .tex file of
\newcommand definitions, one per table cell that shows a paper count.
The chapter text references these commands so only the numbers refresh
as coding progresses.

Usage:
    uv run python scripts/generate_table_counts.py

Output:
    brothrock-dissertation/generated/coding-counts.tex
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
DB_PATH = REPO_ROOT / "lit-review" / "coding" / "lit_review.db"
OUT_PATH = REPO_ROOT / "brothrock-dissertation" / "generated" / "coding-counts.tex"

APP_FRAMING_COLUMN_ID = 4
EVAL_TYPE_COLUMN_ID = 5
REUSE_COLUMNS = {
    "Hw": 6,   # Hardware / Platform
    "Fw": 7,   # Firmware
    "An": 8,   # Analysis / Processing
    "Sw": 28,  # Software
}

# Raw DB value -> canonical suffix used in \newcommand names.
APP_FRAMING_MAP = {
    "Hypothetical": "Hypothetical",
    "Adjacent": "Adjacent",
    "Hypothesis/Literature": "HypLit",
    "Secondary Observational": "SecondaryObs",
    "Primary Observational": "PrimaryObs",
    "Co-Design/Participatory": "CoDesign",
    "Co-Design/Participatory in Context": "CoDesignContext",
}
APP_FRAMING_BUCKETS = [
    "Hypothetical", "Adjacent", "HypLit", "SecondaryObs", "PrimaryObs",
    "CoDesign", "CoDesignContext",
]

EVAL_TYPE_MAP = {
    "None": "None",
    "Benchtop/Simulation": "Benchtop",
    "Controlled/Proxy Setting": "Controlled",
    "Demostration": "Feasibility",
    "Demonstration": "Feasibility",
    "Feasibility Demonstration": "Feasibility",
    "Participatory/Workshop": "Participatory",
    "Target Context with Limited Scope": "TargetLimited",
    "Target Context (Ecological/Longitudinal)": "TargetFull",
    "Full Scale": "FullScale",
    "Full Scale Deployment": "FullScale",
}
EVAL_TYPE_BUCKETS = [
    "None", "Benchtop", "Controlled", "Feasibility", "Participatory",
    "TargetLimited", "TargetFull", "FullScale",
]

REUSE_MAP = {
    "0 - Unavailable": "Zero",
    "1 - Described": "One",
    "1 - Described Limited": "One",
    "2 - Described Detailed": "Two",
    "2- Described Detailed": "Two",
    "3 - Available": "Three",
    "4 - Documented": "Four",
    "N/A": "NA",
    "Previous Works": "PrevWorks",
    "CoTS": "CoTS",
}
REUSE_BUCKETS = ["Zero", "One", "Two", "Three", "Four", "NA", "PrevWorks", "CoTS"]

# DB exclusion_code.code -> chapter code index (EX1..EX8 in the chapter table).
EXCLUSION_MAP = {
    "EX1": "One",
    "EX2": "Two",
    "EX3": "Three",
    "EX5": "Four",          # chapter EX4 (Application-agnostic)
    "EX6": "Five",          # chapter EX5 (No embedded artifact)
    "reivew": "Six",        # chapter EX6 (Review/survey) -- DB typo preserved
    "lacks detail": "Seven",  # chapter EX7 (Insufficient detail)
    "other": "Eight",       # chapter EX8 (Other)
}
EXCLUSION_BUCKETS = [
    "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
]


def included_document_ids(conn: sqlite3.Connection) -> set[int]:
    cur = conn.execute(
        "SELECT document_id FROM pass_review "
        "WHERE pass_number = 3 AND decision = 'include'"
    )
    return {row[0] for row in cur}


def count_single_column(
    conn: sqlite3.Connection, column_id: int, included: set[int],
    label_map: dict[str, str], buckets: list[str], context: str,
) -> Counter:
    counts = Counter({b: 0 for b in buckets})
    cur = conn.execute(
        "SELECT document_id, value FROM matrix_cell WHERE column_id = ?",
        (column_id,),
    )
    for doc_id, value in cur:
        if doc_id not in included or value is None:
            continue
        bucket = label_map.get(value)
        if bucket is None:
            print(
                f"[warn] {context}: unmapped value {value!r} on document {doc_id}",
                file=sys.stderr,
            )
            continue
        counts[bucket] += 1
    return counts


def count_multi_column(
    conn: sqlite3.Connection, column_id: int, included: set[int],
    label_map: dict[str, str], buckets: list[str], context: str,
) -> Counter:
    counts = Counter({b: 0 for b in buckets})
    cur = conn.execute(
        "SELECT document_id, value FROM matrix_cell WHERE column_id = ?",
        (column_id,),
    )
    for doc_id, value in cur:
        if doc_id not in included or value is None:
            continue
        try:
            labels = json.loads(value)
        except json.JSONDecodeError:
            labels = [value]
        for label in labels:
            bucket = label_map.get(label)
            if bucket is None:
                print(
                    f"[warn] {context}: unmapped value {label!r} on document {doc_id}",
                    file=sys.stderr,
                )
                continue
            counts[bucket] += 1
    return counts


def count_exclusions(conn: sqlite3.Connection) -> tuple[Counter, int]:
    counts = Counter({b: 0 for b in EXCLUSION_BUCKETS})
    total = 0
    cur = conn.execute(
        "SELECT ec.code, COUNT(*) "
        "FROM pass_review_exclusion_code prec "
        "JOIN exclusion_code ec ON ec.id = prec.exclusion_code_id "
        "GROUP BY ec.code"
    )
    for code, n in cur:
        total += n
        bucket = EXCLUSION_MAP.get(code)
        if bucket is None:
            print(f"[warn] exclusion: unmapped code {code!r}", file=sys.stderr)
            continue
        counts[bucket] += n
    return counts, total


def render_newcommand(name: str, value: int) -> str:
    return f"\\newcommand{{\\{name}}}{{{value}}}\n"


def main() -> int:
    if not DB_PATH.exists():
        print(f"error: database not found at {DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        included = included_document_ids(conn)
        n_included = len(included)

        app_framing = count_single_column(
            conn, APP_FRAMING_COLUMN_ID, included,
            APP_FRAMING_MAP, APP_FRAMING_BUCKETS, "Application Framing",
        )

        eval_type = count_multi_column(
            conn, EVAL_TYPE_COLUMN_ID, included,
            EVAL_TYPE_MAP, EVAL_TYPE_BUCKETS, "Evaluation Type",
        )

        reuse: dict[str, Counter] = {}
        for dim, col in REUSE_COLUMNS.items():
            reuse[dim] = count_single_column(
                conn, col, included, REUSE_MAP, REUSE_BUCKETS,
                f"Reusability-{dim}",
            )

        excl_counts, excl_total = count_exclusions(conn)
    finally:
        conn.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(
        f"% Generated by lit-review/scripts/generate_table_counts.py on {stamp}.\n"
        f"% Do not edit by hand -- rerun the script to refresh.\n"
        f"%\n"
        f"% Source DB: lit-review/coding/lit_review.db\n"
        f"% Phase 3 included papers: {n_included}\n\n"
    )

    lines.append("% --- Global ---\n")
    lines.append(render_newcommand("nPapersIncluded", n_included))
    lines.append("\n")

    lines.append("% --- Application Framing (enum_single, column 4) ---\n")
    for bucket in APP_FRAMING_BUCKETS:
        lines.append(render_newcommand(f"nAF{bucket}", app_framing[bucket]))
    lines.append("\n")

    lines.append(
        "% --- Evaluation Type (enum_multi, column 5; totals may exceed "
        f"{n_included}) ---\n"
    )
    for bucket in EVAL_TYPE_BUCKETS:
        lines.append(render_newcommand(f"nEval{bucket}", eval_type[bucket]))
    lines.append("\n")

    lines.append(
        "% --- Reusability rubric (enum_single, columns 6/7/8/28). Dims: "
        "Hw=Hardware, Fw=Firmware, An=Analysis, Sw=Software ---\n"
    )
    for dim in REUSE_COLUMNS:
        for bucket in REUSE_BUCKETS:
            lines.append(
                render_newcommand(f"nReuse{dim}{bucket}", reuse[dim][bucket])
            )
        lines.append("\n")

    lines.append("% --- Exclusion criteria (summed across phases 1-3) ---\n")
    for bucket in EXCLUSION_BUCKETS:
        lines.append(render_newcommand(f"nExcl{bucket}", excl_counts[bucket]))
    lines.append(render_newcommand("nExclTotal", excl_total))
    lines.append("\n")

    OUT_PATH.write_text("".join(lines), encoding="utf-8")

    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  included papers (phase 3): {n_included}")
    print(f"  application framing total: {sum(app_framing.values())}")
    print(f"  evaluation type tag total: {sum(eval_type.values())}")
    for dim, col in REUSE_COLUMNS.items():
        print(f"  reusability {dim} total:       {sum(reuse[dim].values())}")
    print(f"  exclusion tags total:      {excl_total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
