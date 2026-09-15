from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .contract import build_record, response_json_schema, validate_response
from .prompt import PROMPT_VERSION, build_messages
from .runtime import DeviceError, require_cuda, run_with_bounded_retry

MODEL_ID = "Qwen/Qwen3.5-4B"
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MODEL_TYPE = "qwen3_5"
EXPECTED_ARCHITECTURE = "Qwen3_5ForConditionalGeneration"


def ensure_external_output(path: Path) -> None:
    resolved = path.resolve()
    if resolved.is_relative_to(WORKSPACE_ROOT):
        raise ValueError("evaluation output must remain outside the Git workspace")


def ensure_model_on_cuda(model: Any) -> None:
    non_cuda = [
        parameter.device.type
        for parameter in model.parameters()
        if parameter.device.type != "cuda"
    ]
    if non_cuda:
        raise DeviceError(
            "model contains non-CUDA parameters; CPU fallback is forbidden"
        )


def require_text_raw(row: dict[str, Any]) -> str:
    if "text_raw" not in row or not isinstance(row["text_raw"], str):
        raise ValueError("T007 requires text_raw")
    return row["text_raw"]


def validate_model_manifest(model_dir: Path) -> dict[str, str]:
    manifest_path = model_dir / "model_manifest.json"
    config_path = model_dir / "config.json"
    if not manifest_path.is_file():
        raise ValueError(f"missing model manifest: {manifest_path}")
    if not config_path.is_file():
        raise ValueError(f"missing model config: {config_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model_id") != MODEL_ID:
        raise ValueError("model_id mismatch in model_manifest.json")
    if manifest.get("revision") != MODEL_REVISION:
        raise ValueError("revision mismatch in model_manifest.json")
    local_path = manifest.get("local_path")
    if not isinstance(local_path, str) or Path(local_path).resolve() != model_dir.resolve():
        raise ValueError("local_path mismatch in model_manifest.json")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("model_type") != EXPECTED_MODEL_TYPE:
        raise ValueError("unexpected model_type in config.json")
    if EXPECTED_ARCHITECTURE not in config.get("architectures", []):
        raise ValueError("unexpected architectures in config.json")
    return {"model_id": MODEL_ID, "revision": MODEL_REVISION}


def failure_record(row: dict[str, Any], error: Exception) -> dict[str, Any]:
    return {
        "review_id": row.get("review_id"),
        "parent_asin": row.get("parent_asin", ""),
        "asin": row.get("asin", ""),
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "prompt_version": PROMPT_VERSION,
        "processing_status": "failed",
        "attempts": getattr(error, "attempts", 0),
        "error_type": type(error).__name__,
        "error_message": str(error),
    }


class QwenInsightAdapter:
    def __init__(self, model_dir: Path, *, max_attempts: int = 2, max_new_tokens: int = 512):
        import torch
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import (
            build_transformers_prefix_allowed_tokens_fn,
        )
        from transformers import AutoModelForMultimodalLM, AutoProcessor

        validate_model_manifest(model_dir)
        self.torch = torch
        self.device = require_cuda(torch)
        self.max_attempts = max_attempts
        self.max_new_tokens = max_new_tokens
        self.JsonSchemaParser = JsonSchemaParser
        self.build_prefix_fn = build_transformers_prefix_allowed_tokens_fn
        self.processor = AutoProcessor.from_pretrained(model_dir, local_files_only=True)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            model_dir,
            local_files_only=True,
            torch_dtype=torch.bfloat16,
        ).eval().to(self.device)
        ensure_model_on_cuda(self.model)

    def _generate(self, messages: list[dict[str, str]]) -> str:
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.device)
        parser = self.JsonSchemaParser(response_json_schema())
        prefix_fn = self.build_prefix_fn(self.processor.tokenizer, parser)
        prompt_length = inputs["input_ids"].shape[-1]
        with self.torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=self.max_new_tokens,
                prefix_allowed_tokens_fn=prefix_fn,
            )
        return self.processor.decode(
            generated[0, prompt_length:], skip_special_tokens=True
        ).strip()

    def infer(self, row: dict[str, Any]) -> dict[str, Any]:
        review_text = require_text_raw(row)
        messages = build_messages(
            product_title=row["product_title"],
            product_category=row["product_category"],
            review_text=review_text,
        )
        attempt = 0

        def generate() -> str:
            nonlocal attempt
            attempt += 1
            current = list(messages)
            if attempt > 1:
                current.append(
                    {
                        "role": "user",
                        "content": "Retry once. Every evidence value must be copied exactly from the review.",
                    }
                )
            return self._generate(current)

        response = run_with_bounded_retry(
            generate,
            max_attempts=self.max_attempts,
            validate=lambda value: validate_response(review_text, value),
        )
        return build_record(
            review_id=row["review_id"],
            parent_asin=row.get("parent_asin", ""),
            asin=row.get("asin", ""),
            review_text=review_text,
            response=response,
            model_id=MODEL_ID,
            revision=MODEL_REVISION,
            prompt_version=PROMPT_VERSION,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=2)
    args = parser.parse_args()

    ensure_external_output(args.output_jsonl)
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    adapter = QwenInsightAdapter(args.model_dir, max_attempts=args.max_attempts)
    with args.input_jsonl.open("r", encoding="utf-8") as source, args.output_jsonl.open(
        "w", encoding="utf-8"
    ) as destination:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            try:
                result = adapter.infer(row)
            except Exception as exc:
                result = failure_record(row, exc)
            destination.write(json.dumps(result, ensure_ascii=False) + "\n")
            destination.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
