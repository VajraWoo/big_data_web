"""Category-level Fast Community Detection for T008 candidate taxonomy discovery.

Important: output is a *candidate cluster set*, not a frozen taxonomy.
Final merge/split/name decisions remain a later human-review step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sentence_transformers.util import community_detection


def _read_candidates(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _center(rows: list[dict], embeddings: np.ndarray, global_indices: list[int]):
    vectors = embeddings[global_indices]
    centroid = vectors.mean(axis=0)
    centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
    similarities = vectors @ centroid
    pos = int(np.argmax(similarities))
    center_index = global_indices[pos]
    return center_index, similarities, centroid


def _top_topics(rows: list[dict], indices: list[int], limit: int = 10):
    counts = Counter(row_topic for i in indices if (row_topic := rows[i].get("topic_raw")))
    return [{"topic_raw": topic, "count": count} for topic, count in counts.most_common(limit)]


def run(args: argparse.Namespace) -> None:
    input_dir = Path(args.input_dir)
    embedding_dir = Path(args.embedding_dir)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    root = {
        "stage": "t008_category_clustering",
        "status": "processing",
        "algorithm": "sentence_transformers.util.community_detection",
        "threshold": args.threshold,
        "min_community_reviews": args.min_community_size,
        "group_by_polarity": not args.ignore_polarity,
        "note": "candidate clusters only; taxonomy semantics are not frozen here",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    root_path = output / "status.json"
    root_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")

    total_clusters = total_members = 0
    started = time.perf_counter()
    for candidate_path in sorted(input_dir.glob("candidates-*.ndjson")):
        suffix = candidate_path.stem.removeprefix("candidates-")
        rows = _read_candidates(candidate_path)
        embeddings = np.load(embedding_dir / f"embeddings-{suffix}.npy", allow_pickle=False)
        if embeddings.shape[0] != len(rows):
            raise RuntimeError(
                f"embedding row mismatch for {candidate_path.name}: {embeddings.shape[0]} != {len(rows)}"
            )
        if not rows:
            continue

        category = rows[0]["product_category"]
        cluster_path = output / f"clusters-{suffix}.ndjson"
        member_path = output / f"members-{suffix}.ndjson"
        category_status = {
            "status": "processing",
            "product_category": category,
            "candidate_count": len(rows),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        groups: dict[str, list[int]] = defaultdict(list)
        for i, row in enumerate(rows):
            group = "all" if args.ignore_polarity else row.get("polarity", "unknown")
            groups[group].append(i)

        category_clusters = category_members = 0
        with cluster_path.open("w", encoding="utf-8", newline="\n") as cluster_handle, \
             member_path.open("w", encoding="utf-8", newline="\n") as member_handle:
            for group_name, indices in sorted(groups.items()):
                if len(indices) < args.min_community_size:
                    continue

                local_embeddings = torch.from_numpy(embeddings[indices])
                communities = community_detection(
                    local_embeddings,
                    threshold=args.threshold,
                    min_community_size=args.min_community_size,
                    batch_size=args.community_batch_size,
                    show_progress_bar=False,
                )

                # Official utility counts candidates. Re-validate using distinct review_id,
                # matching the old project rule.
                accepted = []
                for community in communities:
                    distinct_reviews = {
                        rows[indices[local_i]]["review_id"] for local_i in community
                    }
                    if len(distinct_reviews) >= args.min_community_size:
                        accepted.append(community)

                for rank, community in enumerate(accepted, 1):
                    global_indices = [indices[local_i] for local_i in community]
                    center_index, similarities, _ = _center(rows, embeddings, global_indices)
                    center_row = rows[center_index]

                    # One member per review, keeping the candidate closest to this cluster centroid.
                    best_by_review = {}
                    for position, global_index in enumerate(global_indices):
                        row = rows[global_index]
                        similarity = float(similarities[position])
                        previous = best_by_review.get(row["review_id"])
                        if previous is None or similarity > previous[0]:
                            best_by_review[row["review_id"]] = (similarity, row)

                    product_count = len({row["parent_asin"] for _, row in best_by_review.values()})
                    key = (
                        f"{category}|{group_name}|{center_row['candidate_id']}|"
                        f"{args.threshold}|{args.min_community_size}"
                    )
                    cluster_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]

                    for review_id, (similarity, row) in sorted(best_by_review.items()):
                        member_handle.write(json.dumps({
                            "cluster_id": cluster_id,
                            "candidate_id": row["candidate_id"],
                            "review_id": review_id,
                            "parent_asin": row["parent_asin"],
                            "product_category": category,
                            "polarity": row.get("polarity"),
                            "topic_raw": row.get("topic_raw"),
                            "evidence": row.get("evidence"),
                            "center_similarity": round(similarity, 8),
                        }, ensure_ascii=False) + "\n")
                        category_members += 1
                        total_members += 1

                    cluster_handle.write(json.dumps({
                        "cluster_id": cluster_id,
                        "product_category": category,
                        "candidate_group": group_name,
                        "candidate_taxonomy_status": "needs_human_review",
                        "suggested_label": center_row.get("topic_raw") or center_row.get("candidate_text"),
                        "center_candidate_id": center_row["candidate_id"],
                        "center_topic_raw": center_row.get("topic_raw"),
                        "center_evidence": center_row.get("evidence"),
                        "review_count": len(best_by_review),
                        "product_count": product_count,
                        "candidate_count": len(global_indices),
                        "top_topic_raw": _top_topics(rows, global_indices),
                        "threshold": args.threshold,
                        "min_community_reviews": args.min_community_size,
                        "clustering_method": "fast_community_detection",
                        "effective_min_center_similarity": round(float(similarities.min()), 8),
                    }, ensure_ascii=False) + "\n")
                    category_clusters += 1
                    total_clusters += 1

        category_status.update({
            "status": "ready",
            "cluster_count": category_clusters,
            "member_count": category_members,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        (output / f"status-{suffix}.json").write_text(
            json.dumps(category_status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        root.update({
            "last_completed_category": category,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        root_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")

    root.update({
        "status": "ready",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds_this_run": round(time.perf_counter() - started, 3),
        "cluster_count": total_clusters,
        "member_count": total_members,
    })
    root_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(root, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--embedding-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--min-community-size", type=int, default=10)
    parser.add_argument("--community-batch-size", type=int, default=1024)
    parser.add_argument(
        "--ignore-polarity",
        action="store_true",
        help="Experimental: cluster positive/negative/neutral together. Default keeps them separate.",
    )
    run(parser.parse_args())
