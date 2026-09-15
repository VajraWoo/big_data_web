"""Generate an LLM-ready taxonomy consolidation prompt for one category packet.

This script does not call any model. It produces a prompt text file plus the exact
JSON output contract expected from an LLM or a human-assisted workflow.
"""

from __future__ import annotations
import argparse, json
from pathlib import Path

SCHEMA_EXAMPLE = {
  "product_category": "Ice Makers",
  "themes": [
    {
      "canonical_theme_name": "Ice production speed",
      "member_cluster_ids": ["abc123", "def456"],
      "rationale": "Both clusters describe how quickly ice is produced."
    }
  ]
}

def run(args):
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    clusters = packet["clusters"]

    cluster_lines = []
    for r in clusters:
        tops = "; ".join(x["topic_raw"] for x in r.get("top_topic_raw", [])[:8])
        cluster_lines.append(
            f"- {r['cluster_id']} | label={r.get('suggested_label')} | "
            f"center={r.get('center_topic_raw')} | reviews={r.get('review_count')} | "
            f"products={r.get('product_count')} | polarity={r.get('candidate_group')} | "
            f"top_topics={tops} | evidence={r.get('center_evidence')}"
        )

    prompt = f"""You are consolidating first-level semantic clusters into a category-level business taxonomy.

CATEGORY
{packet['product_category']}

TASK
Assign EVERY cluster below to exactly one canonical theme.

RULES
1. Do not use positive/negative/mixed/neutral as taxonomy categories.
2. Merge paraphrases and near-synonyms representing the same business concept.
3. Keep analytically distinct dimensions separate. For example:
   - speed != capacity
   - reliability != functionality
   - taste != size
   - noise != vibration
4. Prefer concise noun-phrase names such as "Noise level", "Installation ease", "Ice production speed".
5. Do not discard any cluster.
6. Avoid vague umbrella themes when more specific concepts are supported.
7. A canonical theme may contain one cluster if it is genuinely distinct.
8. Return JSON only.

OUTPUT CONTRACT
{json.dumps(SCHEMA_EXAMPLE, ensure_ascii=False, indent=2)}

VALIDATION REQUIREMENTS
- Every input cluster_id must appear exactly once across member_cluster_ids.
- Do not invent cluster_ids.
- canonical_theme_name must be non-empty.
- product_category must exactly equal "{packet['product_category']}".

CLUSTERS
""" + "\n".join(cluster_lines)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    print(json.dumps({
        "status": "ready",
        "category": packet["product_category"],
        "cluster_count": len(clusters),
        "output": str(out),
    }, ensure_ascii=False))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--packet", required=True)
    p.add_argument("--output", required=True)
    run(p.parse_args())
