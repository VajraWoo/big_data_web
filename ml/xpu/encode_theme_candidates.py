"""Encode per-product theme candidates with locked MiniLM on Intel Arc XPU."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import torch
from sentence_transformers import SentenceTransformer


MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def write_status(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args):
    if not torch.xpu.is_available():
        raise RuntimeError("Intel XPU is unavailable; CPU fallback is forbidden")
    device_name = torch.xpu.get_device_name(0)
    if "intel" not in device_name.lower() or "arc" not in device_name.lower():
        raise RuntimeError(f"unexpected XPU device: {device_name}")
    model = SentenceTransformer(args.model_path, device="xpu", local_files_only=True)
    if next(model.parameters()).device.type != "xpu":
        raise RuntimeError("MiniLM is not on XPU; CPU fallback is forbidden")
    model.max_seq_length = args.max_length
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    root_path = output / "status.json"
    root = {
        "stage": "theme_embedding", "status": "processing", "device": device_name,
        "model_revision": MODEL_REVISION, "batch_size": args.batch_size,
        "max_length": args.max_length, "started_at": datetime.now(timezone.utc).isoformat(),
    }
    write_status(root_path, root)
    started = time.perf_counter()
    for source in sorted(Path(args.input_dir).glob("candidates-*.ndjson")):
        suffix = source.stem.removeprefix("candidates-")
        status_path = output / f"status-{suffix}.json"
        if status_path.exists() and json.loads(status_path.read_text(encoding="utf-8")).get("status") == "ready":
            continue
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
        item_started = time.perf_counter()
        embeddings = model.encode(
            [row["sentence_text"] for row in rows], batch_size=args.batch_size,
            show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True,
        ).astype(np.float32, copy=False)
        np.save(output / f"embeddings-{suffix}.npy", embeddings, allow_pickle=False)
        status = {
            "status": "ready", "input_file": source.name, "candidate_count": len(rows),
            "embedding_rows": int(embeddings.shape[0]), "embedding_dimensions": int(embeddings.shape[1]),
            "elapsed_seconds": round(time.perf_counter()-item_started, 3),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        write_status(status_path, status)
        root.update({"last_completed_product": suffix, "updated_at": datetime.now(timezone.utc).isoformat()})
        write_status(root_path, root)
    statuses = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("status-*.json")]
    root.update({
        "status": "ready", "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds_this_run": round(time.perf_counter()-started, 3),
        "product_count": len(statuses),
        "candidate_count": sum(item["candidate_count"] for item in statuses),
        "xpu_peak_allocated_bytes": int(torch.xpu.max_memory_allocated()),
        "xpu_peak_reserved_bytes": int(torch.xpu.max_memory_reserved()),
        "process_peak_working_set_bytes": int(psutil.Process().memory_info().peak_wset),
    })
    write_status(root_path, root)
    print(json.dumps(root, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-length", type=int, default=256)
    run(parser.parse_args())
