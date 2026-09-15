import re


MARKERS = ("wish", "need", "should", "could", "would like", "if only", "hope")
LABELS = ("功能建议", "质量抱怨", "表扬", "其他")
_PATTERN = re.compile(
    r"\b(?:wish(?:es|ed|ing)?|need(?:s|ed|ing)?|should|could|would like|if only|hope(?:s|d|ing)?)\b",
    re.IGNORECASE,
)


def is_demand_candidate(text: str) -> bool:
    return bool(_PATTERN.search(text or ""))


def normalize_label(label: str) -> str:
    value = (label or "").strip()
    if value not in LABELS:
        raise ValueError(f"unsupported demand label: {value}")
    return value
