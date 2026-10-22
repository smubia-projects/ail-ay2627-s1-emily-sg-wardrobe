"""SG Wardrobe API (Cloud Run). API-only: the static site is hosted on Vercel.

Routes
  GET  /api/health   liveness probe
  GET  /api/style    {"ai": bool} so the page can switch AI features off cleanly
  POST /api/style    one of four styling tasks, prompt built server-side
  POST /api/product  read one public shop page for the size checker
"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app import product_reader
from app.llm import LLMError, ai_enabled, complete_json
from app.prompts import SYSTEM, StyleRequest, build_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sg-wardrobe")

MAX_BODY_BYTES = 100_000
STYLE_ADAPTER = TypeAdapter(StyleRequest)

app = FastAPI(title="SG Wardrobe API", docs_url=None, redoc_url=None, openapi_url=None)

origins = [o.strip().rstrip("/") for o in os.getenv("CORS_ORIGINS", "http://localhost:8000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "error": message}, status_code=status, headers={"Cache-Control": "no-store"})


async def _read_json(request: Request) -> bytes:
    raw = await request.body()
    if not raw or len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail={"code": "request_too_large", "error": "Request too large"})
    return raw


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/style")
def style_status():
    return JSONResponse({"ai": ai_enabled()}, headers={"Cache-Control": "no-store"})


@app.post("/api/style")
async def style(request: Request):
    raw = await _read_json(request)
    try:
        req = STYLE_ADAPTER.validate_json(raw)
    except ValidationError:
        return _error(400, "bad_request", "Invalid request")
    if not ai_enabled():
        return _error(501, "misconfigured", "The AI service is not configured")
    try:
        data = await complete_json(SYSTEM, build_prompt(req))
    except LLMError as e:
        return _error(e.status, e.code, e.message)
    # null data means the model did not answer in JSON twice; the page asks again or shows a retry message
    return JSONResponse({"data": data}, headers={"Cache-Control": "no-store"})


class ProductRequest(BaseModel):
    url: str = Field(min_length=1, max_length=600)


@app.post("/api/product")
async def product(request: Request):
    raw = await _read_json(request)
    try:
        url = ProductRequest.model_validate_json(raw).url.strip()
    except ValidationError:
        return _error(400, "bad_request", "Invalid URL")
    try:
        status, result = await asyncio.to_thread(product_reader.read_product, url)
    except Exception:
        logger.exception("Product-page reading failed")
        return _error(502, "unreachable", "Could not read the shop page")
    return JSONResponse(result, status_code=status, headers={"Cache-Control": "no-store"})


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    # keep the shared engine's {"detail": {...}} shape (the 429 CTA reads detail.queries_used)
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    body = {"detail": detail}
    if "code" in detail:
        body.update(code=detail["code"], error=detail.get("error", ""))
    return JSONResponse(body, status_code=exc.status_code, headers={"Cache-Control": "no-store"})
