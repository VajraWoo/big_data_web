"""Build compact category-level packets from first-level T008 clusters.

Input:  data/gold/t008-clusters-20260908-v2/clusters-*.ndjson
Output:
  - packets/<category>.json
  - taxonomy_review_seed.csv
  - manifest.json

The first-level clusters are treated as atomic high-precision semantic units.
Polarity is metadata, not a taxonomy partition.
"""

from __future__ import annotations
import argparse, csv, json, re
from collections import Counter
from pathlib import Path

def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower() or "unknown"

def read_ndjson(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)

def compact_cluster(row: dict) -> dict:
    top_topics = []
    for x in (row.get("top_topic_raw") or [])[:12]:
        topic = str(x.get("topic_raw") or "").strip()
        if topic:
            top_topics.append({
                "topic_raw": topic,
                "count": int(x.get("count") or 0),
            })
    return {
        "cluster_id": row["cluster_id"],
        "candidate_group": row.get("candidate_group"),
        "suggested_label": row.get("suggested_label"),
        "center_topic_raw": row.get("center_topic_raw"),
        "center_evidence": row.get("center_evidence"),
        "review_count": int(row.get("review_count") or 0),
        "product_count": int(row.get("product_count") or 0),
        "top_topic_raw": top_topics,
    }

def run(args):
    input_dir = Path(args.input_dir)
    output = Path(args.output)
    packet_dir = output / "packets"
    packet_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "stage": "t008_taxonomy_consolidation_packets",
        "status": "ready",
        "categories": {},
        "first_level_cluster_count": 0,
    }
    csv_rows = []

    for path in sorted(input_dir.glob("clusters-*.ndjson")):
        rows = list(read_ndjson(path))
        if not rows:
            continue
        category = rows[0]["product_category"]
        compact = [compact_cluster(r) for r in rows]
        compact.sort(key=lambda r: (-r["review_count"], r["cluster_id"]))

        packet = {
            "product_category": category,
            "instructions": {
                "goal": "Create a coherent category-level business taxonomy by assigning every first-level cluster to exactly one canonical theme.",
                "rules": [
                    "Do not use polarity as a taxonomy axis; positive/negative/mixed/neutral are metadata.",
                    "Merge paraphrases and near-synonyms that express the same business concept.",
                    "Keep distinct dimensions separate when they support different analysis, e.g. speed vs capacity vs reliability vs quality.",
                    "Prefer concise noun-phrase theme names.",
                    "Do not discard clusters.",
                    "If two concepts are related but analytically distinct, keep them separate rather than using a vague umbrella.",
                ],
            },
            "clusters": compact,
        }
        packet_path = packet_dir / f"{slug(category)}.json"
        packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

        pol = Counter(str(r.get("candidate_group") or "unknown") for r in rows)
        manifest["categories"][category] = {
            "cluster_count": len(rows),
            "packet": str(packet_path),
            "polarity_group_counts": dict(sorted(pol.items())),
        }
        manifest["first_level_cluster_count"] += len(rows)

        for r in compact:
            csv_rows.append({
                "product_category": category,
                "cluster_id": r["cluster_id"],
                "candidate_group": r["candidate_group"],
                "suggested_label": r["suggested_label"],
                "center_topic_raw": r["center_topic_raw"],
                "review_count": r["review_count"],
                "product_count": r["product_count"],
                "top_topic_raw": " | ".join(
                    f"{x['topic_raw']} ({x['count']})" for x in r["top_topic_raw"]
                ),
                "canonical_theme_name": "",
                "review_status": "",
                "notes": "",
            })

    with (output / "taxonomy_review_seed.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "product_category","cluster_id","candidate_group","suggested_label",
            "center_topic_raw","review_count","product_count","top_topic_raw",
            "canonical_theme_name","review_status","notes"
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(csv_rows)

    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output", required=True)
    run(p.parse_args())
