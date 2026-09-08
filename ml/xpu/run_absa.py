"""Resumable Intel XPU inference for the locked end-to-end ABSA model."""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer


MODEL_REVISION = "23e6d43431a5f96d8a7b7b9721d59bbda30cc63d"


def _write_status(path: Path, status: dict[str, object]) -> None:
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_intel_xpu() -> str:
    if not torch.xpu.is_available():
        raise RuntimeError("Intel XPU is unavailable; CPU fallback is forbidden")
    device_name = torch.xpu.get_device_name(0)
    if "intel" not in device_name.lower() or "arc" not in device_name.lower():
        raise RuntimeError(f"unexpected XPU device: {device_name}")
    probe = torch.tensor([1.0, 2.0], device="xpu")
    if probe.device.type != "xpu" or probe.sum().item() != 3.0:
        raise RuntimeError("XPU execution probe failed")
    return device_name


def _decode_aspects(
    *,
    row: dict[str, object],
    offsets: list[list[int] | tuple[int, int]],
    logits: torch.Tensor,
    id2label: dict[int, str],
) -> list[dict[str, object]]:
    probabilities = torch.softmax(logits.float(), dim=-1)
    predicted = probabilities.argmax(dim=-1)
    text = str(row["sentence_text"])
    found: list[dict[str, object]] = []
    active: dict[str, object] | None = None

    def flush() -> None:
        nonlocal active
        if active is None:
            return
        start = int(active["local_start"])
        end = int(active["local_end"])
        confidence_values = active.pop("confidence_values")
        if not text[start:end].strip():
            active = None
            return
        active.update(
            {
                "aspect_text": text[start:end],
                "confidence": round(sum(confidence_values) / len(confidence_values), 8),
                "aspect_start": int(row["char_start"]) + start,
                "aspect_end": int(row["char_start"]) + end,
            }
        )
        found.append(active)
        active = None

    for token_index, pair in enumerate(offsets):
        start, end = int(pair[0]), int(pair[1])
        if end <= start:
            flush()
            continue
        label = id2label[int(predicted[token_index])]
        if label == "O":
            flush()
            continue
        prefix, _, sentiment = label.partition("-ASP-")
        confidence = float(probabilities[token_index, int(predicted[token_index])])
        if prefix == "B" or active is None or active["aspect_sentiment"] != sentiment.lower():
            flush()
            active = {
                "local_start": start,
                "local_end": end,
                "aspect_sentiment": sentiment.lower(),
                "confidence_values": [confidence],
            }
        else:
            active["local_end"] = end
            active["confidence_values"].append(confidence)
    flush()
    return found


def _infer_block(tokenizer, model, rows, args):
    encoded = tokenizer(
        [str(row["sentence_text"]) for row in rows],
        padding=False,
        truncation=True,
        max_length=args.max_length,
        stride=args.stride,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
    )
    sample_mapping = encoded.pop("overflow_to_sample_mapping")
    offsets = encoded.pop("offset_mapping")
    features = []
    for index in range(len(encoded["input_ids"])):
        features.append({key: encoded[key][index] for key in encoded.keys()})

    aspects_by_sentence: dict[str, dict[tuple[int, int, str], dict[str, object]]] = defaultdict(dict)
    id2label = {int(key): value for key, value in model.config.id2label.items()}
    for start in range(0, len(features), args.batch_size):
        batch_features = features[start : start + args.batch_size]
        batch = tokenizer.pad(batch_features, padding=True, return_tensors="pt")
        batch = {key: value.to("xpu") for key, value in batch.items()}
        with torch.inference_mode():
            logits = model(**batch).logits.detach().cpu()
        for local_index in range(len(batch_features)):
            feature_index = start + local_index
            row = rows[int(sample_mapping[feature_index])]
            decoded = _decode_aspects(
                row=row,
                offsets=offsets[feature_index],
                logits=logits[local_index, : len(offsets[feature_index])],
                id2label=id2label,
            )
            sentence_key = str(row["sentence_id"])
            for aspect in decoded:
                key = (
                    int(aspect["aspect_start"]),
                    int(aspect["aspect_end"]),
                    str(aspect["aspect_sentiment"]),
                )
                previous = aspects_by_sentence[sentence_key].get(key)
                if previous is None or float(aspect["confidence"]) > float(previous["confidence"]):
                    aspects_by_sentence[sentence_key][key] = aspect
    return aspects_by_sentence


def _process_shard(path: Path, output: Path, tokenizer, model, args) -> dict[str, object]:
    started = time.perf_counter()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    reviews: dict[str, dict[str, object]] = {}
    for row in rows:
        reviews.setdefault(
            row["review_id"],
            {"review_id": row["review_id"], "parent_asin": row["parent_asin"], "aspect_count": 0},
        )
    aspects_path = output / path.name.replace("input-", "aspects-")
    reviews_path = output / path.name.replace("input-", "reviews-")
    sentence_failures: dict[str, str] = {}
    aspect_count = 0
    with aspects_path.open("w", encoding="utf-8", newline="\n") as aspects_handle:
        for start in range(0, len(rows), args.sentence_batch_size):
            block = rows[start : start + args.sentence_batch_size]
            try:
                inferred = _infer_block(tokenizer, model, block, args)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                for row in block:
                    sentence_failures[str(row["sentence_id"])] = error
                continue
            for row in block:
                sentence_aspects = inferred.get(str(row["sentence_id"]), {})
                for index, aspect in enumerate(
                    sorted(sentence_aspects.values(), key=lambda item: (item["aspect_start"], item["aspect_end"]))
                ):
                    record = {
                        "aspect_id": f"{row['sentence_id']}:a{index:03d}",
                        "review_id": row["review_id"],
                        "parent_asin": row["parent_asin"],
                        "sentence_id": row["sentence_id"],
                        "aspect_text": aspect["aspect_text"],
                        "aspect_sentiment": aspect["aspect_sentiment"],
                        "confidence": aspect["confidence"],
                        "aspect_start": aspect["aspect_start"],
                        "aspect_end": aspect["aspect_end"],
                        "sentence_start": row["char_start"],
                        "sentence_end": row["char_end"],
                        "sentence_text": row["sentence_text"],
                        "model_revision": MODEL_REVISION,
                    }
                    aspects_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    reviews[str(row["review_id"])]["aspect_count"] += 1
                    aspect_count += 1

    failed_reviews = {
        str(row["review_id"])
        for row in rows
        if str(row["sentence_id"]) in sentence_failures
    }
    success = no_attribute = failed = 0
    with reviews_path.open("w", encoding="utf-8", newline="\n") as reviews_handle:
        for review in reviews.values():
            review_id = str(review["review_id"])
            if review_id in failed_reviews:
                review["processing_status"] = "failed"
                review["error"] = "one or more sentence windows failed"
                failed += 1
            elif int(review["aspect_count"]) > 0:
                review["processing_status"] = "success"
                review["error"] = None
                success += 1
            else:
                review["processing_status"] = "no_attribute"
                review["error"] = None
                no_attribute += 1
            review["model_revision"] = MODEL_REVISION
            reviews_handle.write(json.dumps(review, ensure_ascii=False) + "\n")

    return {
        "status": "ready" if not failed else "completed_with_failures",
        "input_sentence_count": len(rows),
        "input_review_count": len(reviews),
        "success_count": success,
        "no_attribute_count": no_attribute,
        "failed_count": failed,
        "aspect_count": aspect_count,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    input_dir = Path(args.input_dir)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    device_name = _require_intel_xpu()
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True, use_fast=True)
    model = AutoModelForTokenClassification.from_pretrained(args.model_path, local_files_only=True)
    model.eval().to("xpu")
    if next(model.parameters()).device.type != "xpu":
        raise RuntimeError("ABSA model is not on XPU; CPU fallback is forbidden")

    root_status = {
        "stage": "absa",
        "status": "processing",
        "model_revision": MODEL_REVISION,
        "device": device_name,
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "stride": args.stride,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    root_status_path = output / "status.json"
    _write_status(root_status_path, root_status)
    shard_paths = sorted(input_dir.glob("input-*.ndjson"))
    for shard_path in shard_paths:
        shard_status_path = output / shard_path.name.replace("input-", "status-").replace(".ndjson", ".json")
        if shard_status_path.exists():
            existing = json.loads(shard_status_path.read_text(encoding="utf-8"))
            if existing.get("status") == "ready":
                continue
        shard_status = _process_shard(shard_path, output, tokenizer, model, args)
        shard_status.update({"input_file": shard_path.name, "finished_at": datetime.now(timezone.utc).isoformat()})
        _write_status(shard_status_path, shard_status)
        root_status["last_completed_shard"] = shard_path.name
        root_status["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_status(root_status_path, root_status)

    statuses = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(output.glob("status-*.json"))
    ]
    totals = {
        key: sum(int(status.get(key, 0)) for status in statuses)
        for key in (
            "input_sentence_count",
            "input_review_count",
            "success_count",
            "no_attribute_count",
            "failed_count",
            "aspect_count",
        )
    }
    root_status.update(
        {
            "status": "ready" if totals["failed_count"] == 0 else "completed_with_failures",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds_this_run": round(time.perf_counter() - started, 3),
            "shard_count": len(statuses),
            **totals,
            "xpu_peak_allocated_bytes": int(torch.xpu.max_memory_allocated()),
            "xpu_peak_reserved_bytes": int(torch.xpu.max_memory_reserved()),
            "process_peak_working_set_bytes": int(psutil.Process().memory_info().peak_wset),
        }
    )
    _write_status(root_status_path, root_status)
    print(json.dumps(root_status, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--sentence-batch-size", type=int, default=256)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--stride", type=int, default=32)
    run(parser.parse_args())
