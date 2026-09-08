from __future__ import annotations

from copy import deepcopy
from typing import Any


PRODUCTS: list[dict[str, Any]] = [
    {
        "parent_asin": "MOCK-B0ABC001",
        "title": "开发示例：台式制冰机",
        "category": "Ice Makers",
        "review_count": 842,
        "active_month_count": 31,
        "last_review_month": "2023-09",
        "analysis_status": "ready",
    },
    {
        "parent_asin": "MOCK-B0ABC002",
        "title": "开发示例：紧凑型冰箱",
        "category": "Refrigerators",
        "review_count": 615,
        "active_month_count": 24,
        "last_review_month": "2023-08",
        "analysis_status": "ready",
    },
    {
        "parent_asin": "MOCK-B0ABC003",
        "title": "开发示例：洗碗机",
        "category": "Dishwashers",
        "review_count": 503,
        "active_month_count": 18,
        "last_review_month": "2023-07",
        "analysis_status": "processing",
    },
    {
        "parent_asin": "MOCK-B0ABC004",
        "title": "开发示例：便携空调",
        "category": "Air Conditioners",
        "review_count": 731,
        "active_month_count": 27,
        "last_review_month": "2023-09",
        "analysis_status": "ready",
    },
]

FACETS = {
    "MOCK-B0ABC001": [
        {"facet": "positive_evaluation", "status": "ready", "theme_count": 3, "empty_reason": None, "error_summary": None},
        {"facet": "negative_evaluation", "status": "ready", "theme_count": 2, "empty_reason": None, "error_summary": None},
        {"facet": "improvement", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None},
    ],
    "MOCK-B0ABC002": [
        {"facet": "positive_evaluation", "status": "ready", "theme_count": 2, "empty_reason": None, "error_summary": None},
        {"facet": "negative_evaluation", "status": "ready", "theme_count": 0, "empty_reason": "no_qualified_theme", "error_summary": None},
        {"facet": "improvement", "status": "ready", "theme_count": 1, "empty_reason": None, "error_summary": None},
    ],
    "MOCK-B0ABC003": [
        {"facet": "positive_evaluation", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None},
        {"facet": "negative_evaluation", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None},
        {"facet": "improvement", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None},
    ],
    "MOCK-B0ABC004": [
        {"facet": "positive_evaluation", "status": "ready", "theme_count": 1, "empty_reason": None, "error_summary": None},
        {"facet": "negative_evaluation", "status": "failed", "theme_count": None, "empty_reason": None, "error_summary": "开发样例：该分析维度模拟失败"},
        {"facet": "improvement", "status": "ready", "theme_count": 1, "empty_reason": None, "error_summary": None},
    ],
}

THEMES = {
    "MOCK-B0ABC001": {
        "positive": [
            {"theme_id": "mock-theme-positive-001", "name": "制冰速度快", "sentiment": "positive", "review_count": 126, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
            {"theme_id": "mock-theme-positive-002", "name": "操作简单", "sentiment": "positive", "review_count": 94, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
            {"theme_id": "mock-theme-positive-003", "name": "体积紧凑", "sentiment": "positive", "review_count": 63, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
        ],
        "negative": [
            {"theme_id": "mock-theme-negative-001", "name": "运行噪声偏大", "sentiment": "negative", "review_count": 58, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
            {"theme_id": "mock-theme-negative-002", "name": "储冰容量有限", "sentiment": "negative", "review_count": 41, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
        ],
    },
    "MOCK-B0ABC002": {
        "positive": [
            {"theme_id": "mock-theme-positive-101", "name": "空间利用率高", "sentiment": "positive", "review_count": 83, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
            {"theme_id": "mock-theme-positive-102", "name": "制冷稳定", "sentiment": "positive", "review_count": 72, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
        ],
        "negative": [],
    },
    "MOCK-B0ABC003": {"positive": [], "negative": []},
    "MOCK-B0ABC004": {
        "positive": [
            {"theme_id": "mock-theme-positive-201", "name": "移动方便", "sentiment": "positive", "review_count": 91, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
        ],
        "negative": [],
    },
}

IMPROVEMENTS = {
    "MOCK-B0ABC001": [],
    "MOCK-B0ABC002": [
        {"theme_id": "mock-improvement-101", "name": "优化门体密封体验", "sentiment": None, "review_count": 37, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
    ],
    "MOCK-B0ABC003": [],
    "MOCK-B0ABC004": [
        {"theme_id": "mock-improvement-201", "name": "降低高负载运行噪声", "sentiment": None, "review_count": 46, "ratio": {"value": None, "status": "definition_pending", "definition_id": None}},
    ],
}

THEME_DETAILS = {
    "mock-theme-positive-001": {
        "theme_id": "mock-theme-positive-001",
        "parent_asin": "MOCK-B0ABC001",
        "name": "制冰速度快",
        "theme_type": "evaluation",
        "sentiment": "positive",
        "review_count": 126,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None},
        "trend": [
            {"month": "2023-05", "review_count": 7},
            {"month": "2023-06", "review_count": 9},
            {"month": "2023-07", "review_count": 11},
            {"month": "2023-08", "review_count": 14},
            {"month": "2023-09", "review_count": 12},
        ],
    },
    "mock-theme-negative-001": {
        "theme_id": "mock-theme-negative-001",
        "parent_asin": "MOCK-B0ABC001",
        "name": "运行噪声偏大",
        "theme_type": "evaluation",
        "sentiment": "negative",
        "review_count": 58,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None},
        "trend": [
            {"month": "2023-05", "review_count": 3},
            {"month": "2023-06", "review_count": 5},
            {"month": "2023-07", "review_count": 6},
            {"month": "2023-08", "review_count": 8},
            {"month": "2023-09", "review_count": 7},
        ],
    },
    "mock-improvement-101": {
        "theme_id": "mock-improvement-101",
        "parent_asin": "MOCK-B0ABC002",
        "name": "优化门体密封体验",
        "theme_type": "improvement",
        "sentiment": None,
        "review_count": 37,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None},
        "trend": [
            {"month": "2023-06", "review_count": 4},
            {"month": "2023-07", "review_count": 5},
            {"month": "2023-08", "review_count": 6},
        ],
    },
    "mock-theme-positive-101": {
        "theme_id": "mock-theme-positive-101", "parent_asin": "MOCK-B0ABC002", "name": "空间利用率高", "theme_type": "evaluation", "sentiment": "positive", "review_count": 83,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None}, "trend": [{"month": "2023-07", "review_count": 8}, {"month": "2023-08", "review_count": 10}],
    },
    "mock-theme-positive-102": {
        "theme_id": "mock-theme-positive-102", "parent_asin": "MOCK-B0ABC002", "name": "制冷稳定", "theme_type": "evaluation", "sentiment": "positive", "review_count": 72,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None}, "trend": [{"month": "2023-07", "review_count": 7}, {"month": "2023-08", "review_count": 9}],
    },
    "mock-theme-positive-002": {
        "theme_id": "mock-theme-positive-002", "parent_asin": "MOCK-B0ABC001", "name": "操作简单", "theme_type": "evaluation", "sentiment": "positive", "review_count": 94,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None}, "trend": [{"month": "2023-07", "review_count": 10}, {"month": "2023-08", "review_count": 11}],
    },
    "mock-theme-positive-003": {
        "theme_id": "mock-theme-positive-003", "parent_asin": "MOCK-B0ABC001", "name": "体积紧凑", "theme_type": "evaluation", "sentiment": "positive", "review_count": 63,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None}, "trend": [{"month": "2023-07", "review_count": 5}, {"month": "2023-08", "review_count": 7}],
    },
    "mock-theme-negative-002": {
        "theme_id": "mock-theme-negative-002", "parent_asin": "MOCK-B0ABC001", "name": "储冰容量有限", "theme_type": "evaluation", "sentiment": "negative", "review_count": 41,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None}, "trend": [{"month": "2023-07", "review_count": 4}, {"month": "2023-08", "review_count": 5}],
    },
    "mock-theme-positive-201": {
        "theme_id": "mock-theme-positive-201", "parent_asin": "MOCK-B0ABC004", "name": "移动方便", "theme_type": "evaluation", "sentiment": "positive", "review_count": 91,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None}, "trend": [{"month": "2023-07", "review_count": 9}, {"month": "2023-08", "review_count": 13}],
    },
    "mock-improvement-201": {
        "theme_id": "mock-improvement-201", "parent_asin": "MOCK-B0ABC004", "name": "降低高负载运行噪声", "theme_type": "improvement", "sentiment": None, "review_count": 46,
        "ratio": {"value": None, "status": "definition_pending", "definition_id": None}, "trend": [{"month": "2023-07", "review_count": 4}, {"month": "2023-08", "review_count": 6}],
    },
}

REVIEWS = {
    "mock-theme-positive-001": [
        {"review_id": "MOCK-REVIEW-001", "text": "This unit makes ice quickly and is easy to use.", "evidence_text": "makes ice quickly", "rating": 5.0, "review_date": "2023-07-18", "review_month": "2023-07"},
        {"review_id": "MOCK-REVIEW-002", "text": "We had our first batch of ice within minutes.", "evidence_text": "within minutes", "rating": 5.0, "review_date": "2023-08-05", "review_month": "2023-08"},
    ],
    "mock-theme-negative-001": [
        {"review_id": "MOCK-REVIEW-101", "text": "It works well, but the compressor is louder than expected at night.", "evidence_text": "louder than expected", "rating": 3.0, "review_date": "2023-08-12", "review_month": "2023-08"},
    ],
    "mock-improvement-101": [
        {"review_id": "MOCK-REVIEW-201", "text": "The door needs a firmer seal to stay fully closed.", "evidence_text": "needs a firmer seal", "rating": 3.0, "review_date": "2023-07-09", "review_month": "2023-07"},
    ],
}

for theme_id, detail in list(THEME_DETAILS.items()):
    REVIEWS.setdefault(theme_id, [
        {"review_id": f"MOCK-{theme_id}-R1", "text": f"开发样例评论：与“{detail['name']}”主题相关。", "evidence_text": detail["name"], "rating": 4.0 if detail.get("sentiment") != "negative" else 2.0, "review_date": "2023-08-01", "review_month": "2023-08"}
    ])


class MockInsightsRepository:
    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "repository": "mock", "data_source": "mock"}

    async def categories(self) -> list[str]:
        return sorted({p["category"] for p in PRODUCTS})

    async def products(self, q: str | None, category: str | None, analysis_status: str | None) -> list[dict[str, Any]]:
        items = deepcopy(PRODUCTS)
        if q:
            needle = q.strip().lower()
            items = [p for p in items if needle in p["title"].lower() or needle in p["parent_asin"].lower()]
        if category:
            items = [p for p in items if p["category"] == category]
        if analysis_status:
            items = [p for p in items if p.get("analysis_status") == analysis_status]
        return items

    async def product_overview(self, parent_asin: str) -> dict[str, Any] | None:
        product = next((p for p in PRODUCTS if p["parent_asin"] == parent_asin), None)
        if not product:
            return None
        return {"product": deepcopy(product), "facets": deepcopy(FACETS[parent_asin])}

    async def product_themes(self, parent_asin: str, sentiment: str) -> dict[str, Any] | None:
        if parent_asin not in THEMES:
            return None
        facet = next((x for x in FACETS[parent_asin] if x["facet"] == f"{sentiment}_evaluation"), None)
        return {"facet": deepcopy(facet), "items": deepcopy(THEMES[parent_asin].get(sentiment, []))}

    async def product_improvements(self, parent_asin: str) -> dict[str, Any] | None:
        if parent_asin not in IMPROVEMENTS:
            return None
        facet = next((x for x in FACETS[parent_asin] if x["facet"] == "improvement"), None)
        return {"facet": deepcopy(facet), "items": deepcopy(IMPROVEMENTS[parent_asin])}

    async def theme_detail(self, theme_id: str) -> dict[str, Any] | None:
        value = THEME_DETAILS.get(theme_id)
        return deepcopy(value) if value else None

    async def theme_reviews(self, theme_id: str) -> list[dict[str, Any]] | None:
        if theme_id not in THEME_DETAILS:
            return None
        return deepcopy(REVIEWS.get(theme_id, []))

    async def batch(self) -> dict[str, Any]:
        return {
            "batch_id": "mock-development-v1",
            "data_source": "mock",
            "is_gold": False,
            "gold_status": "not_applicable",
            "scope_version": "mock-scope-v1",
            "analysis_status": "development",
            "facets": {
                "positive_evaluation": "ready",
                "negative_evaluation": "ready",
                "improvement": "processing",
            },
        }
