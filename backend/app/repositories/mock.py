from copy import deepcopy

FACETS = {
    "MOCK-ICE-001": [
        {"facet": "positive_evaluation", "status": "ready", "theme_count": 1, "empty_reason": None, "error_summary": None},
        {"facet": "negative_evaluation", "status": "ready", "theme_count": 0, "empty_reason": "no_qualified_theme", "error_summary": None},
        {"facet": "improvement", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None}],
    "MOCK-WASH-002": [
        {"facet": "positive_evaluation", "status": "ready", "theme_count": 1, "empty_reason": None, "error_summary": None},
        {"facet": "negative_evaluation", "status": "ready", "theme_count": 1, "empty_reason": None, "error_summary": None},
        {"facet": "improvement", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None}],
    "MOCK-FRIDGE-003": [
        {"facet": "positive_evaluation", "status": "ready", "theme_count": 0, "empty_reason": "no_qualified_theme", "error_summary": None},
        {"facet": "negative_evaluation", "status": "failed", "theme_count": None, "empty_reason": None, "error_summary": "开发样例：该维度处理失败"},
        {"facet": "improvement", "status": "ready", "theme_count": 1, "empty_reason": None, "error_summary": None}],
    "MOCK-OVEN-004": [
        {"facet": "positive_evaluation", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None},
        {"facet": "negative_evaluation", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None},
        {"facet": "improvement", "status": "processing", "theme_count": None, "empty_reason": None, "error_summary": None}],
}

PRODUCTS = [
    {"parent_asin": "MOCK-ICE-001", "title": "开发示例：台式制冰机", "category": "Ice Makers", "review_count": 842, "active_month_count": 31, "last_review_month": "2023-09", "analysis_status": "processing"},
    {"parent_asin": "MOCK-WASH-002", "title": "开发示例：便携洗衣机", "category": "Washing Machines", "review_count": 615, "active_month_count": 24, "last_review_month": "2023-09", "analysis_status": "processing"},
    {"parent_asin": "MOCK-FRIDGE-003", "title": "开发示例：迷你冰箱", "category": "Refrigerators", "review_count": 477, "active_month_count": 19, "last_review_month": "2023-08", "analysis_status": "failed"},
    {"parent_asin": "MOCK-OVEN-004", "title": "开发示例：台式烤箱", "category": "Ovens", "review_count": 391, "active_month_count": 16, "last_review_month": "2023-09", "analysis_status": "processing"},
]

PENDING_RATIO = {"value": None, "status": "definition_pending", "definition_id": None}
THEMES = {
    "mock-positive-speed": {"theme_id": "mock-positive-speed", "parent_asin": "MOCK-ICE-001", "name": "制冰速度快", "theme_type": "evaluation", "sentiment": "positive", "review_count": 3, "ratio": PENDING_RATIO, "trend": [{"month": month, "review_count": 1, "ratio": {"value": None, "status": "definition_pending"}} for month in ("2023-07", "2023-08", "2023-09")]},
    "mock-wash-simple": {"theme_id": "mock-wash-simple", "parent_asin": "MOCK-WASH-002", "name": "操作简单", "theme_type": "evaluation", "sentiment": "positive", "review_count": 1, "ratio": PENDING_RATIO, "trend": []},
    "mock-wash-noise": {"theme_id": "mock-wash-noise", "parent_asin": "MOCK-WASH-002", "name": "运行噪声偏大", "theme_type": "evaluation", "sentiment": "negative", "review_count": 1, "ratio": PENDING_RATIO, "trend": []},
    "mock-fridge-shelf": {"theme_id": "mock-fridge-shelf", "parent_asin": "MOCK-FRIDGE-003", "name": "改进搁板空间", "theme_type": "improvement", "sentiment": None, "review_count": 1, "ratio": PENDING_RATIO, "trend": []},
}

REVIEWS = {"mock-positive-speed": [
    {"review_id": "MOCK-REVIEW-003", "text": "Ice is ready quickly and the controls are simple.", "evidence_text": "Ice is ready quickly", "rating": 5.0, "review_date": "2023-09-12", "review_month": "2023-09"},
    {"review_id": "MOCK-REVIEW-002", "text": "It makes a batch much faster than expected.", "evidence_text": "much faster than expected", "rating": 5.0, "review_date": "2023-08-03", "review_month": "2023-08"},
    {"review_id": "MOCK-REVIEW-001", "text": "This unit makes ice quickly and is easy to use.", "evidence_text": "makes ice quickly", "rating": 5.0, "review_date": "2023-07-18", "review_month": "2023-07"}]}


class MockInsightsRepository:
    data_source, is_gold, batch_id = "mock", False, "mock-development-v1"

    async def categories(self): return sorted({item["category"] for item in PRODUCTS})
    async def products(self): return deepcopy(PRODUCTS)
    async def overview(self, parent_asin):
        product = next((item for item in PRODUCTS if item["parent_asin"] == parent_asin), None)
        return None if product is None else {"product": deepcopy(product), "facets": deepcopy(FACETS[parent_asin])}
    async def themes(self, parent_asin, sentiment=None, improvement=False):
        facet_name = "improvement" if improvement else f"{sentiment}_evaluation"
        facet = next(item for item in FACETS[parent_asin] if item["facet"] == facet_name)
        items = [deepcopy(item) for item in THEMES.values() if item["parent_asin"] == parent_asin and ((improvement and item["theme_type"] == "improvement") or (not improvement and item["theme_type"] == "evaluation" and item["sentiment"] == sentiment))]
        for item in items: item.pop("trend", None)
        return {"facet": deepcopy(facet), "items": items}
    async def theme(self, theme_id): return deepcopy(THEMES.get(theme_id))
    async def theme_reviews(self, theme_id): return deepcopy(REVIEWS.get(theme_id, [])) if theme_id in THEMES else None
    async def batch(self):
        return {"batch_id": self.batch_id, "data_source": self.data_source, "is_gold": False, "gold_status": "not_applicable", "scope_version": "mock-scope-v1", "analysis_status": "development", "formal_product_target": 139}
