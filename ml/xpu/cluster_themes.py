"""CPU Fast Community Detection for evaluation themes and improvement needs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sentence_transformers.util import community_detection


FACETS = (("evaluation", "positive"), ("evaluation", "negative"), ("improvement", None))


def _phrase(text: str, max_words: int = 12) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    phrase = " ".join(words[:max_words]).strip(" .,:;!?-\"")
    return phrase or text.strip()


def _theme_name(theme_type, sentiment, center_phrase, attribute):
    if not attribute:
        return center_phrase, "center_phrase"
    prefix = "Improve" if theme_type == "improvement" else (
        "Praise" if sentiment == "positive" else "Concern"
    )
    return f"{prefix} {attribute}: {center_phrase}", "template"


def _process_product(candidate_path, embedding_path, output, args):
    started = time.perf_counter()
    rows = [json.loads(line) for line in candidate_path.read_text(encoding="utf-8").splitlines() if line]
    embeddings = np.load(embedding_path, allow_pickle=False)
    if embeddings.shape != (len(rows), 384):
        raise RuntimeError(f"embedding shape mismatch for {candidate_path.name}: {embeddings.shape}")
    parent_asin = rows[0]["parent_asin"]
    suffix = candidate_path.stem.removeprefix("candidates-")
    theme_count = member_count = 0
    with (
        (output / f"themes-{suffix}.ndjson").open("w", encoding="utf-8", newline="\n") as theme_handle,
        (output / f"members-{suffix}.ndjson").open("w", encoding="utf-8", newline="\n") as member_handle,
        (output / f"facets-{suffix}.ndjson").open("w", encoding="utf-8", newline="\n") as facet_handle,
    ):
        for theme_type, sentiment in FACETS:
            indices = [i for i, row in enumerate(rows)
                       if row["theme_type"] == theme_type and row.get("sentiment") == sentiment]
            communities = community_detection(
                torch.from_numpy(embeddings[indices]), threshold=args.threshold,
                min_community_size=args.min_community_size,
                batch_size=args.community_batch_size, show_progress_bar=False,
            ) if len(indices) >= args.min_community_size else []
            accepted = [community for community in communities if len({
                rows[indices[i]]["review_id"] for i in community
            }) >= args.min_community_size]
            facet_theme_count = 0
            for community in accepted:
                global_indices = [indices[i] for i in community]
                distinct_reviews = {rows[i]["review_id"] for i in global_indices}
                vectors = embeddings[global_indices]
                centroid = vectors.mean(axis=0)
                centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
                similarities = vectors @ centroid
                center_position = int(np.argmax(similarities))
                center_index = global_indices[center_position]
                center_sentence = rows[center_index]["sentence_text"]
                center_phrase = _phrase(center_sentence)
                attribute_reviews = defaultdict(set)
                sources = set()
                for index in global_indices:
                    row = rows[index]
                    sources.update(row["sources"])
                    for attribute in row["attributes"]:
                        normalized = re.sub(r"\s+", " ", attribute).strip().lower()
                        if normalized:
                            attribute_reviews[normalized].add(row["review_id"])
                required = max(3, math.ceil(len(distinct_reviews) * 0.20))
                ranked = sorted(attribute_reviews.items(), key=lambda item: (-len(item[1]), item[0]))
                frequent_attribute = ranked[0][0] if ranked and len(ranked[0][1]) >= required else None
                name, naming_method = _theme_name(theme_type, sentiment, center_phrase, frequent_attribute)
                key = f"{parent_asin}|{theme_type}|{sentiment}|{rows[center_index]['candidate_id']}"
                theme_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
                best_by_review = {}
                for position, global_index in enumerate(global_indices):
                    row = rows[global_index]
                    similarity = float(similarities[position])
                    previous = best_by_review.get(row["review_id"])
                    if previous is None or similarity > previous[0]:
                        best_by_review[row["review_id"]] = (similarity, row)
                for review_id, (similarity, row) in sorted(best_by_review.items()):
                    member_handle.write(json.dumps({
                        "theme_id": theme_id, "candidate_id": row["candidate_id"],
                        "review_id": review_id, "parent_asin": parent_asin,
                        "theme_type": theme_type, "sentiment": sentiment,
                        "sources": row["sources"], "attributes": row["attributes"],
                        "evidence_sentence": row["sentence_text"],
                        "center_similarity": round(similarity, 8),
                    }, ensure_ascii=False) + "\n")
                    member_count += 1
                theme_handle.write(json.dumps({
                    "theme_id": theme_id, "parent_asin": parent_asin,
                    "theme_type": theme_type, "name": name, "sentiment": sentiment,
                    "sources": sorted(sources), "center_phrase": center_phrase,
                    "center_sentence": center_sentence, "frequent_attribute": frequent_attribute,
                    "naming_method": naming_method, "review_count": len(best_by_review),
                    "threshold": args.threshold, "min_community_reviews": args.min_community_size,
                    "clustering_method": "fast_community_detection",
                    "effective_min_similarity": round(float(similarities.min()), 8),
                }, ensure_ascii=False) + "\n")
                facet_theme_count += 1
                theme_count += 1
            facet_handle.write(json.dumps({
                "parent_asin": parent_asin, "theme_type": theme_type, "sentiment": sentiment,
                "status": "ready", "theme_count": facet_theme_count,
                "reason": None if facet_theme_count else "no_qualified_theme",
            }, ensure_ascii=False) + "\n")
    return {
        "status": "ready", "parent_asin": parent_asin, "theme_count": theme_count,
        "member_count": member_count, "facet_count": 3,
        "elapsed_seconds": round(time.perf_counter()-started, 3),
    }


def run(args):
    input_dir, embedding_dir, output = Path(args.input_dir), Path(args.embedding_dir), Path(args.output)
    embedding_status = json.loads((embedding_dir / "status.json").read_text(encoding="utf-8"))
    if embedding_status.get("status") != "ready":
        raise RuntimeError(f"theme embeddings are not complete: {embedding_status.get('status')}")
    output.mkdir(parents=True, exist_ok=True)
    root_path = output / "status.json"
    root = {
        "stage": "theme_clustering", "status": "processing", "device": "cpu",
        "algorithm": "sentence_transformers.util.community_detection",
        "threshold": args.threshold, "min_community_reviews": args.min_community_size,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    root_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")
    started = time.perf_counter()
    for candidates in sorted(input_dir.glob("candidates-*.ndjson")):
        suffix = candidates.stem.removeprefix("candidates-")
        status_path = output / f"status-{suffix}.json"
        if status_path.exists() and json.loads(status_path.read_text(encoding="utf-8")).get("status") == "ready":
            continue
        status = _process_product(candidates, embedding_dir / f"embeddings-{suffix}.npy", output, args)
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        root.update({"last_completed_product": suffix, "updated_at": datetime.now(timezone.utc).isoformat()})
        root_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")
    statuses = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("status-*.json")]
    root.update({
        "status": "ready", "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds_this_run": round(time.perf_counter()-started, 3),
        "product_count": len(statuses), "facet_count": sum(x["facet_count"] for x in statuses),
        "theme_count": sum(x["theme_count"] for x in statuses),
        "member_count": sum(x["member_count"] for x in statuses),
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
    run(parser.parse_args())
