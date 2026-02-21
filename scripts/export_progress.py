#!/usr/bin/env python3
"""Export literature review progress data from SQLite to JSON for visualization."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "lit_review.db"
OUT_PATH = Path(__file__).parent.parent / "docs" / "data.json"


def export(db_path: Path = DB_PATH, out_path: Path = OUT_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    data: dict = {}

    # --- Searches ---
    c.execute("SELECT s.id, s.source, COUNT(*) as count FROM document d JOIN search s ON d.search_id=s.id GROUP BY s.id")
    searches = [{"id": r["id"], "source": r["source"], "count": r["count"]} for r in c.fetchall()]
    data["searches"] = searches
    total_docs = sum(s["count"] for s in searches)
    data["total_documents"] = total_docs

    # --- Duplicates ---
    c.execute("SELECT COUNT(DISTINCT duplicate_group_id) FROM document WHERE duplicate_group_id IS NOT NULL")
    data["duplicate_groups"] = c.fetchone()[0]

    # --- Pass 1: Human decisions ---
    c.execute("""
        SELECT decision, COUNT(*) as count
        FROM pass_review WHERE pass_number=1 AND decision IS NOT NULL
        GROUP BY decision
    """)
    p1_human = {r["decision"]: r["count"] for r in c.fetchall()}
    p1_total_human = sum(p1_human.values())

    # --- Pass 1: LLM suggestions ---
    c.execute("""
        SELECT json_extract(llm_suggestion, '$.decision') as decision, COUNT(*) as count
        FROM pass_review WHERE pass_number=1 AND llm_suggestion IS NOT NULL
        GROUP BY json_extract(llm_suggestion, '$.decision')
    """)
    p1_llm = {r["decision"]: r["count"] for r in c.fetchall()}
    p1_total_llm = sum(p1_llm.values())

    # Pass 1 LLM agreement (where both human and LLM decided)
    c.execute("""
        SELECT COUNT(*) FROM pass_review
        WHERE pass_number=1 AND decision IS NOT NULL AND llm_suggestion IS NOT NULL
        AND decision = json_extract(llm_suggestion, '$.decision')
    """)
    p1_agree = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM pass_review
        WHERE pass_number=1 AND decision IS NOT NULL AND llm_suggestion IS NOT NULL
    """)
    p1_both = c.fetchone()[0]

    data["pass1"] = {
        "human": p1_human,
        "human_total": p1_total_human,
        "llm": p1_llm,
        "llm_total": p1_total_llm,
        "agreement": p1_agree,
        "agreement_total": p1_both,
        "agreement_pct": round(p1_agree / p1_both * 100, 1) if p1_both > 0 else 0,
        "pending_human": total_docs - p1_total_human,
    }

    # --- Pass 2: eligible ---
    p2_eligible = p1_human.get("include", 0) + p1_human.get("uncertain", 0)

    # --- Pass 2: Human decisions ---
    c.execute("""
        SELECT decision, COUNT(*) as count
        FROM pass_review WHERE pass_number=2 AND decision IS NOT NULL
        GROUP BY decision
    """)
    p2_human = {r["decision"]: r["count"] for r in c.fetchall()}
    p2_total_human = sum(p2_human.values())

    # --- Pass 2: LLM suggestions ---
    c.execute("""
        SELECT json_extract(llm_suggestion, '$.decision') as decision, COUNT(*) as count
        FROM pass_review WHERE pass_number=2 AND llm_suggestion IS NOT NULL
        GROUP BY json_extract(llm_suggestion, '$.decision')
    """)
    p2_llm = {r["decision"]: r["count"] for r in c.fetchall()}
    p2_total_llm = sum(p2_llm.values())

    # Pass 2 LLM agreement
    c.execute("""
        SELECT COUNT(*) FROM pass_review
        WHERE pass_number=2 AND decision IS NOT NULL AND llm_suggestion IS NOT NULL
        AND decision = json_extract(llm_suggestion, '$.decision')
    """)
    p2_agree = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM pass_review
        WHERE pass_number=2 AND decision IS NOT NULL AND llm_suggestion IS NOT NULL
    """)
    p2_both = c.fetchone()[0]

    data["pass2"] = {
        "eligible": p2_eligible,
        "human": p2_human,
        "human_total": p2_total_human,
        "llm": p2_llm,
        "llm_total": p2_total_llm,
        "agreement": p2_agree,
        "agreement_total": p2_both,
        "agreement_pct": round(p2_agree / p2_both * 100, 1) if p2_both > 0 else 0,
        "pending_human": p2_eligible - p2_total_human,
    }

    # --- Exclusion codes ---
    c.execute("""
        SELECT ec.code, ec.description, pr.pass_number, COUNT(*) as count
        FROM pass_review_exclusion_code prec
        JOIN exclusion_code ec ON ec.id=prec.exclusion_code_id
        JOIN pass_review pr ON pr.id=prec.pass_review_id
        WHERE pr.decision IS NOT NULL
        GROUP BY ec.code, pr.pass_number
        ORDER BY ec.code, pr.pass_number
    """)
    exclusion_codes: dict[str, dict] = {}
    for r in c.fetchall():
        code = r["code"]
        if code not in exclusion_codes:
            exclusion_codes[code] = {"code": code, "description": r["description"], "pass1": 0, "pass2": 0}
        if r["pass_number"] == 1:
            exclusion_codes[code]["pass1"] = r["count"]
        else:
            exclusion_codes[code]["pass2"] = r["count"]
    data["exclusion_codes"] = list(exclusion_codes.values())

    # --- Related ---
    c.execute("SELECT COUNT(*) FROM document WHERE related=1")
    data["related_count"] = c.fetchone()[0]

    # --- Per-search breakdown for pass 1 ---
    search_breakdown = []
    for s in searches:
        c.execute("""
            SELECT pr.decision, COUNT(*) as count
            FROM pass_review pr
            JOIN document d ON d.id=pr.document_id
            WHERE d.search_id=? AND pr.pass_number=1 AND pr.decision IS NOT NULL
            GROUP BY pr.decision
        """, (s["id"],))
        decisions = {r["decision"]: r["count"] for r in c.fetchall()}
        search_breakdown.append({
            "source": s["source"],
            "total": s["count"],
            "include": decisions.get("include", 0),
            "exclude": decisions.get("exclude", 0),
            "uncertain": decisions.get("uncertain", 0),
        })
    data["search_breakdown"] = search_breakdown

    # --- Sankey data (human decisions only) ---
    # Nodes: All Papers → Pass 1 → Include/Exclude/Uncertain → Pass 2 → Include/Exclude/Uncertain
    sankey_nodes = [
        {"id": "all", "label": f"All Papers ({total_docs})"},
        {"id": "p1_include", "label": f"Pass 1 Include ({p1_human.get('include', 0)})"},
        {"id": "p1_exclude", "label": f"Pass 1 Exclude ({p1_human.get('exclude', 0)})"},
        {"id": "p1_uncertain", "label": f"Pass 1 Uncertain ({p1_human.get('uncertain', 0)})"},
    ]

    sankey_links = [
        {"source": "all", "target": "p1_include", "value": p1_human.get("include", 0)},
        {"source": "all", "target": "p1_exclude", "value": p1_human.get("exclude", 0)},
    ]
    if p1_human.get("uncertain", 0) > 0:
        sankey_links.append({"source": "all", "target": "p1_uncertain", "value": p1_human.get("uncertain", 0)})

    p1_pending = total_docs - p1_total_human
    if p1_pending > 0:
        sankey_nodes.append({"id": "p1_pending", "label": f"Pass 1 Pending ({p1_pending})"})
        sankey_links.append({"source": "all", "target": "p1_pending", "value": p1_pending})

    # Pass 2 nodes
    if p2_total_human > 0 or p2_eligible > 0:
        sankey_nodes.append({"id": "p2_include", "label": f"Pass 2 Include ({p2_human.get('include', 0)})"})
        sankey_nodes.append({"id": "p2_exclude", "label": f"Pass 2 Exclude ({p2_human.get('exclude', 0)})"})

        if p2_human.get("include", 0) > 0:
            sankey_links.append({"source": "p1_include", "target": "p2_include", "value": p2_human.get("include", 0)})
        if p2_human.get("exclude", 0) > 0:
            sankey_links.append({"source": "p1_include", "target": "p2_exclude", "value": p2_human.get("exclude", 0)})
        if p2_human.get("uncertain", 0) > 0:
            sankey_nodes.append({"id": "p2_uncertain", "label": f"Pass 2 Uncertain ({p2_human.get('uncertain', 0)})"})
            sankey_links.append({"source": "p1_include", "target": "p2_uncertain", "value": p2_human.get("uncertain", 0)})

        # Uncertain from pass 1 also flows to pass 2
        # Count how many p1_uncertain have p2 decisions
        c.execute("""
            SELECT pr2.decision, COUNT(*) FROM pass_review pr1
            JOIN pass_review pr2 ON pr2.document_id=pr1.document_id AND pr2.pass_number=2
            WHERE pr1.pass_number=1 AND pr1.decision='uncertain' AND pr2.decision IS NOT NULL
            GROUP BY pr2.decision
        """)
        uncertain_to_p2 = {r[0]: r[1] for r in c.fetchall()}
        for dec, count in uncertain_to_p2.items():
            target = f"p2_{dec}"
            sankey_links.append({"source": "p1_uncertain", "target": target, "value": count})

        # Pending pass 2 human review
        p2_pending = p2_eligible - p2_total_human
        if p2_pending > 0:
            sankey_nodes.append({"id": "p2_pending", "label": f"Pass 2 Pending ({p2_pending})"})
            # Split pending between include and uncertain sources
            c.execute("""
                SELECT pr1.decision, COUNT(*) FROM pass_review pr1
                LEFT JOIN pass_review pr2 ON pr2.document_id=pr1.document_id AND pr2.pass_number=2 AND pr2.decision IS NOT NULL
                WHERE pr1.pass_number=1 AND pr1.decision IN ('include', 'uncertain') AND pr2.id IS NULL
                GROUP BY pr1.decision
            """)
            pending_sources = {r[0]: r[1] for r in c.fetchall()}
            for src, count in pending_sources.items():
                sankey_links.append({"source": f"p1_{src}", "target": "p2_pending", "value": count})

    data["sankey"] = {"nodes": sankey_nodes, "links": sankey_links}

    # --- LLM model info ---
    c.execute("SELECT DISTINCT model FROM llm_request_log WHERE model IS NOT NULL")
    data["llm_models"] = [r[0] for r in c.fetchall()]

    c.execute("""
        SELECT pass_number, AVG(response_time_ms) as avg_ms, COUNT(*) as count
        FROM llm_request_log
        GROUP BY pass_number
    """)
    data["llm_performance"] = [
        {"pass": r["pass_number"], "avg_response_ms": round(r["avg_ms"] or 0), "count": r["count"]}
        for r in c.fetchall()
    ]

    conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Exported to {out_path} ({len(json.dumps(data))} bytes)")
    return data


if __name__ == "__main__":
    export()
