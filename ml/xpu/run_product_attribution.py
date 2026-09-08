"""Resumable current-product attribution for negative ABSA evidence on Intel XPU."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


MODEL_REVISION = "b95119ce93d3e065de6214e38cd4a97b0f2f2c6d"
HYPOTHESIS_TEMPLATE = "The review sentence describes a problem with the reviewed product: {title}"
DECISION_RULE = "entailment > neutral AND entailment > contradiction"
CLASSIFICATION_REVISION = "current-product-attribution-v1"


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _infer(tokenizer, model, rows, args, label_ids):
    hypotheses = [HYPOTHESIS_TEMPLATE.format(title=row["product_title"]) for row in rows]
    encoded = tokenizer(
        [row["sentence_text"] for row in rows], hypotheses, padding=False,
        truncation="only_first", max_length=args.max_length, stride=args.stride,
        return_overflowing_tokens=True,
    )
    mapping = encoded.pop("overflow_to_sample_mapping")
    features = [{key: encoded[key][i] for key in encoded} for i in range(len(encoded["input_ids"]))]
    best = {}
    for start in range(0, len(features), args.batch_size):
        batch = tokenizer.pad(features[start:start+args.batch_size], padding=True, return_tensors="pt")
        batch = {key: value.to("xpu") for key, value in batch.items()}
        with torch.inference_mode():
            probabilities = torch.softmax(model(**batch).logits.float(), dim=-1).cpu()
        for local_index in range(len(probabilities)):
            feature_index = start + local_index
            sample_index = int(mapping[feature_index])
            scores = {name: float(probabilities[local_index, label_ids[name]])
                      for name in ("entailment", "neutral", "contradiction")}
            margin = scores["entailment"] - max(scores["neutral"], scores["contradiction"])
            if sample_index not in best or margin > best[sample_index][0]:
                best[sample_index] = (margin, scores)
    return {index: value[1] for index, value in best.items()}


def _process(path, output, tokenizer, model, args, labels):
    started = time.perf_counter()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    target = output / path.name.replace("input-", "decisions-")
    accepted = rejected = failed = 0
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for start in range(0, len(rows), args.evidence_batch_size):
            block = rows[start:start+args.evidence_batch_size]
            try:
                scores_by_index = _infer(tokenizer, model, block, args, labels)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                for row in block:
                    handle.write(json.dumps({
                        **row, "processing_status": "failed", "error": error,
                        "model_revision": MODEL_REVISION,
                        "classification_revision": CLASSIFICATION_REVISION,
                    }, ensure_ascii=False) + "\n")
                    failed += 1
                continue
            for index, row in enumerate(block):
                scores = scores_by_index[index]
                is_current = scores["entailment"] > scores["neutral"] and scores["entailment"] > scores["contradiction"]
                handle.write(json.dumps({
                    **row, **{key: round(value, 8) for key, value in scores.items()},
                    "is_current_product_problem": is_current,
                    "processing_status": "attributed" if is_current else "not_attributed",
                    "error": None, "model_revision": MODEL_REVISION,
                    "decision_rule": DECISION_RULE,
                    "classification_revision": CLASSIFICATION_REVISION,
                }, ensure_ascii=False) + "\n")
                if is_current:
                    accepted += 1
                else:
                    rejected += 1
    return {
        "status": "ready" if failed == 0 else "completed_with_failures",
        "input_count": len(rows), "attributed_count": accepted,
        "not_attributed_count": rejected, "failed_count": failed,
        "elapsed_seconds": round(time.perf_counter()-started, 3),
    }


def run(args):
    if not torch.xpu.is_available():
        raise RuntimeError("Intel XPU is unavailable; CPU fallback is forbidden")
    device = torch.xpu.get_device_name(0)
    if "intel" not in device.lower() or "arc" not in device.lower():
        raise RuntimeError(f"unexpected XPU device: {device}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_path, local_files_only=True)
    model.eval().to("xpu")
    if next(model.parameters()).device.type != "xpu":
        raise RuntimeError("attribution model is not on XPU; CPU fallback is forbidden")
    labels = {str(value).lower(): int(key) for key, value in model.config.id2label.items()}
    if set(labels) != {"entailment", "neutral", "contradiction"}:
        raise RuntimeError(f"unexpected labels: {labels}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    root_path = output / "status.json"
    root = {
        "stage": "current_product_attribution", "status": "processing",
        "device": device, "model_revision": MODEL_REVISION,
        "hypothesis_template": HYPOTHESIS_TEMPLATE, "decision_rule": DECISION_RULE,
        "classification_revision": CLASSIFICATION_REVISION,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(root_path, root)
    started = time.perf_counter()
    for source in sorted(Path(args.input_dir).glob("input-*.ndjson")):
        status_path = output / source.name.replace("input-", "status-").replace(".ndjson", ".json")
        if status_path.exists() and json.loads(status_path.read_text(encoding="utf-8")).get("status") == "ready":
            continue
        status = _process(source, output, tokenizer, model, args, labels)
        status.update({"input_file": source.name, "finished_at": datetime.now(timezone.utc).isoformat()})
        _write(status_path, status)
        root.update({"last_completed_shard": source.name, "updated_at": datetime.now(timezone.utc).isoformat()})
        _write(root_path, root)
    statuses = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(output.glob("status-*.json"))]
    totals = {key: sum(item[key] for item in statuses) for key in
              ("input_count", "attributed_count", "not_attributed_count", "failed_count")}
    root.update({
        "status": "ready" if totals["failed_count"] == 0 else "completed_with_failures",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds_this_run": round(time.perf_counter()-started, 3),
        "shard_count": len(statuses), **totals,
        "xpu_peak_allocated_bytes": int(torch.xpu.max_memory_allocated()),
        "xpu_peak_reserved_bytes": int(torch.xpu.max_memory_reserved()),
        "process_peak_working_set_bytes": int(psutil.Process().memory_info().peak_wset),
    })
    _write(root_path, root)
    print(json.dumps(root, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--evidence-batch-size", type=int, default=256)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--stride", type=int, default=32)
    run(parser.parse_args())
