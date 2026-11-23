from fastapi import FastAPI

app = FastAPI(title="Intelligent API Traffic Gateway", version="0.1.0")

@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "gateway"}
