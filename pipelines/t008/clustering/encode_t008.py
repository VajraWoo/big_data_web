"""Encode T008 category candidates with all-MiniLM-L6-v2.

Unlike the legacy script, device is configurable instead of hard-wired to Intel XPU.
Use --device auto to prefer XPU, then CUDA, then CPU.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


def _choose_device(requested: str) -> str:
    if requested != "auto":
        if requested == "xpu" and not torch.xpu.is_available():
            raise RuntimeError("requested XPU but torch.xpu.is_available() is false")
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("requested CUDA but torch.cuda.is_available() is false")
        return requested
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return "xpu"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _read_candidates(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def run(args: argparse.Namespace) -> None:
    input_dir = Path(args.input_dir)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    device = _choose_device(args.device)
    model = SentenceTransformer(
        args.model_path,
        device=device,
        local_files_only=args.local_files_only,
    )
    model.max_seq_length = args.max_length

    root = {
        "stage": "t008_embedding",
        "status": "processing",
        "device": device,
        "model_path": args.model_path,
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    status_path = output / "status.json"
    status_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")

    total_candidates = 0
    dimensions = None
    started = time.perf_counter()
    for source in sorted(input_dir.glob("candidates-*.ndjson")):
        suffix = source.stem.removeprefix("candidates-")
        target = output / f"embeddings-{suffix}.npy"
        item_status_path = output / f"status-{suffix}.json"

        if item_status_path.exists():
            previous = json.loads(item_status_path.read_text(encoding="utf-8"))
            if previous.get("status") == "ready" and target.exists():
                total_candidates += int(previous["candidate_count"])
                dimensions = previous.get("embedding_dimensions", dimensions)
                continue

        rows = _read_candidates(source)
        texts = [row["candidate_text"] for row in rows]
        item_started = time.perf_counter()
        if texts:
            embeddings = model.encode(
                texts,
                batch_size=args.batch_size,
                show_progress_bar=True,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ).astype(np.float32, copy=False)
        else:
            embeddings = np.empty((0, 384), dtype=np.float32)

        if embeddings.ndim != 2:
            raise RuntimeError(f"unexpected embedding rank for {source.name}: {embeddings.shape}")
        np.save(target, embeddings, allow_pickle=False)
        dimensions = int(embeddings.shape[1]) if embeddings.shape[0] else dimensions
        total_candidates += len(rows)

        item_status = {
            "status": "ready",
            "input_file": source.name,
            "candidate_count": len(rows),
            "embedding_rows": int(embeddings.shape[0]),
            "embedding_dimensions": int(embeddings.shape[1]) if embeddings.ndim == 2 else None,
            "elapsed_seconds": round(time.perf_counter() - item_started, 3),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        item_status_path.write_text(
            json.dumps(item_status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        root.update({
            "last_completed_category": suffix,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        status_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")

    root.update({
        "status": "ready",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds_this_run": round(time.perf_counter() - started, 3),
        "candidate_count": total_candidates,
        "embedding_dimensions": dimensions,
    })
    status_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(root, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--model-path",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Local model directory or Hugging Face model name.",
    )
    parser.add_argument("--device", choices=("auto", "cpu", "xpu", "cuda"), default="auto")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--local-files-only", action="store_true")
    run(parser.parse_args())
