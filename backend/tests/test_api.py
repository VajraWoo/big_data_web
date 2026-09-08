from fastapi.testclient import TestClient

from app.main import app


def test_health_identifies_mock_repository_as_development_data():
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"] == {"service": "ok", "repository": "ok", "data_source": "mock", "is_gold": False}


def test_products_support_search_category_filter_and_pagination():
    with TestClient(app) as client:
        response = client.get("/api/v1/products", params={"q": "制冰", "category": "Ice Makers", "page": 1, "page_size": 1})
    body = response.json()
    assert response.status_code == 200
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["parent_asin"].startswith("MOCK-")
    assert body["pagination"] == {"page": 1, "page_size": 1, "total_items": 1, "total_pages": 1}
    assert body["meta"]["is_gold"] is False


def test_overview_exposes_ready_empty_processing_and_failed_facets():
    with TestClient(app) as client:
        ready = client.get("/api/v1/products/MOCK-ICE-001/overview").json()
        processing = client.get("/api/v1/products/MOCK-WASH-002/overview").json()
        failed = client.get("/api/v1/products/MOCK-FRIDGE-003/overview").json()
    assert ready["data"]["facets"][1]["empty_reason"] == "no_qualified_theme"
    assert processing["data"]["facets"][2]["status"] == "processing"
    assert failed["data"]["facets"][1]["status"] == "failed"


def test_theme_detail_and_reviews_use_unique_review_counts_and_pagination():
    with TestClient(app) as client:
        detail = client.get("/api/v1/themes/mock-positive-speed").json()
        reviews = client.get("/api/v1/themes/mock-positive-speed/reviews", params={"page": 1, "page_size": 1}).json()
    assert detail["data"]["review_count"] == 3
    assert detail["data"]["ratio"]["status"] == "definition_pending"
    assert reviews["pagination"]["total_items"] == 3
    assert reviews["data"]["items"][0]["review_id"] == "MOCK-REVIEW-003"


def test_not_found_uses_stable_error_shape():
    with TestClient(app) as client:
        response = client.get("/api/v1/products/UNKNOWN/overview")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert response.json()["error"]["request_id"]
