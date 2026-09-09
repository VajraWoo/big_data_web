import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


@pytest.fixture(scope="module")
def gold_selection():
    products_response = client.get(
        "/api/v1/products",
        params={"page": 1, "page_size": 100},
    )
    assert products_response.status_code == 200

    products = products_response.json()["data"]["items"]
    assert products

    for product in products:
        parent_asin = product["parent_asin"]

        for sentiment in ("positive", "negative"):
            themes_response = client.get(
                f"/api/v1/products/{parent_asin}/themes",
                params={"sentiment": sentiment},
            )
            assert themes_response.status_code == 200

            themes = themes_response.json()["data"]["items"]
            if themes:
                return {
                    "products_response": products_response,
                    "product": product,
                    "sentiment": sentiment,
                    "theme": themes[0],
                }

    pytest.fail("The current Gold dataset contains no positive or negative themes")


def test_health_reports_gold_repository():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["repository"] == "gold"
    assert body["data"]["data_source"] == "t010_gold+t011_gold"
    assert body["data"]["t011_group_count"] == 7734
    assert body["data"]["polarity_override_count"] == 13
    assert body["meta"]["is_gold"] is True
    assert body["meta"]["data_source"] == "gold"


def test_products_returns_formal_gold_products(gold_selection):
    response = gold_selection["products_response"]
    body = response.json()

    assert body["pagination"]["total_items"] > 0
    assert gold_selection["product"]["parent_asin"]
    assert gold_selection["product"]["analysis_status"] == "ready"
    assert body["meta"]["is_gold"] is True


def test_product_overview_and_themes_are_available(gold_selection):
    parent_asin = gold_selection["product"]["parent_asin"]

    overview = client.get(f"/api/v1/products/{parent_asin}/overview")
    assert overview.status_code == 200
    assert overview.json()["data"]["product"]["parent_asin"] == parent_asin

    themes = client.get(
        f"/api/v1/products/{parent_asin}/themes",
        params={"sentiment": gold_selection["sentiment"]},
    )
    assert themes.status_code == 200
    assert themes.json()["data"]["items"]


def test_theme_detail_and_reviews_use_dynamic_gold_theme(gold_selection):
    theme_id = gold_selection["theme"]["theme_id"]

    detail = client.get(f"/api/v1/themes/{theme_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["theme_id"] == theme_id
    assert detail.json()["meta"]["is_gold"] is True

    reviews = client.get(f"/api/v1/themes/{theme_id}/reviews")
    assert reviews.status_code == 200
    assert reviews.json()["pagination"]["total_items"] > 0
    assert reviews.json()["data"]["items"]


def test_product_improvements_use_t011_gold(gold_selection):
    products = gold_selection["products_response"].json()["data"]["items"]

    for product in products:
        parent_asin = product["parent_asin"]
        response = client.get(f"/api/v1/products/{parent_asin}/improvements")
        assert response.status_code == 200

        items = response.json()["data"]["items"]
        if items:
            assert items[0]["taxonomy_id"]
            assert items[0]["improvement_suggestion"]
            assert response.json()["meta"]["data_source"] == "gold"
            return

    pytest.fail("The current T011 Gold dataset contains no improvement suggestions")


def test_not_found_uses_error_envelope():
    response = client.get("/api/v1/themes/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "THEME_NOT_FOUND"
    assert body["error"]["request_id"].startswith("req_")
