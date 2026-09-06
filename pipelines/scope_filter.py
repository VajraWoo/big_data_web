"""Rules shared by the whole-appliance scope statistics job."""

from __future__ import annotations


WHOLE_APPLIANCE_CATEGORIES = {
    "All-in-One Combination Washers & Dryers",
    "Beverage Refrigerators",
    "Built-In Dishwashers",
    "Chest Freezers",
    "Combination Microwave & Wall Ovens",
    "Cooktops",
    "Countertop Dishwashers",
    "Double Wall Ovens",
    "Drop-In Ranges",
    "Dryers",
    "Freestanding Ranges",
    "Ice Makers",
    "Kegerators",
    "LG Styler Steam Closets",
    "Portable Dishwashers",
    "Portable Dryers",
    "Portable Washers",
    "Range Hoods",
    "Refrigerators",
    "Single Wall Ovens",
    "Slide-In Ranges",
    "Stacked Washer & Dryer Units",
    "Trash Compactors",
    "Upright Freezers",
    "Washers",
    "Warming Drawers",
}

EXCLUDED_MARKERS = (
    "accessories",
    "replacement",
    "filters",
    "parts",
)


def classify_product_category(categories: object) -> tuple[str, str | None]:
    """Return included/excluded/review and the specific whole-appliance category."""
    if not isinstance(categories, (list, tuple)) or not categories:
        return "review", None
    path = [value.strip() for value in categories if isinstance(value, str) and value.strip()]
    if not path:
        return "review", None
    lowered = " > ".join(path).lower()
    if any(marker in lowered for marker in EXCLUDED_MARKERS):
        return "excluded", None
    category = path[-1]
    if category in WHOLE_APPLIANCE_CATEGORIES:
        return "included", category
    return "review", None


def product_passes_scope(
    *,
    review_count: int,
    active_months: int,
    last_review_month: str,
    active_since_month: str,
    positive_count: int = 0,
    negative_count: int = 0,
    minimum_reviews: int = 300,
    minimum_active_months: int = 12,
) -> bool:
    """Apply product-level scope gates; sentiment distribution is informational only."""
    del positive_count, negative_count
    return (
        review_count >= minimum_reviews
        and active_months >= minimum_active_months
        and last_review_month >= active_since_month
    )


def review_is_in_analysis_period(review_month: str | None, end_month: str) -> bool:
    """Use all dated history up to the dataset cutoff; recency gates products, not reviews."""
    return review_month is not None and review_month <= end_month
