#!/usr/bin/env python3
"""Generate the curated paper-matrix artifacts for Chapter 2.

Reads:
  - lit-review/coding/lit_review.db   (paper coding)
  - lit-review/coding/matrix-papers.txt (curated, ordered bibtex_keys by domain;
                                         auto-seeded on first run)

Writes:
  - brothrock-dissertation/generated/matrix-cells.tex
        One \\def per (AUTO column, paper) + per-column accessor macros +
        a \\matReuseMax{bibkey} composite reuse indicator.
  - brothrock-dissertation/generated/crosstab-framing-eval.tex
        Summary table: Application Framing x Evaluation Type paper counts.

Phase 1 scope: cells + cross-tab + seeder.
Phase 2 (forthcoming): `--bootstrap` to emit tables/lit-review/main-matrix.tex.

Usage:
    uv run python scripts/generate_matrix.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

DB_PATH = REPO_ROOT / "lit-review" / "coding" / "lit_review.db"
LIST_PATH = REPO_ROOT / "lit-review" / "coding" / "matrix-papers.txt"
CELLS_OUT = REPO_ROOT / "brothrock-dissertation" / "generated" / "matrix-cells.tex"
CROSSTAB_OUT = (
    REPO_ROOT / "brothrock-dissertation" / "generated" / "crosstab-framing-eval.tex"
)
MATRIX_OUT = (
    REPO_ROOT / "brothrock-dissertation" / "tables" / "lit-review" / "main-matrix.tex"
)

# ---- Column IDs ----

COL_APP_TYPE = 3
COL_APP_FRAMING = 4
COL_EVAL_TYPE = 5
COL_REUSE_HW = 6
COL_REUSE_FW = 7
COL_REUSE_AN = 8
COL_REUSE_SW = 28
COL_SENSORS = 13
COL_DATA_TECH = 12
COL_DATA_PROC = 30

# ---- Short-form maps (raw DB value -> display string) ----

APP_TYPE_MAP = {
    "Health": "H",
    "Ecological": "E",
    "Other": "O",
}

APP_FRAMING_MAP = {
    "Hypothetical": "Hypot",
    "Adjacent": "Adj",
    "Hypothesis/Literature": "Hyp/Lit",
    "Secondary Observational": "SecObs",
    "Primary Observational": "PrimObs",
    "Co-Design/Participatory": "Co",
    "Co-Design/Participatory in Context": "Co+",
}

EVAL_TYPE_MAP = {
    "None": "---",
    "Benchtop/Simulation": "Bench",
    "Controlled/Proxy Setting": "Ctrl",
    "Demostration": "Demo",
    "Demonstration": "Demo",
    "Feasibility Demonstration": "Demo",
    "Participatory/Workshop": "Wkshp",
    "Target Context with Limited Scope": "TCLtd",
    "Target Context (Ecological/Longitudinal)": "TCFull",
    "Full Scale": "FullS",
    "Full Scale Deployment": "FullS",
}

REUSE_MAP = {
    "0 - Unavailable": "0",
    "1 - Described": "1",
    "1 - Described Limited": "1",
    "2 - Described Detailed": "2",
    "2- Described Detailed": "2",
    "3 - Available": "3",
    "4 - Documented": "4",
    "N/A": "---",
    "Previous Works": "PW",
    "CoTS": "CoTS",
}

SENSORS_MAP = {
    "Temperature": "Temp",
    "Air Quality": "AirQ",
    "Basic Environmental": "BasicEnv",
    "Ultrasonic": "Ultra",
    "Microphone": "Mic",
    "Passive IR": "PIR",
    "Water Quality": "WaterQ",
    "IMU": "IMU",
    "PPG": "PPG",
    "GPS": "GPS",
    "Camera": "Cam",
    "LIDAR": "LiDAR",
    "Custom": "Custom",
    "Light": "Light",
    "Humidity": "Humid",
    "Pressure": "Press",
    "Soil": "Soil",
    "Gas": "Gas",
    "RFID": "RFID",
    "Electrical": "Elec",
    "Potentiostat": "Poten",
    "SpO2": "SpO2",
    "Force": "Force",
    "GSR": "GSR",
    "EMG": "EMG",
    "Rotary": "Rotary",
    "Touch": "Touch",
    "Vibration": "Vib",
}

DATA_TECH_MAP = {
    "BLE": "BLE",
    "WiFi": "WiFi",
    "LoRA": "LoRa",
    "LoRa": "LoRa",
    "ZigBee": "ZigBee",
    "Wired": "Wired",
    "Custom": "Custom",
    "None": "---",
    "None/Envisioned": "Envis",
    "Not Specified": "NS",
    "RFID": "RFID",
    "Backscatter": "BScat",
    "Cellular": "Cell",
    "Onboard": "OnDev",
}

DATA_PROC_MAP = {
    "onboard": "OnDev",
    "cloud": "Cloud",
    "Machine Learning": "ML",
    "Deep Learning": "DL",
    "one-off scripting/exploratory": "Script",
}

# Column display name, DB id, raw->short map, enum style.
AUTO_COLUMNS = [
    ("AppType",    COL_APP_TYPE,    APP_TYPE_MAP,    "single"),
    ("AppFraming", COL_APP_FRAMING, APP_FRAMING_MAP, "single"),
    ("EvalType",   COL_EVAL_TYPE,   EVAL_TYPE_MAP,   "multi"),
    ("ReuseHw",    COL_REUSE_HW,    REUSE_MAP,       "single"),
    ("ReuseFw",    COL_REUSE_FW,    REUSE_MAP,       "single"),
    ("ReuseAn",    COL_REUSE_AN,    REUSE_MAP,       "single"),
    ("ReuseSw",    COL_REUSE_SW,    REUSE_MAP,       "single"),
    ("Sensors",    COL_SENSORS,     SENSORS_MAP,     "multi"),
    ("DataTech",   COL_DATA_TECH,   DATA_TECH_MAP,   "multi"),
    ("DataProc",   COL_DATA_PROC,   DATA_PROC_MAP,   "multi"),
]

REUSE_NAMES = ("ReuseHw", "ReuseFw", "ReuseAn", "ReuseSw")

MISSING = "---"


# ---- DB access ----

def connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def included_papers(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """Return [(doc_id, bibkey, app_type)] for Phase 3 included papers, Health before Ecological before Other."""
    order = {"Health": 0, "Ecological": 1, "Other": 2}
    cur = conn.execute(
        """
        SELECT d.id, d.bibtex_key, COALESCE(mc.value, 'Other') AS app_type
        FROM document d
        JOIN pass_review pr ON pr.document_id = d.id
        LEFT JOIN matrix_cell mc
          ON mc.document_id = d.id AND mc.column_id = ?
        WHERE pr.pass_number = 3 AND pr.decision = 'include'
        """,
        (COL_APP_TYPE,),
    )
    rows = [(r[0], r[1], r[2] or "Other") for r in cur]
    rows.sort(key=lambda r: (order.get(r[2], 99), r[1]))
    return rows


def fetch_cell(conn: sqlite3.Connection, doc_id: int, col_id: int) -> str | None:
    cur = conn.execute(
        "SELECT value FROM matrix_cell WHERE document_id = ? AND column_id = ?",
        (doc_id, col_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    val = row[0]
    if val is None or val == "":
        return None
    return val


# ---- Short-form rendering ----

def render_single(raw: str | None, mapping: dict[str, str], col_label: str) -> str:
    if raw is None:
        return MISSING
    short = mapping.get(raw)
    if short is None:
        print(f"[warn] {col_label}: unmapped value {raw!r}", file=sys.stderr)
        return raw
    return short


def render_multi(raw: str | None, mapping: dict[str, str], col_label: str) -> str:
    if raw is None:
        return MISSING
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        values = [raw]
    if not values:
        return MISSING
    out: list[str] = []
    for v in values:
        short = mapping.get(v)
        if short is None:
            print(f"[warn] {col_label}: unmapped value {v!r}", file=sys.stderr)
            out.append(v)
        else:
            out.append(short)
    return ", ".join(out)


def reuse_max(reuse_values: dict[str, str]) -> str:
    """Highest numeric reuse level across H/F/A/S; --- if all non-numeric."""
    numeric = [int(v) for v in reuse_values.values() if v.isdigit()]
    if not numeric:
        return MISSING
    return str(max(numeric))


# ---- Sidecar list ----

def seed_list_file(papers: list[tuple[int, str, str]], path: Path) -> None:
    """Create matrix-papers.txt grouped by App Type. Only called if file is absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[str]] = {"Health": [], "Ecological": [], "Other": []}
    for _, bibkey, app_type in papers:
        grouped.setdefault(app_type, []).append(bibkey)

    lines = [
        "# Curated paper list for the Chapter 2 main matrix.",
        "# Edit freely: reorder lines, delete papers, move between sections.",
        "# Lines starting with '#' are comments; blank lines are ignored.",
        "# Section headers ('## Health', etc.) group rows in the rendered table.",
        "# Regenerate: cd lit-review && uv run python scripts/generate_matrix.py",
        "",
    ]
    for group in ("Health", "Ecological", "Other"):
        keys = grouped.get(group, [])
        if not keys:
            continue
        lines.append(f"## {group}")
        lines.extend(keys)
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def load_list_file(path: Path) -> list[tuple[str, str]]:
    """Return [(group, bibkey)] in the order given by the file."""
    out: list[tuple[str, str]] = []
    current = "Other"
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") and not line.startswith("##"):
            continue
        if line.startswith("##"):
            current = line.lstrip("#").strip() or "Other"
            continue
        out.append((current, line))
    return out


# ---- LaTeX emission ----

def tex_escape(s: str) -> str:
    """Escape LaTeX specials that can appear in short-form values. Keep it minimal."""
    return (
        s.replace("\\", r"\textbackslash{}")
         .replace("&", r"\&")
         .replace("%", r"\%")
         .replace("_", r"\_")
         .replace("$", r"\$")
         .replace("#", r"\#")
         .replace("^", r"\^{}")
    )


def emit_cells(
    conn: sqlite3.Connection,
    ordered: list[tuple[str, str]],
    bibkey_to_doc: dict[str, int],
    out_path: Path,
) -> tuple[int, int, int]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append(
        f"% Generated by lit-review/scripts/generate_matrix.py on {stamp}.\n"
        f"% Do not edit by hand -- rerun the script to refresh.\n"
        f"%\n"
        f"% Source DB:   lit-review/coding/lit_review.db\n"
        f"% Paper list:  lit-review/coding/matrix-papers.txt\n"
        f"% Mechanism:   \\matCol{{bibkey}} -> \\csname matCol@bibkey\\endcsname\n\n"
    )

    # Accessors (one per AUTO column + \matReuseMax + \matReuseCombined).
    lines.append("% ---- Accessor macros ----\n")
    for name, _, _, _ in AUTO_COLUMNS:
        lines.append(
            f"\\providecommand{{\\mat{name}}}[1]"
            f"{{\\csname mat{name}@#1\\endcsname}}\n"
        )
    lines.append(
        "\\providecommand{\\matReuseMax}[1]"
        "{\\csname matReuseMax@#1\\endcsname}\n"
    )
    lines.append(
        "\\providecommand{\\matReuseCombined}[1]"
        "{\\csname matReuseCombined@#1\\endcsname}\n"
    )
    lines.append("\n")

    n_cell_defs = 0
    unresolved_warnings = 0
    papers_written = 0

    for group, bibkey in ordered:
        doc_id = bibkey_to_doc.get(bibkey)
        if doc_id is None:
            print(
                f"[warn] bibkey not found in Phase 3 included set: {bibkey!r} "
                f"(section {group})",
                file=sys.stderr,
            )
            unresolved_warnings += 1
            continue

        lines.append(f"% ---- {bibkey} ({group}) ----\n")
        reuse_shorts: dict[str, str] = {}
        for name, col_id, mapping, kind in AUTO_COLUMNS:
            raw = fetch_cell(conn, doc_id, col_id)
            if kind == "single":
                short = render_single(raw, mapping, name)
            else:
                short = render_multi(raw, mapping, name)
            if name in REUSE_NAMES:
                reuse_shorts[name] = short
            lines.append(
                f"\\expandafter\\def\\csname mat{name}@{bibkey}\\endcsname"
                f"{{{tex_escape(short)}}}\n"
            )
            n_cell_defs += 1

        composite = reuse_max(reuse_shorts)
        lines.append(
            f"\\expandafter\\def\\csname matReuseMax@{bibkey}\\endcsname"
            f"{{{tex_escape(composite)}}}\n"
        )
        # Use hyphen (not em-dash) for missing in the combined cell so width
        # stays predictable.
        combined = "/".join(
            "-" if reuse_shorts.get(k, MISSING) == MISSING else reuse_shorts[k]
            for k in REUSE_NAMES
        )
        lines.append(
            f"\\expandafter\\def\\csname matReuseCombined@{bibkey}\\endcsname"
            f"{{{tex_escape(combined)}}}\n"
        )
        lines.append("\n")
        papers_written += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    return n_cell_defs, papers_written, unresolved_warnings


def emit_crosstab(
    conn: sqlite3.Connection,
    ordered: list[tuple[str, str]],
    bibkey_to_doc: dict[str, int],
    out_path: Path,
) -> None:
    # Papers -> (framing_short, [eval_short, ...])
    framing_order = list(APP_FRAMING_MAP.values())
    eval_order = [
        "Bench", "Ctrl", "Demo", "Wkshp", "TCLtd", "TCFull", "FullS",
    ]
    counts: dict[tuple[str, str], int] = Counter()
    framing_totals: Counter = Counter()
    eval_totals: Counter = Counter()
    papers_counted = 0

    for _, bibkey in ordered:
        doc_id = bibkey_to_doc.get(bibkey)
        if doc_id is None:
            continue
        framing_raw = fetch_cell(conn, doc_id, COL_APP_FRAMING)
        eval_raw = fetch_cell(conn, doc_id, COL_EVAL_TYPE)
        if framing_raw is None:
            continue
        framing_short = APP_FRAMING_MAP.get(framing_raw, framing_raw)
        eval_values: list[str] = []
        if eval_raw is not None:
            try:
                parsed = json.loads(eval_raw)
            except json.JSONDecodeError:
                parsed = [eval_raw]
            for v in parsed:
                short = EVAL_TYPE_MAP.get(v, v)
                if short != MISSING:
                    eval_values.append(short)
        papers_counted += 1
        framing_totals[framing_short] += 1
        for ev in eval_values:
            counts[(framing_short, ev)] += 1
            eval_totals[ev] += 1

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    col_spec = "@{}l " + " ".join(["S[table-format=2.0]"] * len(eval_order)) + " S[table-format=2.0]@{}"
    lines: list[str] = []
    lines.append(
        f"% Generated by lit-review/scripts/generate_matrix.py on {stamp}.\n"
        f"% Do not edit by hand -- rerun the script to refresh.\n\n"
    )
    lines.append("\\begin{table}[t]\n")
    lines.append("\t\\centering\n")
    lines.append(
        "\t\\caption{Application Framing $\\times$ Evaluation Type. "
        "Cells count papers carrying each combination; Evaluation Type is "
        "multi-valued so row totals can exceed framing counts. Supports RQ1.3.}\n"
    )
    lines.append("\t\\label{tab:crosstab-framing-eval}\n")
    lines.append("\t\\renewcommand{\\arraystretch}{1.15}\n")
    lines.append(f"\t\\begin{{tabular}}{{{col_spec}}}\n")
    lines.append("\t\t\\toprule\n")
    header_cells = ["\\textbf{Framing}"] + [f"{{\\textbf{{{e}}}}}" for e in eval_order] + ["{\\textbf{n}}"]
    lines.append("\t\t" + " & ".join(header_cells) + " \\\\ \\addlinespace\n")
    lines.append("\t\t\\midrule\n")
    for fr in framing_order:
        row_cells = [fr]
        for ev in eval_order:
            row_cells.append(str(counts.get((fr, ev), 0)))
        row_cells.append(str(framing_totals.get(fr, 0)))
        lines.append("\t\t" + " & ".join(row_cells) + " \\\\\n")
    lines.append("\t\t\\midrule\n")
    total_row = ["\\textit{n}"] + [str(eval_totals.get(ev, 0)) for ev in eval_order] + [str(papers_counted)]
    lines.append("\t\t" + " & ".join(total_row) + " \\\\\n")
    lines.append("\t\t\\bottomrule\n")
    lines.append("\t\\end{tabular}\n")
    lines.append("\\end{table}\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")


# ---- Bootstrap: tables/lit-review/main-matrix.tex (tabularray longtblr) ----

# Column layout: (kind, header, colspec_Q_fragment, accessor_or_placeholder).
# Widths sum to ~17.6 cm; landscape usable ~22 cm, so ~4 cm slack for colseps.
MATRIX_LAYOUT = [
    ("cite",   "Paper",      "Q[l, wd=1.0cm]", None),
    ("auto",   "Framing",    "Q[l, wd=1.4cm]", "AppFraming"),
    ("auto",   "Eval",       "Q[l, wd=1.9cm]", "EvalType"),
    ("auto",   "Reuse",      "Q[c, wd=1.4cm]", "ReuseCombined"),
    ("auto",   "DataTech",   "Q[l, wd=1.4cm]", "DataTech"),
    ("auto",   "Proc",       "Q[l, wd=1.5cm]", "DataProc"),
    ("manual", "\\textmu C", "Q[l, wd=1.5cm]", None),
    ("manual", "Platform",   "Q[l, wd=1.5cm]", None),
    ("manual", "Interface",  "Q[l, wd=1.8cm]", None),
    ("manual", "Artifact",   "Q[l, wd=2.0cm]", None),
    ("manual", "Target",     "Q[l, wd=2.2cm]", None),
]


MATRIX_CAPTION = (
    "Curated paper matrix for the systematic literature review. AUTO columns "
    "(Framing through Proc) are generated from coded matrix cells; MANUAL "
    "columns ($\\mu$C through Target) are hand-written. Reuse column shows "
    "Hardware/Firmware/Analysis/Software rubric scores (0--4, see "
    "Table~\\ref{tab:coding-reusability}); PW = Previous Works, CoTS = "
    "commercial off-the-shelf, --- = N/A or uncoded. Framing: Hyp/Lit, Hypot, "
    "Adj, SecObs, PrimObs, Co, Co+. Eval: Bench, Ctrl, Demo, Wkshp, TCLtd, "
    "TCFull, FullS."
)


def bootstrap_matrix(
    ordered: list[tuple[str, str]],
    bibkey_to_doc: dict[str, int],
    out_path: Path,
) -> bool:
    """Write the main-matrix.tex skeleton as a tabularray longtblr. No-op if exists."""
    if out_path.exists():
        print(f"bootstrap skipped: {out_path.relative_to(REPO_ROOT)} already exists")
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)

    colspec = "\n\t\t".join(c[2] for c in MATRIX_LAYOUT)
    headers = " & ".join(c[1] for c in MATRIX_LAYOUT)
    ncols = len(MATRIX_LAYOUT)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append(
        f"% Main curated paper matrix (Chapter 2). Bootstrapped by\n"
        f"% lit-review/scripts/generate_matrix.py on {stamp}.\n"
        f"%\n"
        f"% Editing rules:\n"
        f"%   - AUTO cells (\\matFraming{{...}}, \\matEvalType{{...}}, ...) refresh from\n"
        f"%     the DB when you rerun the script. Do NOT hand-edit their values.\n"
        f"%   - MANUAL cells start as \\mTODO{{}} (renders '---'). Replace inline with\n"
        f"%     your chosen short text (e.g. `nRF52`, `mobile / React Native`).\n"
        f"%   - Reorder or prune rows by editing lit-review/coding/matrix-papers.txt\n"
        f"%     and rerunning the script -- note that removing a row from the list\n"
        f"%     does NOT remove it from this file. Rebootstrap to redo from scratch\n"
        f"%     (delete this file, then run with --bootstrap).\n"
        f"%   - Column widths are defined in MATRIX_LAYOUT (script). You can also\n"
        f"%     tune them in the colspec block below.\n\n"
    )
    lines.append("\\begin{landscape}\n")
    lines.append("\\sffamily\\footnotesize\n\n")
    # Caption lives outside the longtblr so it renders exactly once on the first
    # page. The longtblr's `head` template is overridden below so continuation
    # pages show only a short italic marker (no caption repeat).
    lines.append(f"\\captionof{{table}}{{{MATRIX_CAPTION}}}\n")
    lines.append("\\label{tab:main-matrix}\n\n")
    lines.append(
        "\\DefTblrTemplate{contfoot-text}{default}{\\emph{continued on next page}}\n"
    )
    lines.append(
        "\\DefTblrTemplate{head}{default}{%\n"
        "\t\\emph{Table~\\ref{tab:main-matrix} -- continued from previous page}\\\\[4pt]\n"
        "}\n"
    )
    lines.append(
        "\\DefTblrTemplate{firsthead}{default}{}  % no firsthead block; caption is above\n"
    )
    lines.append("\n")
    lines.append("\\begin{longtblr}[\n")
    lines.append("\tentry = none,\n")
    lines.append("]{\n")
    lines.append("\tcolspec = {\n")
    lines.append(f"\t\t{colspec}\n")
    lines.append("\t},\n")
    lines.append("\trowhead = 1,\n")
    lines.append("\trow{1} = {font=\\bfseries},\n")
    lines.append("\tcolsep = 4pt,\n")
    lines.append("\thlines = {0.2pt, gray!40},\n")
    lines.append("}\n")
    lines.append("\t\\toprule\n")
    lines.append(f"\t{headers} \\\\\n")
    lines.append("\t\\midrule\n\n")

    prev_group: str | None = None
    n_rows = 0
    for group, bibkey in ordered:
        if bibkey not in bibkey_to_doc:
            continue
        if group != prev_group:
            if prev_group is not None:
                lines.append("\t\\midrule\n")
            lines.append(
                f"\t\\SetCell[c={ncols}]{{l}} \\textit{{{group}}} \\\\\n"
            )
            prev_group = group

        lines.append(f"\t% ---- {bibkey} ----\n")
        for i, (kind, header, _, acc) in enumerate(MATRIX_LAYOUT):
            if kind == "cite":
                cell = f"\\cite{{{bibkey}}}"
            elif kind == "auto":
                cell = f"\\mat{acc}{{{bibkey}}}"
            else:
                cell = "\\mTODO{}"
            prefix = "\t\t  " if i > 0 else "\t"
            sep = " &" if i < len(MATRIX_LAYOUT) - 1 else " \\\\"
            lines.append(f"{prefix}{cell}{sep}  % {header}\n")
        lines.append("\n")
        n_rows += 1

    lines.append("\t\\bottomrule\n")
    lines.append("\\end{longtblr}\n\n")
    lines.append("\\end{landscape}\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"bootstrapped {out_path.relative_to(REPO_ROOT)} with {n_rows} rows")
    return True




# ---- Main ----

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Chapter 2 paper-matrix artifacts.")
    p.add_argument(
        "--bootstrap",
        action="store_true",
        help="Also emit tables/lit-review/main-matrix.tex (no-op if it exists).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not DB_PATH.exists():
        print(f"error: database not found at {DB_PATH}", file=sys.stderr)
        return 1

    conn = connect_ro(DB_PATH)
    try:
        papers = included_papers(conn)
        bibkey_to_doc = {bibkey: doc_id for doc_id, bibkey, _ in papers}

        # Seed the list file if missing.
        if not LIST_PATH.exists():
            seed_list_file(papers, LIST_PATH)
            print(f"seeded {LIST_PATH.relative_to(REPO_ROOT)} with {len(papers)} papers")

        ordered = load_list_file(LIST_PATH)

        n_defs, n_papers, n_warn = emit_cells(conn, ordered, bibkey_to_doc, CELLS_OUT)
        emit_crosstab(conn, ordered, bibkey_to_doc, CROSSTAB_OUT)

        if args.bootstrap:
            bootstrap_matrix(ordered, bibkey_to_doc, MATRIX_OUT)
    finally:
        conn.close()

    print(f"wrote {CELLS_OUT.relative_to(REPO_ROOT)}")
    print(f"  {n_defs} macro defs across {n_papers} papers ({len(AUTO_COLUMNS)} auto columns + \\matReuseMax)")
    if n_warn:
        print(f"  {n_warn} bibkeys in list file did not match Phase 3 included set (see warnings)")
    print(f"wrote {CROSSTAB_OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
