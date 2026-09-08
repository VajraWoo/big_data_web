"""Validate a consolidated taxonomy JSON and materialize canonical IDs/mappings.

Expected LLM/human JSON:
{
  "product_category": "...",
  "themes": [
    {
      "canonical_theme_name": "...",
      "member_cluster_ids": ["..."],
      "rationale": "..."
    }
  ]
}

Outputs:
- taxonomy.ndjson
- cluster-to-taxonomy.ndjson
- validation.json
"""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def load_packet(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def load_decisions(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def run(args):
    packet = load_packet(args.packet)
    decisions = load_decisions(args.decisions)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    expected_category = packet["product_category"]
    if decisions.get("product_category") != expected_category:
        raise RuntimeError(
            f"category mismatch: expected {expected_category!r}, got {decisions.get('product_category')!r}"
        )

    valid_ids = {r["cluster_id"] for r in packet["clusters"]}
    seen = {}
    errors = []

    themes = decisions.get("themes")
    if not isinstance(themes, list) or not themes:
        raise RuntimeError("themes must be a non-empty list")

    for theme_index, theme in enumerate(themes):
        name = str(theme.get("canonical_theme_name") or "").strip()
        ids = theme.get("member_cluster_ids")
        if not name:
            errors.append(f"theme[{theme_index}] has empty canonical_theme_name")
        if not isinstance(ids, list) or not ids:
            errors.append(f"theme[{theme_index}] has no member_cluster_ids")
            continue
        for cid in ids:
            if cid not in valid_ids:
                errors.append(f"unknown cluster_id: {cid}")
            if cid in seen:
                errors.append(f"duplicate cluster_id: {cid}")
            seen[cid] = theme_index

    missing = sorted(valid_ids - set(seen))
    if missing:
        errors.append(f"missing cluster_ids: {len(missing)}")

    validation = {
        "status": "failed" if errors else "ready",
        "product_category": expected_category,
        "expected_cluster_count": len(valid_ids),
        "assigned_cluster_count": len(seen),
        "theme_count": len(themes),
        "errors": errors,
        "missing_cluster_ids_sample": missing[:20],
    }
    (output / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if errors:
        print(json.dumps(validation, ensure_ascii=False))
        raise RuntimeError("taxonomy validation failed")

    cluster_index = {r["cluster_id"]: r for r in packet["clusters"]}
    with (output / "taxonomy.ndjson").open("w", encoding="utf-8") as th, \
         (output / "cluster-to-taxonomy.ndjson").open("w", encoding="utf-8") as mh:
        for theme in themes:
            name = str(theme["canonical_theme_name"]).strip()
            key = f"{expected_category}|{name.lower()}"
            taxonomy_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
            member_ids = list(theme["member_cluster_ids"])
            review_sum = sum(int(cluster_index[cid].get("review_count") or 0) for cid in member_ids)
            product_sum_upper = sum(int(cluster_index[cid].get("product_count") or 0) for cid in member_ids)
            th.write(json.dumps({
                "taxonomy_id": taxonomy_id,
                "product_category": expected_category,
                "canonical_theme_name": name,
                "first_level_cluster_count": len(member_ids),
                "first_level_review_count_sum": review_sum,
                "first_level_product_count_sum_upper_bound": product_sum_upper,
                "rationale": theme.get("rationale"),
                "status": "human_review_required",
            }, ensure_ascii=False) + "\n")
            for cid in member_ids:
                mh.write(json.dumps({
                    "taxonomy_id": taxonomy_id,
                    "product_category": expected_category,
                    "canonical_theme_name": name,
                    "first_level_cluster_id": cid,
                }, ensure_ascii=False) + "\n")

    print(json.dumps(validation, ensure_ascii=False))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--packet", required=True)
    p.add_argument("--decisions", required=True)
    p.add_argument("--output", required=True)
    run(p.parse_args())
