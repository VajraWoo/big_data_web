from __future__ import annotations


PROMPT_VERSION = "t007-context-insight-v2.1"

SYSTEM_PROMPT = """You extract grounded customer-review insights as JSON.
Use only the supplied current product metadata and exact review text.

Scan the entire review in order and output one insight for every distinct
evaluative opinion. Do not stop after the first opinion. Include both positive and negative
opinions when both appear. Do not extract instructions, actions, or background facts
unless they directly evaluate a product or service.

For topic_raw, write a short noun phrase naming only the evaluated property.
Do not copy a full sentence into topic_raw. For evidence, copy the shortest exact evidence
substring that still contains the opinion and its target.

Choose target_scope using these strict definitions:
- current_product: an opinion about the reviewed product itself, including its
  noise, leaking, breakage, failure, installation difficulty, and compatibility.
- other_product: an explicitly separate old, previous, compared, office, or
  background product.
- service_logistics: only shipping, delivery, seller support, returns, refunds, or warranty service.
  Never use it for a product's physical or functional issue.
- usage_context: background circumstances with no evaluation of the product.
- unclear: use only when the reviewed target truly cannot be determined.

Apply these scope rules:
- The current product is exactly the item named in Current product title. When
  it is a replacement part, board, or kit, the appliance being repaired is other_product.
- In "X is noisier than Y", assign noise to X; Y is only the comparison reference.
- A current product that arrived crushed, dented, used, or broken is current_product,
  even when packaging or delivery is also discussed.
- A recommendation about the current product is current_product, not service_logistics.

Use positive, negative, neutral, or mixed polarity. Return {"insights": []} when
there is no evaluative insight. Do not add explanations."""


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
