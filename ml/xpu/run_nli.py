"""Resumable explicit-suggestion NLI inference on Intel Arc XPU."""

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
HYPOTHESIS = "The reviewer suggests a change, addition, or improvement to the product."
DECISION_RULE = "entailment > neutral AND entailment > contradiction"
CLASSIFICATION_REVISION = "explicit-suggestion-rule-v2"


def _write_status(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_xpu() -> str:
    if not torch.xpu.is_available():
        raise RuntimeError("Intel XPU is unavailable; CPU fallback is forbidden")
    name = torch.xpu.get_device_name(0)
    if "intel" not in name.lower() or "arc" not in name.lower():
        raise RuntimeError(f"unexpected XPU device: {name}")
    return name


def _infer_block(tokenizer, model, rows, args, label_ids):
    encoded = tokenizer(
        [str(row["sentence_text"]) for row in rows],
        [HYPOTHESIS] * len(rows),
        padding=False,
        truncation="only_first",
        max_length=args.max_length,
        stride=args.stride,
        return_overflowing_tokens=True,
    )
    sample_mapping = encoded.pop("overflow_to_sample_mapping")
    features = [
        {key: encoded[key][index] for key in encoded.keys()}
        for index in range(len(encoded["input_ids"]))
    ]
    best: dict[int, dict[str, float]] = {}
    for start in range(0, len(features), args.batch_size):
        feature_batch = features[start : start + args.batch_size]
        tensors = tokenizer.pad(feature_batch, padding=True, return_tensors="pt")
        tensors = {key: value.to("xpu") for key, value in tensors.items()}
        with torch.inference_mode():
            probabilities = torch.softmax(model(**tensors).logits.float(), dim=-1).cpu()
        for local_index in range(len(feature_batch)):
            feature_index = start + local_index
            sample_index = int(sample_mapping[feature_index])
            scores = {
                "entailment": float(probabilities[local_index, label_ids["entailment"]]),
                "contradiction": float(probabilities[local_index, label_ids["contradiction"]]),
                "neutral": float(probabilities[local_index, label_ids["neutral"]]),
            }
            previous = best.get(sample_index)
            if previous is None or scores["entailment"] - scores["contradiction"] > previous["entailment"] - previous["contradiction"]:
                best[sample_index] = scores
    return best


def _process_shard(path, output, tokenizer, model, args, label_ids):
    started = time.perf_counter()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    results_path = output / path.name.replace("input-", "sentence-nli-")
    suggestions_path = output / path.name.replace("input-", "suggestions-")
    accepted = rejected = failed = 0
    with (
        results_path.open("w", encoding="utf-8", newline="\n") as results_handle,
        suggestions_path.open("w", encoding="utf-8", newline="\n") as suggestions_handle,
    ):
        for start in range(0, len(rows), args.sentence_batch_size):
            block = rows[start : start + args.sentence_batch_size]
            try:
                scores_by_index = _infer_block(tokenizer, model, block, args, label_ids)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                for row in block:
                    results_handle.write(json.dumps({
                        "sentence_id": row["sentence_id"], "review_id": row["review_id"],
                        "parent_asin": row["parent_asin"], "processing_status": "failed",
                        "error": error, "model_revision": MODEL_REVISION,
                    }, ensure_ascii=False) + "\n")
                    failed += 1
                continue
            for index, row in enumerate(block):
                scores = scores_by_index[index]
                is_suggestion = (
                    scores["entailment"] > scores["neutral"]
                    and scores["entailment"] > scores["contradiction"]
                )
                status = "suggestion" if is_suggestion else "not_suggestion"
                record = {
                    "sentence_id": row["sentence_id"],
                    "review_id": row["review_id"],
                    "parent_asin": row["parent_asin"],
                    "sentence_text": row["sentence_text"],
                    "entailment": round(scores["entailment"], 8),
                    "contradiction": round(scores["contradiction"], 8),
                    "neutral": round(scores["neutral"], 8),
                    "processing_status": status,
                    "error": None,
                    "model_revision": MODEL_REVISION,
                    "decision_rule": DECISION_RULE,
                    "classification_revision": CLASSIFICATION_REVISION,
                }
                results_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                if is_suggestion:
                    suggestions_handle.write(json.dumps({
                        "suggestion_id": row["sentence_id"],
                        "review_id": row["review_id"],
                        "parent_asin": row["parent_asin"],
                        "sentence_id": row["sentence_id"],
                        "sentence_text": row["sentence_text"],
                        "entailment": record["entailment"],
                        "neutral": record["neutral"],
                        "contradiction": record["contradiction"],
                        "confirmed_label": True,
                        "model_revision": MODEL_REVISION,
                        "decision_rule": DECISION_RULE,
                        "classification_revision": CLASSIFICATION_REVISION,
                    }, ensure_ascii=False) + "\n")
                    accepted += 1
                else:
                    rejected += 1
    return {
        "status": "ready" if failed == 0 else "completed_with_failures",
        "input_sentence_count": len(rows),
        "suggestion_count": accepted,
        "not_suggestion_count": rejected,
        "failed_count": failed,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def run(args):
    started = time.perf_counter()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    device_name = _require_xpu()
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_path, local_files_only=True)
    model.eval().to("xpu")
    if next(model.parameters()).device.type != "xpu":
        raise RuntimeError("NLI model is not on XPU; CPU fallback is forbidden")
    labels = {str(value).lower(): int(key) for key, value in model.config.id2label.items()}
    if set(labels) != {"entailment", "neutral", "contradiction"}:
        raise RuntimeError(f"unexpected NLI labels: {labels}")

    root = {
        "stage": "explicit_suggestion_nli", "status": "processing",
        "model_revision": MODEL_REVISION, "device": device_name,
        "hypothesis": HYPOTHESIS, "decision_rule": DECISION_RULE,
        "classification_revision": CLASSIFICATION_REVISION,
        "batch_size": args.batch_size, "max_length": args.max_length, "stride": args.stride,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    root_path = output / "status.json"
    _write_status(root_path, root)
    for shard in sorted(Path(args.input_dir).glob("input-*.ndjson")):
        status_path = output / shard.name.replace("input-", "status-").replace(".ndjson", ".json")
        if status_path.exists() and json.loads(status_path.read_text(encoding="utf-8")).get("status") == "ready":
            continue
        shard_status = _process_shard(shard, output, tokenizer, model, args, labels)
        shard_status.update({"input_file": shard.name, "finished_at": datetime.now(timezone.utc).isoformat()})
        _write_status(status_path, shard_status)
        root.update({"last_completed_shard": shard.name, "updated_at": datetime.now(timezone.utc).isoformat()})
        _write_status(root_path, root)

    statuses = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(output.glob("status-*.json"))]
    totals = {key: sum(int(item[key]) for item in statuses) for key in (
        "input_sentence_count", "suggestion_count", "not_suggestion_count", "failed_count"
    )}
    root.update({
        "status": "ready" if totals["failed_count"] == 0 else "completed_with_failures",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds_this_run": round(time.perf_counter() - started, 3),
        "shard_count": len(statuses), **totals,
        "xpu_peak_allocated_bytes": int(torch.xpu.max_memory_allocated()),
        "xpu_peak_reserved_bytes": int(torch.xpu.max_memory_reserved()),
        "process_peak_working_set_bytes": int(psutil.Process().memory_info().peak_wset),
    })
    _write_status(root_path, root)
    print(json.dumps(root, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--sentence-batch-size", type=int, default=256)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--stride", type=int, default=32)
    run(parser.parse_args())
