from __future__ import annotations

import argparse
import json
import math
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .contract import build_partial_record, response_json_schema
from .prompt import PROMPT_VERSION, build_messages

MODEL_ID = "Qwen/Qwen3.5-4B"
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
EXPECTED_MODEL_TYPE = "qwen3_5"
EXPECTED_ARCHITECTURE = "Qwen3_5ForConditionalGeneration"
DEFAULT_MAX_NEW_TOKENS = 1024


def chunked(values: Sequence[Any], size: int) -> Iterator[list[Any]]:
    if size < 1:
        raise ValueError("batch size must be positive")
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def percentile(values: Sequence[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return int(ordered[index])


def load_completed_review_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid resume JSONL at line {line_number}") from exc
            review_id = value.get("review_id")
            if isinstance(review_id, str) and review_id:
                completed.add(review_id)
    return completed


def validate_model_manifest(model_dir: Path) -> None:
    manifest_path = model_dir / "model_manifest.json"
    config_path = model_dir / "config.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if manifest.get("model_id") != MODEL_ID:
        raise ValueError("4B model_id mismatch")
    if manifest.get("revision") != MODEL_REVISION:
        raise ValueError("4B revision mismatch")
    if Path(str(manifest.get("local_path"))).resolve() != model_dir.resolve():
        raise ValueError("4B local_path mismatch")
    if config.get("model_type") != EXPECTED_MODEL_TYPE:
        raise ValueError("unexpected model_type")
    if EXPECTED_ARCHITECTURE not in config.get("architectures", []):
        raise ValueError("unexpected model architecture")


def require_text_raw(row: dict[str, Any]) -> str:
    text = row.get("text_raw")
    if not isinstance(text, str):
        raise ValueError("T007 requires text_raw")
    return text


def failure_record(row: dict[str, Any], error: Exception, attempts: int, raw_output: str | None = None) -> dict[str, Any]:
    return {
        "review_id": row.get("review_id"),
        "parent_asin": row.get("parent_asin", ""),
        "asin": row.get("asin", ""),
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "prompt_version": PROMPT_VERSION,
        "processing_status": "failed",
        "attempts": attempts,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "raw_output": raw_output,
    }


class GpuMonitor:
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.utilization: list[int] = []
        self.memory_mib: list[int] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(2.0, self.interval * 2))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                output = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=5,
                ).strip().splitlines()[0]
                utilization, memory = [int(value.strip()) for value in output.split(",")]
                self.utilization.append(utilization)
                self.memory_mib.append(memory)
            except Exception:
                pass
            self._stop.wait(self.interval)

    def summary(self) -> dict[str, float | int]:
        return {
            "gpu_samples": len(self.utilization),
            "gpu_utilization_avg_percent": round(sum(self.utilization) / len(self.utilization), 2) if self.utilization else 0.0,
            "gpu_utilization_peak_percent": max(self.utilization, default=0),
            "gpu_memory_peak_mib": max(self.memory_mib, default=0),
        }


@dataclass
class WorkItem:
    row: dict[str, Any]
    messages: list[dict[str, str]]
    attempts: int = 0


class VllmAdapter:
    def __init__(self, model_dir: Path, gpu_memory_utilization: float, max_model_len: int, max_new_tokens: int):
        validate_model_manifest(model_dir)
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; CPU fallback is forbidden")
        from transformers import AutoTokenizer
        from vllm import LLM, SamplingParams
        from vllm.sampling_params import StructuredOutputsParams

        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        self.sampling_params = SamplingParams(
            temperature=0.0,
            max_tokens=max_new_tokens,
            repetition_penalty=1.1,
            structured_outputs=StructuredOutputsParams(json=response_json_schema()),
        )
        self.llm = LLM(
            model=str(model_dir),
            tokenizer=str(model_dir),
            dtype="bfloat16",
            gpu_memory_utilization=gpu_memory_utilization,
            max_model_len=max_model_len,
            enable_prefix_caching=True,
            trust_remote_code=False,
        )

    def prompt(self, messages: list[dict[str, str]]) -> str:
        return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    def generate(self, items: list[WorkItem]):
        prompts = [self.prompt(item.messages) for item in items]
        return self.llm.generate(prompts, self.sampling_params, use_tqdm=False)


def load_pending_rows(input_path: Path, completed: set[str], limit: int | None) -> tuple[list[dict[str, Any]], int]:
    pending: list[dict[str, Any]] = []
    skipped = 0
    with input_path.open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            review_id = row.get("review_id")
            if review_id in completed:
                skipped += 1
                continue
            pending.append(row)
            if limit is not None and len(pending) >= limit:
                break
    return pending, skipped


def make_item(row: dict[str, Any]) -> WorkItem:
    review_text = require_text_raw(row)
    messages = build_messages(
        product_title=row["product_title"],
        product_category=row["product_category"],
        review_text=review_text,
    )
    return WorkItem(row=row, messages=messages)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.max_attempts not in (1, 2):
        raise ValueError("max-attempts must be 1 or 2")

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    summary_path = args.summary_json or args.output_jsonl.with_suffix(".summary.json")
    completed = load_completed_review_ids(args.output_jsonl)
    rows, skipped = load_pending_rows(args.input_jsonl, completed, args.limit)

    monitor = GpuMonitor()
    monitor.start()
    wall_started = time.perf_counter()
    load_started = time.perf_counter()
    adapter = VllmAdapter(args.model_dir, args.gpu_memory_utilization, args.max_model_len, args.max_new_tokens)
    load_seconds = time.perf_counter() - load_started
    inference_started = time.perf_counter()

    success = 0
    failed = 0
    engine_input_tokens: list[int] = []
    engine_output_tokens: list[int] = []
    result_input_tokens: list[int] = []
    result_output_tokens: list[int] = []

    with args.output_jsonl.open("a", encoding="utf-8") as destination:
        for row_batch in chunked(rows, args.batch_size):
            active: list[WorkItem] = []
            for row in row_batch:
                try:
                    active.append(make_item(row))
                except Exception as exc:
                    destination.write(json.dumps(failure_record(row, exc, 0), ensure_ascii=False) + "\n")
                    destination.flush()
                    failed += 1

            for attempt_number in range(1, args.max_attempts + 1):
                if not active:
                    break
                for item in active:
                    item.attempts = attempt_number
                    if attempt_number == 2:
                        item.messages = list(item.messages) + [{
                            "role": "user",
                            "content": "Retry once. Every evidence value must be copied exactly from the review.",
                        }]
                outputs = adapter.generate(active)
                retry: list[WorkItem] = []
                for item, output in zip(active, outputs, strict=True):
                    input_count = len(output.prompt_token_ids)
                    candidate = output.outputs[0]
                    output_count = len(candidate.token_ids)
                    engine_input_tokens.append(input_count)
                    engine_output_tokens.append(output_count)
                    try:
                        response = json.loads(candidate.text)
                        review_text = require_text_raw(item.row)
                        record = build_partial_record(
                            review_id=item.row["review_id"],
                            parent_asin=item.row.get("parent_asin", ""),
                            asin=item.row.get("asin", ""),
                            review_text=review_text,
                            response=response,
                            model_id=MODEL_ID,
                            revision=MODEL_REVISION,
                            prompt_version=PROMPT_VERSION,
                        )
                        if record["processing_status"] == "failed" and attempt_number < args.max_attempts:
                            retry.append(item)
                            continue
                        record.update({
                            "attempts": attempt_number,
                            "input_tokens": input_count,
                            "output_tokens": output_count,
                            "raw_output": candidate.text if record["rejected_insights"] else None,
                        })
                        destination.write(json.dumps(record, ensure_ascii=False) + "\n")
                        destination.flush()
                        if record["processing_status"] == "failed":
                            failed += 1
                        else:
                            success += 1
                            result_input_tokens.append(input_count)
                            result_output_tokens.append(output_count)
                    except Exception as exc:
                        if attempt_number < args.max_attempts:
                            retry.append(item)
                        else:
                            destination.write(json.dumps(failure_record(item.row, exc, attempt_number, candidate.text), ensure_ascii=False) + "\n")
                            destination.flush()
                            failed += 1
                active = retry

            elapsed = time.perf_counter() - inference_started
            processed = success + failed
            rate = processed / elapsed if elapsed else 0.0
            eta = (len(rows) - processed) / rate if rate else None
            print(json.dumps({"processed": processed, "total": len(rows), "reviews_per_second": round(rate, 4), "eta_seconds": round(eta, 1) if eta is not None else None}), flush=True)

    inference_seconds = time.perf_counter() - inference_started
    wall_seconds = time.perf_counter() - wall_started
    monitor.stop()
    summary = {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "prompt_version": PROMPT_VERSION,
        "input_path": str(args.input_jsonl),
        "output_path": str(args.output_jsonl),
        "batch_size": args.batch_size,
        "requested": len(rows),
        "skipped_existing": skipped,
        "success": success,
        "failed": failed,
        "load_seconds": round(load_seconds, 3),
        "inference_seconds": round(inference_seconds, 3),
        "total_seconds": round(wall_seconds, 3),
        "reviews_per_second": round((success + failed) / inference_seconds, 6) if inference_seconds else 0.0,
        "input_tokens_per_second": round(sum(engine_input_tokens) / inference_seconds, 3) if inference_seconds else 0.0,
        "output_tokens_per_second": round(sum(engine_output_tokens) / inference_seconds, 3) if inference_seconds else 0.0,
        "input_tokens_mean": round(sum(result_input_tokens) / len(result_input_tokens), 2) if result_input_tokens else 0.0,
        "input_tokens_p95": percentile(result_input_tokens, 0.95),
        "output_tokens_mean": round(sum(result_output_tokens) / len(result_output_tokens), 2) if result_output_tokens else 0.0,
        "output_tokens_p95": percentile(result_output_tokens, 0.95),
        "estimated_full_seconds_116728": round(116728 * inference_seconds / (success + failed), 1) if success + failed else None,
        **monitor.summary(),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
