"""Build semantic prompt blocks for a large T008 category.

This script is ONLY for workload partitioning. KMeans block membership is not a taxonomy
decision and is never published downstream.

Input:
  one category packet created by build_taxonomy_packets.py

Output:
  blocks/block-XXX.json
  block_manifest.json

Method:
  MiniLM representative embeddings + MiniBatchKMeans.
  Number of blocks = ceil(cluster_count / target_block_size).
"""

from __future__ import annotations
import argparse, json, math, re
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from sklearn.cluster import MiniBatchKMeans


def choose_device(req: str) -> str:
    if req != "auto":
        return req
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return "xpu"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def rep_text(row: dict) -> str:
    center = str(row.get("center_topic_raw") or "").strip()
    tops = []
    for x in (row.get("top_topic_raw") or [])[:8]:
        t = str(x.get("topic_raw") or "").strip()
        if t and t.lower() not in {z.lower() for z in tops}:
            tops.append(t)
    evidence = str(row.get("center_evidence") or "").strip()
    parts = ([center] if center else []) + tops + ([evidence] if evidence else [])
    out, seen = [], set()
    for p in parts:
        p = " ".join(p.split())
        if p and p.lower() not in seen:
            out.append(p); seen.add(p.lower())
    return " | ".join(out)


def run(args):
    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))
    rows = packet["clusters"]
    n = len(rows)
    k = max(1, math.ceil(n / args.target_block_size))
    device = choose_device(args.device)

    print(f"category={packet['product_category']} clusters={n} target_block_size={args.target_block_size} blocks={k}")
    print(f"loading MiniLM on {device}...", flush=True)
    model = SentenceTransformer(args.model_path, device=device, local_files_only=args.local_files_only)
    texts = [rep_text(r) for r in rows]
    emb = model.encode(
        texts, batch_size=args.batch_size, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True
    ).astype(np.float32, copy=False)

    km = MiniBatchKMeans(
        n_clusters=k,
        random_state=args.seed,
        batch_size=max(1024, args.target_block_size * 8),
        n_init="auto",
    )
    labels = km.fit_predict(emb)

    out = Path(args.output)
    block_dir = out / "blocks"
    block_dir.mkdir(parents=True, exist_ok=True)

    blocks = []
    assigned = set()
    for b in range(k):
        idx = np.where(labels == b)[0].tolist()
        # Sort by similarity to the block centroid so the most representative items appear first.
        centroid = km.cluster_centers_[b]
        centroid = centroid / max(float(np.linalg.norm(centroid)), 1e-12)
        idx.sort(key=lambda i: -float(emb[i] @ centroid))

        members = [rows[i] for i in idx]
        for r in members:
            cid = r["cluster_id"]
            if cid in assigned:
                raise RuntimeError(f"duplicate block assignment: {cid}")
            assigned.add(cid)

        block = {
            "product_category": packet["product_category"],
            "block_id": f"block-{b:03d}",
            "purpose": "prompt_partition_only_not_taxonomy",
            "cluster_count": len(members),
            "clusters": members,
        }
        path = block_dir / f"block-{b:03d}.json"
        path.write_text(json.dumps(block, ensure_ascii=False, indent=2), encoding="utf-8")
        blocks.append({"block_id": block["block_id"], "cluster_count": len(members), "path": str(path)})

    expected = {r["cluster_id"] for r in rows}
    if assigned != expected:
        raise RuntimeError(f"block coverage mismatch: assigned={len(assigned)} expected={len(expected)}")

    manifest = {
        "stage": "large_taxonomy_semantic_blocking",
        "status": "ready",
        "product_category": packet["product_category"],
        "cluster_count": n,
        "block_count": k,
        "target_block_size": args.target_block_size,
        "block_size_min": min(x["cluster_count"] for x in blocks),
        "block_size_max": max(x["cluster_count"] for x in blocks),
        "coverage_exact_once": True,
        "blocking_method": "MiniLM + MiniBatchKMeans (prompt partition only)",
        "blocks": blocks,
    }
    (out / "block_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--packet", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--model-path", required=True)
    p.add_argument("--device", choices=("auto","cpu","xpu","cuda"), default="auto")
    p.add_argument("--local-files-only", action="store_true")
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--target-block-size", type=int, default=100)
    p.add_argument("--seed", type=int, default=20260908)
    run(p.parse_args())
