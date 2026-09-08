from __future__ import annotations

from math import ceil
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .repositories import GoldInsightsRepository

app = FastAPI(title="Merchant Review Insights API", version="0.1.0")
repo = GoldInsightsRepository()


async def meta() -> dict[str, Any]:
    batch = await repo.batch()

    return {
        "data_source": batch.get(
            "data_source",
            "t010_gold",
        ),
        "is_gold": batch.get(
            "is_gold",
            True,
        ),
        "batch_id": batch.get(
            "batch_id",
            "t010-aggregation-20260908-v1-duckdb",
        ),
        "generated_at": batch.get(
            "generated_at",
        ),
        "gold_status": batch.get(
            "gold_status",
            "verified",
        ),
    }


async def envelope(data: Any) -> dict[str, Any]:
    return {
        "data": data,
        "meta": await meta(),
    }


async def paged(
    items: list[dict[str, Any]],
    page: int,
    page_size: int,
) -> dict[str, Any]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "data": {
            "items": items[start:end],
        },
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": ceil(total / page_size) if total else 0,
        },
        "meta": await meta(),
    }


@app.exception_handler(HTTPException)
async def http_error_handler(
    request: Request,
    exc: HTTPException,
):
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {
            "code": "HTTP_ERROR",
            "message": str(exc.detail),
            "details": None,
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                **detail,
                "request_id": f"req_{uuid4().hex[:12]}",
            }
        },
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
    }


@app.get("/api/v1/health")
async def health():
    return await envelope(
        await repo.health()
    )


@app.get("/api/v1/catalog/categories")
async def categories():
    return await envelope(
        {
            "items": await repo.categories(),
        }
    )


@app.get("/api/v1/products")
async def products(
    q: str | None = None,
    category: str | None = None,
    analysis_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items = await repo.products(
        q,
        category,
        analysis_status,
    )

    return await paged(
        items,
        page,
        page_size,
    )


@app.get("/api/v1/products/{parent_asin}/overview")
async def product_overview(
    parent_asin: str,
):
    data = await repo.product_overview(
        parent_asin
    )

    if data is None:
        raise HTTPException(
            404,
            {
                "code": "PRODUCT_NOT_FOUND",
                "message": "未找到该正式范围商品",
                "details": None,
            },
        )

    return await envelope(data)


@app.get("/api/v1/products/{parent_asin}/themes")
async def product_themes(
    parent_asin: str,
    sentiment: Literal[
        "positive",
        "negative",
    ],
):
    data = await repo.product_themes(
        parent_asin,
        sentiment,
    )

    if data is None:
        raise HTTPException(
            404,
            {
                "code": "PRODUCT_NOT_FOUND",
                "message": "未找到该正式范围商品",
                "details": None,
            },
        )

    return await envelope(data)


@app.get("/api/v1/products/{parent_asin}/improvements")
async def product_improvements(
    parent_asin: str,
    source: str | None = None,
):
    _ = source

    data = await repo.product_improvements(
        parent_asin
    )

    if data is None:
        raise HTTPException(
            404,
            {
                "code": "PRODUCT_NOT_FOUND",
                "message": "未找到该正式范围商品",
                "details": None,
            },
        )

    return await envelope(data)


@app.get("/api/v1/themes/{theme_id}")
async def theme_detail(
    theme_id: str,
):
    data = await repo.theme_detail(
        theme_id
    )

    if data is None:
        raise HTTPException(
            404,
            {
                "code": "THEME_NOT_FOUND",
                "message": "未找到该主题",
                "details": None,
            },
        )

    return await envelope(data)


@app.get("/api/v1/themes/{theme_id}/reviews")
async def theme_reviews(
    theme_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = "date_desc",
):
    items = await repo.theme_reviews(
        theme_id
    )

    if items is None:
        raise HTTPException(
            404,
            {
                "code": "THEME_NOT_FOUND",
                "message": "未找到该主题",
                "details": None,
            },
        )

    if sort == "date_desc":
        items = sorted(
            items,
            key=lambda x: x.get("review_date") or "",
            reverse=True,
        )

    return await paged(
        items,
        page,
        page_size,
    )


@app.get("/api/v1/analysis/batch")
async def analysis_batch():
    return await envelope(
        await repo.batch()
    )