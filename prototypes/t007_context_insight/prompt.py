from __future__ import annotations


PROMPT_VERSION = "t007-context-insight-v1"

SYSTEM_PROMPT = """You extract grounded customer-review insights as JSON.
Use only the supplied current product metadata and exact review text.
For every distinct product topic, copy an exact continuous evidence substring.
Classify its scope as current_product, other_product, service_logistics,
usage_context, or unclear. Do not transfer faults from old, compared, office,
or background products to the current product. Use positive, negative, neutral,
or mixed polarity. If exact evidence appears more than once, include its zero-based
evidence_occurrence. Return {\"insights\": []} when there is no product insight.
Do not add explanations."""


def build_messages(
    *, product_title: str, product_category: str, review_text: str
) -> list[dict[str, str]]:
    user = (
        f"Current product title: {product_title}\n"
        f"Current product category: {product_category}\n"
        "Review text (copy evidence exactly from between the markers):\n"
        f"<review>{review_text}</review>"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
