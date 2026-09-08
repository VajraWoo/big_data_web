"""One-shot Intel XPU compatibility and throughput check for the locked NLI model."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


HYPOTHESIS = "The reviewer suggests a change, addition, or improvement to the product."


def require_xpu() -> str:
    if not torch.xpu.is_available():
        raise RuntimeError("Intel XPU is unavailable; CPU fallback is forbidden")
    name = torch.xpu.get_device_name(0)
    if "intel" not in name.lower() or "arc" not in name.lower():
        raise RuntimeError(f"unexpected XPU device: {name}")
    return name


def predict(texts, tokenizer, model, batch_size, max_length):
    probabilities = []
    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start : start + batch_size]
        encoded = tokenizer(
            batch_texts,
            [HYPOTHESIS] * len(batch_texts),
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to("xpu") for key, value in encoded.items()}
        with torch.inference_mode():
            logits = model(**encoded).logits
        probabilities.extend(torch.softmax(logits.float(), dim=-1).cpu().tolist())
    torch.xpu.synchronize()
    return probabilities


def run(args):
    device_name = require_xpu()
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_path, local_files_only=True)
    model.eval().to("xpu")
    if next(model.parameters()).device.type != "xpu":
        raise RuntimeError("NLI model is not on XPU; CPU fallback is forbidden")
    labels = {int(key): value for key, value in model.config.id2label.items()}
    expected_labels = {"entailment", "neutral", "contradiction"}
    if set(labels.values()) != expected_labels:
        raise RuntimeError(f"unexpected NLI labels: {labels}")

    semantic_texts = [
        "The ice maker should have a larger basket.",
        "The ice maker works perfectly and needs no changes.",
    ]
    semantic_probabilities = predict(semantic_texts, tokenizer, model, 2, args.max_length)
    by_label = [
        {labels[index]: round(score, 8) for index, score in enumerate(scores)}
        for scores in semantic_probabilities
    ]
    semantic_pass = (
        by_label[0]["entailment"] > by_label[0]["contradiction"]
        and by_label[1]["entailment"] <= by_label[1]["contradiction"]
    )
    if not semantic_pass:
        raise RuntimeError(f"fixed NLI semantic cases failed: {by_label}")

    texts = json.loads(Path(args.input).read_text(encoding="utf-8"))
    predict(texts[: args.batch_size * 2], tokenizer, model, args.batch_size, args.max_length)
    torch.xpu.reset_peak_memory_stats()
    started = time.perf_counter()
    predict(texts, tokenizer, model, args.batch_size, args.max_length)
    elapsed = time.perf_counter() - started
    report = {
        "status": "ready",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "model": "cross-encoder/nli-MiniLM2-L6-H768",
        "model_revision": Path(args.model_path).name,
        "device": device_name,
        "labels": labels,
        "hypothesis": HYPOTHESIS,
        "semantic_cases": [
            {"text": text, "scores": scores} for text, scores in zip(semantic_texts, by_label)
        ],
        "semantic_cases_passed": semantic_pass,
        "sentence_count": len(texts),
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "elapsed_seconds": round(elapsed, 6),
        "sentences_per_second": round(len(texts) / elapsed, 6),
        "xpu_peak_allocated_bytes": int(torch.xpu.max_memory_allocated()),
        "xpu_peak_reserved_bytes": int(torch.xpu.max_memory_reserved()),
        "process_peak_working_set_bytes": int(psutil.Process().memory_info().peak_wset),
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=256)
    run(parser.parse_args())
