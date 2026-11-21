import json
import logging
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from . import db
from .routes import router

logger = logging.getLogger('inbox')
logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app):
    db.initialize()
    yield

app = FastAPI(title="AI Knowledge Inbox", lifespan=lifespan)
app.include_router(router)

@app.middleware('http')
async def log_request(request: Request, call_next):
    request_id = str(uuid4())
    started = perf_counter()
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    logger.info(json.dumps({'event': 'request', 'request_id': request_id,
        'method': request.method, 'path': request.url.path, 'status': response.status_code,
        'duration_ms': round((perf_counter() - started) * 1000, 2)}))
    return response

@app.exception_handler(sqlite3.Error)
async def database_error(request: Request, exc):
    logger.error(json.dumps({'event': 'database_error', 'error_type': type(exc).__name__}))
    return JSONResponse(status_code=503, content={'detail': 'Storage is temporarily unavailable. Please try again.'})


@app.get("/health")
async def health():
    return {"status": "ok"}
