from __future__ import annotations

from typing import Any

import re

POLARITIES = {"positive", "negative", "neutral", "mixed"}
TARGET_SCOPES = {
    "current_product",
    "other_product",
    "service_logistics",
    "usage_context",
    "unclear",
}


class ContractError(ValueError):
    pass


def response_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["insights"],
        "properties": {
            "insights": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "topic_raw",
                        "polarity",
                        "evidence",
                        "target_scope",
                    ],
                    "properties": {
                        "topic_raw": {"type": "string", "minLength": 1},
                        "polarity": {"enum": sorted(POLARITIES)},
                        "evidence": {
    "type": "string",
    "minLength": 1,
    "maxLength": 300,
},
                        "target_scope": {"enum": sorted(TARGET_SCOPES)},
                    },
                },
            }
        },
    }


def _all_offsets(text: str, evidence: str) -> list[int]:
    offsets: list[int] = []
    cursor = 0

    while True:
        position = text.find(evidence, cursor)
        if position < 0:
            return offsets

        offsets.append(position)
        cursor = position + 1


def _ground_evidence(text: str, evidence: str) -> tuple[str, int, int]:
    # 1. 优先 exact match
    exact_offsets = _all_offsets(text, evidence)

    if len(exact_offsets) == 1:
        start = exact_offsets[0]
        return evidence, start, start + len(evidence)

    if len(exact_offsets) > 1:
        raise ContractError("evidence has multiple exact matches in text_raw")

    # 2. exact match 失败时，只允许空白或引号形态差异。
    # 唯一命中后仍回写 text_raw 中的真实原文与坐标。
    normalized = evidence.strip()
    if not normalized:
        raise ContractError("empty evidence after normalization")

    quote_pattern = r"[\"'“”‘’]"
    pattern_parts: list[str] = []
    cursor = 0
    while cursor < len(normalized):
        character = normalized[cursor]
        if character.isspace():
            while cursor < len(normalized) and normalized[cursor].isspace():
                cursor += 1
            pattern_parts.append(r"\s+")
            continue
        pattern_parts.append(quote_pattern if character in "\"'“”‘’" else re.escape(character))
        cursor += 1

    pattern = "".join(pattern_parts)
    matches = list(re.finditer(pattern, text))

    if not matches:
        raise ContractError("evidence not found in text_raw")

    if len(matches) > 1:
        raise ContractError(
            "evidence has multiple normalized matches in text_raw"
        )

    match = matches[0]

    start = match.start()
    end = match.end()

    # 最终 evidence 必须回写 text_raw 中的真实原文
    grounded_evidence = text[start:end]

    return grounded_evidence, start, end


def validate_response(review_text: str, response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or set(response) != {"insights"}:
        raise ContractError("response must contain only an insights array")

    if not isinstance(response["insights"], list):
        raise ContractError("insights must be an array")

    validated: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for index, raw in enumerate(response["insights"]):
        if not isinstance(raw, dict):
            raise ContractError(f"insight {index} must be an object")

        required = {
            "topic_raw",
            "polarity",
            "evidence",
            "target_scope",
        }

        allowed = required

        if not required.issubset(raw) or not set(raw).issubset(allowed):
            raise ContractError(
                f"insight {index} has missing or unknown fields"
            )

        topic = raw["topic_raw"]
        evidence = raw["evidence"]
        polarity = raw["polarity"]
        target_scope = raw["target_scope"]

        if not isinstance(topic, str) or not topic.strip():
            raise ContractError(
                f"insight {index} has an empty topic"
            )

        if not isinstance(evidence, str) or not evidence:
            raise ContractError(
                f"insight {index} has empty evidence"
            )

        if polarity not in POLARITIES:
            raise ContractError(
                f"insight {index} has invalid polarity"
            )

        if target_scope not in TARGET_SCOPES:
            raise ContractError(
                f"insight {index} has invalid target_scope"
            )

        try:
            grounded_evidence, start, end = _ground_evidence(
                review_text,
                evidence,
            )
        except ContractError as exc:
            raise ContractError(
                f"insight {index} {exc}"
            ) from exc

        key = (
            topic.strip().casefold(),
            grounded_evidence,
            target_scope,
        )

        if key in seen:
            continue

        seen.add(key)

        validated.append(
            {
                "topic_raw": topic.strip(),
                "polarity": polarity,
                "evidence": grounded_evidence,
                "evidence_char_start": start,
                "evidence_char_end": end,
                "target_scope": target_scope,
            }
        )

    return {
    "insights": validated,
    "ambiguous_evidence_count": 0,
    "ambiguous_evidence_rate": 0.0,
}


def build_record(
    *,
    review_id: str,
    parent_asin: str,
    asin: str,
    review_text: str,
    response: Any,
    model_id: str,
    revision: str,
    prompt_version: str,
) -> dict[str, Any]:
    validated = validate_response(review_text, response)
    return {
        "review_id": review_id,
        "parent_asin": parent_asin,
        "asin": asin,
        "model_id": model_id,
        "revision": revision,
        "prompt_version": prompt_version,
        "processing_status": (
            "success" if validated["insights"] else "success_no_insight"
        ),
        "ambiguous_evidence_count": validated["ambiguous_evidence_count"],
        "ambiguous_evidence_rate": validated["ambiguous_evidence_rate"],
        "insights": validated["insights"],
    }


def build_partial_record(
    *,
    review_id: str,
    parent_asin: str,
    asin: str,
    review_text: str,
    response: Any,
    model_id: str,
    revision: str,
    prompt_version: str,
) -> dict[str, Any]:
    if not isinstance(response, dict) or set(response) != {"insights"}:
        raise ContractError("response must contain only an insights array")
    raw_insights = response["insights"]
    if not isinstance(raw_insights, list):
        raise ContractError("insights must be an array")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for index, raw_insight in enumerate(raw_insights):
        try:
            candidate = validate_response(
                review_text,
                {"insights": [raw_insight]},
            )["insights"][0]
            key = (
                candidate["topic_raw"].casefold(),
                candidate["evidence"],
                candidate["target_scope"],
            )
            if key in seen:
                continue
            seen.add(key)
            accepted.append(candidate)
        except (ContractError, IndexError) as exc:
            rejected.append(
                {
                    "index": index,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "raw_insight": raw_insight,
                }
            )

    if accepted and rejected:
        status = "partial_success"
    elif accepted:
        status = "success"
    elif rejected:
        status = "failed"
    else:
        status = "success_no_insight"

    record = {
        "review_id": review_id,
        "parent_asin": parent_asin,
        "asin": asin,
        "model_id": model_id,
        "revision": revision,
        "prompt_version": prompt_version,
        "processing_status": status,
        "ambiguous_evidence_count": 0,
        "ambiguous_evidence_rate": 0.0,
        "insights": accepted,
        "rejected_insights": rejected,
    }
    if status == "failed":
        record.update(
            {
                "error_type": "ContractError",
                "error_message": "all generated insights were rejected",
            }
        )
    return record
