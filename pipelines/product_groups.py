"""Pure, outcome-blind rules for product-group profiling and selection."""

from __future__ import annotations

import math
import re
import unicodedata


GENERIC_CATEGORIES = {
    "appliances",
    "home & kitchen",
    "home and kitchen",
    "products",
}


def _is_generic_category(label: str) -> bool:
    normalized = label.casefold()
    tokens = set(re.findall(r"[a-z]+", normalized))
    return normalized in GENERIC_CATEGORIES or bool(tokens & {"parts", "accessories"})

DEFAULT_THRESHOLDS = {
    "review_count": 5000,
    "product_count": 10,
    "eligible_text_rate": 0.70,
    "active_months": 12,
    "metadata_identifiability": 0.80,
    "category_depth": 2,
}


def _clean_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split()).strip()
    return cleaned or None


def _slug(label: str) -> str:
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_label.lower()).strip("-")


def canonical_product_group(categories: object, main_category: object = None) -> dict | None:
    """Return the deepest non-generic category without using review outcomes."""
    path = []
    if isinstance(categories, (list, tuple)):
        for value in categories:
            label = _clean_label(value)
            if label and (not path or path[-1].casefold() != label.casefold()):
                path.append(label)
    main = _clean_label(main_category)
    if not path and main:
        path.append(main)
    specific = [label for label in path if not _is_generic_category(label)]
    if not specific:
        return None
    name = specific[-1]
    group_id = _slug(name)
    if not group_id:
        return None
    return {
        "group_id": group_id,
        "name": name,
        "category_depth": len(path),
        "category_path": path,
    }


def evaluate_candidate(metrics: dict, thresholds: dict | None = None) -> dict:
    """Apply predeclared data sufficiency gates and retain every failure reason."""
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    checks = [
        ("review_count", "reviews", 0),
        ("product_count", "products", 0),
        ("eligible_text_rate", "eligible_text_rate", 0.0),
        ("active_months", "active_months", 0),
        ("metadata_identifiability", "metadata_identifiability", 0.0),
        ("category_depth", "category_depth", 0),
    ]
    reasons = []
    for field, reason_name, default in checks:
        observed = metrics.get(field, default)
        minimum = limits[field]
        if observed is None or observed < minimum:
            suffix = f"{minimum:.2f}" if isinstance(minimum, float) else str(minimum)
            reasons.append(f"{reason_name}_below_{suffix}")
    return {
        "selection_state": "candidate" if not reasons else "rejected",
        "selection_reasons": ["passed_predeclared_data_gates"] if not reasons else [],
        "rejection_reasons": reasons,
    }


def selection_score(metrics: dict) -> float:
    """Fixed score using only coverage, continuity and metadata—not NLP outcomes."""
    review_component = min(math.log1p(max(metrics.get("review_count", 0), 0)) / math.log1p(1_000_000), 1.0)
    product_component = min(math.log1p(max(metrics.get("product_count", 0), 0)) / math.log1p(10_000), 1.0)
    time_component = min(max(metrics.get("active_months", 0), 0) / 120.0, 1.0)
    depth_component = min(max(metrics.get("category_depth", 0), 0) / 4.0, 1.0)
    score = (
        0.35 * review_component
        + 0.20 * product_component
        + 0.20 * max(min(metrics.get("eligible_text_rate", 0.0), 1.0), 0.0)
        + 0.10 * time_component
        + 0.10 * max(min(metrics.get("metadata_identifiability", 0.0), 1.0), 0.0)
        + 0.05 * depth_component
    )
    return round(score, 8)


def _semantic_family(row: dict) -> str:
    words = re.findall(r"[a-z]+", str(row.get("name") or row.get("group_id") or "").casefold())
    if not words:
        return str(row.get("group_id", ""))
    family = words[-1]
    if family.endswith("ies") and len(family) > 3:
        return family[:-3] + "y"
    if family.endswith("s") and not family.endswith("ss") and len(family) > 3:
        return family[:-1]
    return family


def select_candidates(rows: list[dict], minimum_selected: int = 2, thresholds: dict | None = None) -> list[dict]:
    """Select the highest fixed-score eligible groups with deterministic ties."""
    evaluated = []
    for source in rows:
        row = dict(source)
        row.update(evaluate_candidate(row, thresholds))
        row["selection_score"] = selection_score(row)
        row["semantic_family"] = _semantic_family(row)
        evaluated.append(row)

    eligible = sorted(
        (row for row in evaluated if row["selection_state"] == "candidate"),
        key=lambda row: (-row["selection_score"], row["group_id"]),
    )
    selected_families = set()
    selected = []
    for row in eligible:
        if row["semantic_family"] in selected_families:
            continue
        selected.append(row)
        selected_families.add(row["semantic_family"])
        if len(selected) == minimum_selected:
            break
    for row in selected:
        row["selection_state"] = "selected"
        row["selection_reasons"] = [
            "passed_predeclared_data_gates",
            "top_outcome_blind_selection_score",
            "distinct_semantic_family",
        ]

    state_order = {"selected": 0, "candidate": 1, "rejected": 2}
    return sorted(
        evaluated,
        key=lambda row: (state_order[row["selection_state"]], -row["selection_score"], row["group_id"]),
    )
