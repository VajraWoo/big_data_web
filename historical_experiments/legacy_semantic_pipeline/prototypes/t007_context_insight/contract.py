from __future__ import annotations

from typing import Any


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
                        "evidence": {"type": "string", "minLength": 1},
                        "evidence_occurrence": {"type": "integer", "minimum": 0},
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


def validate_response(review_text: str, response: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or set(response) != {"insights"}:
        raise ContractError("response must contain only an insights array")
    if not isinstance(response["insights"], list):
        raise ContractError("insights must be an array")

    validated: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    ambiguous_evidence_count = 0
    for index, raw in enumerate(response["insights"]):
        if not isinstance(raw, dict):
            raise ContractError(f"insight {index} must be an object")
        required = {"topic_raw", "polarity", "evidence", "target_scope"}
        allowed = required | {"evidence_occurrence"}
        if not required.issubset(raw) or not set(raw).issubset(allowed):
            raise ContractError(f"insight {index} has missing or unknown fields")

        topic = raw["topic_raw"]
        evidence = raw["evidence"]
        polarity = raw["polarity"]
        target_scope = raw["target_scope"]
        if not isinstance(topic, str) or not topic.strip():
            raise ContractError(f"insight {index} has an empty topic")
        if not isinstance(evidence, str) or not evidence:
            raise ContractError(f"insight {index} has empty evidence")
        if polarity not in POLARITIES:
            raise ContractError(f"insight {index} has invalid polarity")
        if target_scope not in TARGET_SCOPES:
            raise ContractError(f"insight {index} has invalid target_scope")

        offsets = _all_offsets(review_text, evidence)
        if not offsets:
            raise ContractError(f"insight {index} evidence not found in text_raw")
        occurrence = raw.get("evidence_occurrence")
        if len(offsets) > 1 and occurrence is None:
            raise ContractError(f"insight {index} has ambiguous evidence")
        if occurrence is None:
            occurrence = 0
        if not isinstance(occurrence, int) or occurrence < 0 or occurrence >= len(offsets):
            raise ContractError(f"insight {index} has invalid evidence occurrence")

        key = (topic.strip().casefold(), evidence, target_scope)
        if key in seen:
            continue
        seen.add(key)
        if len(offsets) > 1:
            ambiguous_evidence_count += 1
        start = offsets[occurrence]
        validated.append(
            {
                "topic_raw": topic.strip(),
                "polarity": polarity,
                "evidence": evidence,
                "evidence_occurrence": occurrence,
                "evidence_char_start": start,
                "evidence_char_end": start + len(evidence),
                "target_scope": target_scope,
            }
        )
    return {
        "insights": validated,
        "ambiguous_evidence_count": ambiguous_evidence_count,
        "ambiguous_evidence_rate": (
            ambiguous_evidence_count / len(validated) if validated else 0.0
        ),
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
