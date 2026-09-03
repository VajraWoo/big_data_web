from contextlib import asynccontextmanager
import os
from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncMongoClient(
        os.environ.get("MONGODB_URI", "mongodb://mongodb:27017"),
        serverSelectionTimeoutMS=2000, connectTimeoutMS=2000, socketTimeoutMS=2000,
    )
    app.state.mongo = client
    try:
        yield
    finally:
        await client.close()


app = FastAPI(title="Merchant Insights — Environment Check", version="0.1.0", lifespan=lifespan)


class Health(BaseModel):
    service: Literal["ok", "degraded"]
    mongodb: Literal["ok", "unavailable"]
    active_run: str | None = None


def get_database(request: Request):
    return request.app.state.mongo.admin


@app.get("/healthz")
def liveness():
    return {"status": "alive"}


@app.get("/api/v1/health", response_model=Health, responses={503: {"model": Health}})
async def health(database=Depends(get_database)):
    try:
        result = await database.command("ping")
        if result.get("ok") != 1:
            raise PyMongoError("Database ping was not successful")
    except PyMongoError:
        return JSONResponse(
            status_code=503,
            content=Health(service="degraded", mongodb="unavailable").model_dump(),
        )
    return Health(service="ok", mongodb="ok")
