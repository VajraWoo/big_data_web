from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any, Iterator, Sequence


MODEL_ID = "Qwen/Qwen3.5-4B"
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
PROMPT_VERSION = "t011-product-theme-improvement-v1.0"
DEFAULT_MAX_MODEL_LEN = 8192
DEFAULT_MAX_INPUT_TOKENS = 7680
DEFAULT_MAX_NEW_TOKENS = 384

FINAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["improvement_suggestion"],
    "properties": {
        "improvement_suggestion": {"type": "string", "minLength": 1},
    },
}
SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["problem_summary"],
    "properties": {"problem_summary": {"type": "string", "minLength": 1}},
}

SYSTEM_PROMPT = """你是产品改进分析员。请仅依据给定的真实用户观点，为当前商品的当前负面主题提出具体、可执行的修改建议。
不得虚构证据中没有的问题，不得写营销文案，不得只改写主题名，也不要输出“建议进一步研究”等空话。
最终建议使用简洁中文；简单问题可写一句，复杂问题可写两三句。只输出符合指定 JSON schema 的对象。"""


def chunked(values: Sequence[Any], size: int) -> Iterator[list[Any]]:
    if size < 1:
        raise ValueError("batch size must be positive")
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def percentile(values: Sequence[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return int(ordered[index])


def format_insight(insight: dict[str, Any]) -> str:
    formatted = (
        f"[{insight['candidate_id']}]"
        f"[{insight['polarity']}] "
        f"{insight['candidate_text']}"
    )
    evidence = insight.get("evidence")
    if isinstance(evidence, str) and evidence.strip() and evidence != insight["candidate_text"]:
        formatted += f" | 原始证据：{evidence}"
    return formatted


def group_header(row: dict[str, Any]) -> str:
    return (
        f"商品：{row['product_title']}\n"
        f"商品类别：{row['product_category']}\n"
        f"负面主题：{row['canonical_theme_name']}\n"
        f"商品 ID：{row['parent_asin']}\n"
        f"Taxonomy ID：{row['taxonomy_id']}"
    )


def build_direct_messages(row: dict[str, Any]) -> list[dict[str, str]]:
    evidence = "\n".join(format_insight(item) for item in row["insights"])
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{group_header(row)}\n\n"
                "以下是该商品在此主题下的全部 negative/mixed insight。"
                "请综合它们生成一条修改建议。\n\n"
                f"{evidence}"
            ),
        },
    ]


def build_chunk_messages(row: dict[str, Any], insights: list[dict[str, Any]]) -> list[dict[str, str]]:
    evidence = "\n".join(format_insight(item) for item in insights)
    return [
        {
            "role": "system",
            "content": (
                "你只负责忠实汇总当前证据块反映的问题表现，不提出最终建议，"
                "不添加证据中没有的内容。只输出符合指定 JSON schema 的对象。"
            ),
        },
        {
            "role": "user",
            "content": f"{group_header(row)}\n\n证据块：\n{evidence}",
        },
    ]


def build_reduce_messages(row: dict[str, Any], summaries: list[str]) -> list[dict[str, str]]:
    blocks = "\n".join(f"[{index}] {value}" for index, value in enumerate(summaries, 1))
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{group_header(row)}\n\n"
                "以下内容是按原始 insight 固定顺序生成的证据块摘要。"
                "请综合全部摘要生成一条最终修改建议。\n\n"
                f"{blocks}"
            ),
        },
    ]


def token_count(tokenizer: Any, messages: list[dict[str, str]]) -> int:
    tokens = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
    )
    input_ids = getattr(tokens, "input_ids", None)
    return len(input_ids if input_ids is not None else tokens)


def split_insights(row: dict[str, Any], tokenizer: Any, max_input_tokens: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for insight in row["insights"]:
        candidate = current + [insight]
        if token_count(tokenizer, build_chunk_messages(row, candidate)) <= max_input_tokens:
            current = candidate
            continue
        if not current:
            raise ValueError(f"single insight exceeds input budget: {insight['candidate_id']}")
        chunks.append(current)
        current = [insight]
        if token_count(tokenizer, build_chunk_messages(row, current)) > max_input_tokens:
            raise ValueError(f"single insight exceeds input budget: {insight['candidate_id']}")
    if current:
        chunks.append(current)
    return chunks


def validate_suggestion(value: Any) -> str:
    if not isinstance(value, dict) or set(value) != {"improvement_suggestion"}:
        raise ValueError("response must contain only improvement_suggestion")
    suggestion = value["improvement_suggestion"]
    if not isinstance(suggestion, str) or not suggestion.strip():
        raise ValueError("improvement_suggestion must be non-empty")
    return suggestion.strip()


def validate_summary(value: Any) -> str:
    if not isinstance(value, dict) or set(value) != {"problem_summary"}:
        raise ValueError("response must contain only problem_summary")
    summary = value["problem_summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("problem_summary must be non-empty")
    return summary.strip()


def load_successful_input_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid checkpoint JSON at line {line_number}") from exc
            if row.get("generation_status") == "success" and row.get("input_id"):
                completed.add(str(row["input_id"]))
    return completed


def load_inputs(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            input_id = str(row.get("input_id") or "")
            if not input_id:
                raise ValueError(f"missing input_id at line {line_number}")
            if input_id in seen:
                raise ValueError(f"duplicate input_id: {input_id}")
            if not row.get("insights") or int(row.get("negative_insight_count", 0)) < 1:
                raise ValueError(f"invalid triggered group: {input_id}")
            seen.add(input_id)
            rows.append(row)
    return rows


def validate_model_manifest(model_dir: Path) -> None:
    manifest = json.loads((model_dir / "model_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("model_id") != MODEL_ID or manifest.get("revision") != MODEL_REVISION:
        raise ValueError("model manifest does not match frozen Qwen3.5-4B revision")


def scan_token_lengths(
    rows: list[dict[str, Any]], tokenizer: Any, max_input_tokens: int
) -> tuple[dict, dict]:
    lengths: list[int] = []
    chunked_groups: dict[str, list[list[dict]]] = {}
    for row in rows:
        length = token_count(tokenizer, build_direct_messages(row))
        lengths.append(length)
        if length > max_input_tokens:
            chunked_groups[row["input_id"]] = split_insights(row, tokenizer, max_input_tokens)
    return (
        {
            "group_count": len(rows),
            "max_input_tokens": max_input_tokens,
            "direct_group_count": len(rows) - len(chunked_groups),
            "chunked_group_count": len(chunked_groups),
            "token_length": {
                "min": min(lengths),
                "median": percentile(lengths, 0.5),
                "p95": percentile(lengths, 0.95),
                "p99": percentile(lengths, 0.99),
                "max": max(lengths),
            },
            "max_chunk_count": max((len(value) for value in chunked_groups.values()), default=1),
        },
        chunked_groups,
    )


class VllmAdapter:
    def __init__(self, model_dir: Path, max_model_len: int, gpu_memory_utilization: float):
        import torch
        from vllm import LLM, SamplingParams
        from vllm.sampling_params import StructuredOutputsParams

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; CPU fallback is forbidden")
        self.SamplingParams = SamplingParams
        self.StructuredOutputsParams = StructuredOutputsParams
        self.llm = LLM(
            model=str(model_dir),
            tokenizer=str(model_dir),
            dtype="bfloat16",
            gpu_memory_utilization=gpu_memory_utilization,
            max_model_len=max_model_len,
            enable_prefix_caching=True,
            trust_remote_code=False,
        )

    def generate(self, prompts: list[str], schema: dict, max_tokens: int):
        params = self.SamplingParams(
            temperature=0.0,
            max_tokens=max_tokens,
            repetition_penalty=1.1,
            structured_outputs=self.StructuredOutputsParams(json=schema),
        )
        return self.llm.generate(prompts, params, use_tqdm=False)


def prompt_text(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def parse_output(output: Any) -> tuple[dict, int, int, str]:
    candidate = output.outputs[0]
    raw = candidate.text
    return json.loads(raw), len(output.prompt_token_ids), len(candidate.token_ids), raw


def base_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "input_id", "parent_asin", "product_title", "product_category",
            "taxonomy_id", "canonical_theme_name", "support_insight_count",
            "support_review_count", "negative_insight_count", "mixed_insight_count",
        )
    }


def failure_record(row: dict[str, Any], error: Exception, mode: str) -> dict[str, Any]:
    return {
        **base_record(row),
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "prompt_version": PROMPT_VERSION,
        "generation_mode": mode,
        "generation_status": "failed",
        "error_type": type(error).__name__,
        "error_message": str(error),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline T011 vLLM improvement generation")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--checkpoint-jsonl", type=Path, required=True)
    parser.add_argument("--scan-report", type=Path, required=True)
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-model-len", type=int, default=DEFAULT_MAX_MODEL_LEN)
    parser.add_argument("--max-input-tokens", type=int, default=DEFAULT_MAX_INPUT_TOKENS)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    args = parser.parse_args()
    if args.max_input_tokens + args.max_new_tokens > args.max_model_len:
        raise ValueError("input and output token budgets exceed max-model-len")

    validate_model_manifest(args.model_dir)
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True)
    rows = load_inputs(args.input_jsonl)
    scan, chunk_map = scan_token_lengths(rows, tokenizer, args.max_input_tokens)
    scan.update({"model_id": MODEL_ID, "revision": MODEL_REVISION, "prompt_version": PROMPT_VERSION})
    args.scan_report.parent.mkdir(parents=True, exist_ok=True)
    args.scan_report.write_text(json.dumps(scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"token_scan": scan}, ensure_ascii=False), flush=True)
    if args.scan_only:
        return 0

    completed = load_successful_input_ids(args.checkpoint_jsonl)
    pending = [row for row in rows if row["input_id"] not in completed]
    args.checkpoint_jsonl.parent.mkdir(parents=True, exist_ok=True)
    adapter = VllmAdapter(args.model_dir, args.max_model_len, args.gpu_memory_utilization)
    started = time.perf_counter()
    success = failed = 0

    with args.checkpoint_jsonl.open("a", encoding="utf-8", newline="\n") as destination:
        direct = [row for row in pending if row["input_id"] not in chunk_map]
        for batch in chunked(direct, args.batch_size):
            prompts = [prompt_text(tokenizer, build_direct_messages(row)) for row in batch]
            outputs = adapter.generate(prompts, FINAL_SCHEMA, args.max_new_tokens)
            for row, output in zip(batch, outputs, strict=True):
                try:
                    parsed, input_tokens, output_tokens, _ = parse_output(output)
                    record = {
                        **base_record(row),
                        "improvement_suggestion": validate_suggestion(parsed),
                        "model_id": MODEL_ID,
                        "revision": MODEL_REVISION,
                        "prompt_version": PROMPT_VERSION,
                        "generation_mode": "direct",
                        "chunk_count": 1,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "generation_status": "success",
                    }
                    success += 1
                except Exception as exc:
                    record = failure_record(row, exc, "direct")
                    failed += 1
                destination.write(json.dumps(record, ensure_ascii=False) + "\n")
            destination.flush()
            print(json.dumps({"processed": success + failed, "pending": len(pending)}), flush=True)

        for row in (value for value in pending if value["input_id"] in chunk_map):
            try:
                chunks = chunk_map[row["input_id"]]
                map_prompts = [prompt_text(tokenizer, build_chunk_messages(row, chunk)) for chunk in chunks]
                map_outputs = adapter.generate(map_prompts, SUMMARY_SCHEMA, min(256, args.max_new_tokens))
                summaries = [validate_summary(parse_output(output)[0]) for output in map_outputs]
                reduce_messages = build_reduce_messages(row, summaries)
                if token_count(tokenizer, reduce_messages) > args.max_input_tokens:
                    raise ValueError("chunk summaries exceed fixed reduce input budget")
                final_output = adapter.generate(
                    [prompt_text(tokenizer, reduce_messages)], FINAL_SCHEMA, args.max_new_tokens
                )[0]
                parsed, input_tokens, output_tokens, _ = parse_output(final_output)
                record = {
                    **base_record(row),
                    "improvement_suggestion": validate_suggestion(parsed),
                    "model_id": MODEL_ID,
                    "revision": MODEL_REVISION,
                    "prompt_version": PROMPT_VERSION,
                    "generation_mode": "chunked",
                    "chunk_count": len(chunks),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "generation_status": "success",
                }
                success += 1
            except Exception as exc:
                record = failure_record(row, exc, "chunked")
                failed += 1
            destination.write(json.dumps(record, ensure_ascii=False) + "\n")
            destination.flush()
            print(json.dumps({"processed": success + failed, "pending": len(pending)}), flush=True)

    elapsed = time.perf_counter() - started
    print(json.dumps({"requested": len(pending), "skipped_success": len(completed), "success": success, "failed": failed, "seconds": round(elapsed, 2)}, ensure_ascii=False), flush=True)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
