"""Generate LLM prompts for every semantic block."""

from __future__ import annotations
import argparse, json
from pathlib import Path


def make_prompt(block: dict) -> str:
    lines = []
    for r in block["clusters"]:
        tops = "; ".join(str(x.get("topic_raw") or "") for x in (r.get("top_topic_raw") or [])[:8])
        lines.append(
            f"- {r['cluster_id']} | center={r.get('center_topic_raw')} | "
            f"reviews={r.get('review_count')} | products={r.get('product_count')} | "
            f"polarity={r.get('candidate_group')} | top_topics={tops} | "
            f"evidence={r.get('center_evidence')}"
        )

    example = {
        "product_category": block["product_category"],
        "block_id": block["block_id"],
        "local_themes": [
            {
                "local_theme_name": "Noise level",
                "member_cluster_ids": ["cluster_a", "cluster_b"],
                "definition": "Operating or fan noise produced by the product."
            }
        ]
    }
    return f"""You are consolidating one semantic workload block into LOCAL candidate themes.

IMPORTANT
This block is only part of the full category. Do NOT try to create the final global taxonomy.
A later global consolidation step will merge equivalent local themes from different blocks.

CATEGORY
{block['product_category']}

BLOCK
{block['block_id']}

RULES
1. Assign EVERY cluster_id exactly once.
2. Do not use polarity as a taxonomy axis.
3. Merge paraphrases/near-synonyms only when they express the same analytical dimension.
4. Keep dimensions separate when they support different analysis:
   speed != capacity != reliability != quality;
   noise != vibration;
   size != fit;
   taste != texture != shape.
5. Prefer concise noun-phrase names.
6. Do not discard clusters.
7. If a cluster is genuinely distinct, a local theme may contain only one cluster.
8. Return JSON only.

OUTPUT CONTRACT
{json.dumps(example, ensure_ascii=False, indent=2)}

CLUSTERS
""" + "\n".join(lines)


def run(args):
    block_dir = Path(args.block_dir)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in sorted(block_dir.glob("block-*.json")):
        block = json.loads(p.read_text(encoding="utf-8"))
        (out / f"{block['block_id']}.txt").write_text(make_prompt(block), encoding="utf-8")
        count += 1
    print(json.dumps({"status":"ready","prompt_count":count,"output":str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--block-dir", required=True)
    p.add_argument("--output", required=True)
    run(p.parse_args())
