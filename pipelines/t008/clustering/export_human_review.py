"""Create a compact human-review CSV from T008 candidate clusters."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def run(args):
    source_dir = Path(args.clusters)
    output = Path(args.output)
    rows = []
    for path in sorted(source_dir.glob("clusters-*.ndjson")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            item = json.loads(line)
            rows.append({
                "cluster_id": item["cluster_id"],
                "product_category": item["product_category"],
                "candidate_group": item["candidate_group"],
                "suggested_label": item["suggested_label"],
                "review_count": item["review_count"],
                "product_count": item["product_count"],
                "center_topic_raw": item.get("center_topic_raw", ""),
                "center_evidence": item.get("center_evidence", ""),
                "top_topic_raw": " | ".join(
                    f"{x['topic_raw']} ({x['count']})" for x in item.get("top_topic_raw", [])
                ),
                "human_action": "",
                "final_taxonomy_label": "",
                "human_notes": "",
            })
    rows.sort(key=lambda x: (x["product_category"], x["candidate_group"], -x["review_count"]))
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
            "cluster_id","product_category","candidate_group","suggested_label","review_count",
            "product_count","center_topic_raw","center_evidence","top_topic_raw",
            "human_action","final_taxonomy_label","human_notes"
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"status": "ready", "rows": len(rows), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clusters", required=True)
    parser.add_argument("--output", required=True)
    run(parser.parse_args())
