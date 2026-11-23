import asyncio
import os
import random
from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title=os.getenv("SERVICE_NAME", "demo-backend"))
SERVICE_NAME = os.getenv("SERVICE_NAME", "demo-backend")

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def echo(path: str, request: Request):
    delay_ms = max(0, min(int(request.headers.get("x-demo-delay-ms", os.getenv("DEFAULT_DELAY_MS", "0"))), 30000))
    error_rate = max(0.0, min(float(request.headers.get("x-demo-error-rate", os.getenv("ERROR_RATE", "0"))), 1.0))
    await asyncio.sleep(delay_ms / 1000)
    if random.random() < error_rate:
        raise HTTPException(status_code=503, detail="simulated backend failure")
    return {"service": SERVICE_NAME, "path": f"/{path}", "method": request.method,
            "query": dict(request.query_params),
            "body": (await request.body()).decode("utf-8", errors="replace")}
