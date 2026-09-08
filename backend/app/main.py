from math import ceil
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.repositories import InsightsRepository, MockInsightsRepository

app = FastAPI(title="Merchant Review Insights API", version="0.2.0")
app.state.repository = MockInsightsRepository()


def repository(request: Request) -> InsightsRepository:
    return request.app.state.repository


def meta(repo: InsightsRepository) -> dict:
    return {"data_source": repo.data_source, "is_gold": repo.is_gold, "batch_id": repo.batch_id}


def paginated(items: list[dict], number: int, size: int, repo: InsightsRepository) -> dict:
    total = len(items)
    start = (number - 1) * size
    return {"data": {"items": items[start:start + size]}, "pagination": {"page": number, "page_size": size, "total_items": total, "total_pages": ceil(total / size) if total else 0}, "meta": meta(repo)}


def not_found(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {"code": code, "message": message, "details": None, "request_id": f"req_{uuid4().hex}"}})


@app.get("/healthz")
async def liveness(): return {"status": "alive"}


@app.get("/api/v1/health")
async def health(repo: InsightsRepository = Depends(repository)):
    return {"data": {"service": "ok", "repository": "ok", "data_source": repo.data_source, "is_gold": repo.is_gold}, "meta": meta(repo)}


@app.get("/api/v1/catalog/categories")
async def categories(repo: InsightsRepository = Depends(repository)):
    return {"data": {"items": await repo.categories()}, "meta": meta(repo)}


@app.get("/api/v1/products")
async def products(q: str = "", category: str | None = None, analysis_status: str | None = None, page_number: int = Query(1, alias="page", ge=1), page_size: int = Query(20, ge=1, le=100), repo: InsightsRepository = Depends(repository)):
    items = await repo.products()
    query = q.strip().casefold()
    if query: items = [item for item in items if query in item["title"].casefold() or query in item["parent_asin"].casefold()]
    if category: items = [item for item in items if item["category"] == category]
    if analysis_status: items = [item for item in items if item["analysis_status"] == analysis_status]
    return paginated(items, page_number, page_size, repo)


@app.get("/api/v1/products/{parent_asin}/overview")
async def overview(parent_asin: str, repo: InsightsRepository = Depends(repository)):
    data = await repo.overview(parent_asin)
    return not_found("PRODUCT_NOT_FOUND", "未找到该正式范围商品") if data is None else {"data": data, "meta": meta(repo)}


@app.get("/api/v1/products/{parent_asin}/themes")
async def themes(parent_asin: str, sentiment: str = Query(..., pattern="^(positive|negative)$"), repo: InsightsRepository = Depends(repository)):
    if await repo.overview(parent_asin) is None: return not_found("PRODUCT_NOT_FOUND", "未找到该正式范围商品")
    return {"data": await repo.themes(parent_asin, sentiment=sentiment), "meta": meta(repo)}


@app.get("/api/v1/products/{parent_asin}/improvements")
async def improvements(parent_asin: str, repo: InsightsRepository = Depends(repository)):
    if await repo.overview(parent_asin) is None: return not_found("PRODUCT_NOT_FOUND", "未找到该正式范围商品")
    return {"data": await repo.themes(parent_asin, improvement=True), "meta": meta(repo)}


@app.get("/api/v1/themes/{theme_id}")
async def theme(theme_id: str, repo: InsightsRepository = Depends(repository)):
    data = await repo.theme(theme_id)
    return not_found("THEME_NOT_FOUND", "未找到该主题") if data is None else {"data": data, "meta": meta(repo)}


@app.get("/api/v1/themes/{theme_id}/reviews")
async def theme_reviews(theme_id: str, page_number: int = Query(1, alias="page", ge=1), page_size: int = Query(20, ge=1, le=100), repo: InsightsRepository = Depends(repository)):
    items = await repo.theme_reviews(theme_id)
    return not_found("THEME_NOT_FOUND", "未找到该主题") if items is None else paginated(items, page_number, page_size, repo)


@app.get("/api/v1/analysis/batch")
async def batch(repo: InsightsRepository = Depends(repository)):
    return {"data": await repo.batch(), "meta": meta(repo)}
