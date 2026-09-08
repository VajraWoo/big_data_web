from __future__ import annotations
import argparse, csv, json, random
from collections import defaultdict
from pathlib import Path

def read_ndjson(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

def load_members(mapping_path):
    by_tax = defaultdict(list)
    for row in read_ndjson(mapping_path):
        by_tax[row["taxonomy_candidate_id"]].append(row)
    return by_tax

def load_first_level_clusters(cluster_dir):
    by_id = {}
    for p in sorted(Path(cluster_dir).glob("clusters-*.ndjson")):
        for row in read_ndjson(p):
            by_id[row["cluster_id"]] = row
    return by_id

def cluster_summary(row):
    top = " | ".join(
        f"{x.get('topic_raw','')} ({x.get('count',0)})"
        for x in (row.get("top_topic_raw") or [])[:10]
    )
    return {
        "first_level_cluster_id": row["cluster_id"],
        "candidate_group": row.get("candidate_group", ""),
        "suggested_label": row.get("suggested_label", ""),
        "center_topic_raw": row.get("center_topic_raw", ""),
        "center_evidence": row.get("center_evidence", ""),
        "review_count": row.get("review_count", 0),
        "product_count": row.get("product_count", 0),
        "top_topic_raw": top,
    }

def run(args):
    taxonomy = read_ndjson(args.taxonomy)
    members = load_members(args.mapping)
    first = load_first_level_clusters(args.first_level_dir)

    by_cat = defaultdict(list)
    for row in taxonomy:
        by_cat[row["product_category"]].append(row)

    rng = random.Random(args.seed)
    out_rows = []

    for category, rows in sorted(by_cat.items()):
        merged = [r for r in rows if int(r.get("first_level_cluster_count", 1)) > 1]
        merged.sort(key=lambda r: (-int(r.get("first_level_cluster_count", 1)),
                                   -int(r.get("first_level_review_count_sum", 0) or 0),
                                   r["taxonomy_candidate_id"]))
        selected_merged = merged[:args.top_merged_per_category]

        singletons = [r for r in rows if int(r.get("first_level_cluster_count", 1)) == 1]
        # Prefer larger first-level review-count singletons; then add reproducible random examples.
        singleton_scored = []
        for r in singletons:
            mids = members.get(r["taxonomy_candidate_id"], [])
            review_count = 0
            if mids:
                fl = first.get(mids[0]["first_level_cluster_id"])
                if fl:
                    review_count = int(fl.get("review_count", 0) or 0)
            singleton_scored.append((review_count, r))
        singleton_scored.sort(key=lambda x: (-x[0], x[1]["taxonomy_candidate_id"]))
        high_singletons = [r for _, r in singleton_scored[:args.top_singletons_per_category]]
        remaining = [r for _, r in singleton_scored[args.top_singletons_per_category:]]
        rng.shuffle(remaining)
        random_singletons = remaining[:args.random_singletons_per_category]

        chosen = [("merged_top", r) for r in selected_merged]
        chosen += [("singleton_high_review", r) for r in high_singletons]
        chosen += [("singleton_random", r) for r in random_singletons]

        for audit_type, tax in chosen:
            tax_id = tax["taxonomy_candidate_id"]
            mapped = members.get(tax_id, [])
            mapped_sorted = sorted(
                mapped,
                key=lambda m: (-float(m.get("taxonomy_center_similarity", 0.0)),
                               m["first_level_cluster_id"])
            )
            fl_rows = []
            for m in mapped_sorted:
                fl = first.get(m["first_level_cluster_id"])
                if fl:
                    fl_rows.append(cluster_summary(fl))

            # Keep enough detail for review, but avoid making a gigantic CSV cell.
            sample = fl_rows[:args.max_first_level_examples]
            member_labels = " || ".join(
                f"[{x['candidate_group']}] {x['suggested_label']}"
                for x in sample
            )
            member_topics = " || ".join(
                f"{x['center_topic_raw']} :: {x['top_topic_raw']}"
                for x in sample
            )
            member_evidence = " || ".join(
                x["center_evidence"] for x in sample if x["center_evidence"]
            )

            out_rows.append({
                "audit_type": audit_type,
                "product_category": category,
                "taxonomy_candidate_id": tax_id,
                "taxonomy_suggested_label": tax.get("suggested_label", ""),
                "first_level_cluster_count": tax.get("first_level_cluster_count", 1),
                "is_singleton": tax.get("is_singleton", False),
                "polarity_group_counts": json.dumps(tax.get("polarity_group_counts", {}), ensure_ascii=False),
                "top_topics_weighted": " | ".join(
                    f"{x.get('topic_raw','')} ({x.get('weight',0)})"
                    for x in (tax.get("top_topics_weighted") or [])[:12]
                ),
                "member_labels": member_labels,
                "member_topics": member_topics,
                "member_center_evidence": member_evidence,
                "human_judgment": "",
                "suggested_action": "",
                "final_taxonomy_label": "",
                "notes": "",
            })

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "audit_type","product_category","taxonomy_candidate_id","taxonomy_suggested_label",
        "first_level_cluster_count","is_singleton","polarity_group_counts","top_topics_weighted",
        "member_labels","member_topics","member_center_evidence",
        "human_judgment","suggested_action","final_taxonomy_label","notes"
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    print(json.dumps({
        "status":"ready",
        "rows":len(out_rows),
        "categories":len(by_cat),
        "top_merged_per_category":args.top_merged_per_category,
        "top_singletons_per_category":args.top_singletons_per_category,
        "random_singletons_per_category":args.random_singletons_per_category,
        "output":str(output)
    }, ensure_ascii=False))

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--taxonomy", required=True)
    p.add_argument("--mapping", required=True)
    p.add_argument("--first-level-dir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--top-merged-per-category", type=int, default=10)
    p.add_argument("--top-singletons-per-category", type=int, default=10)
    p.add_argument("--random-singletons-per-category", type=int, default=5)
    p.add_argument("--max-first-level-examples", type=int, default=20)
    p.add_argument("--seed", type=int, default=20260908)
    run(p.parse_args())
