import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field
from prophet import Prophet
from redis.asyncio import Redis
from sklearn.ensemble import IsolationForest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.features import extract_features

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://traffic:traffic-dev-only@localhost:5432/traffic")
MODEL_PATH = os.getenv("MODEL_PATH", "models/isolation_forest.joblib")
FEATURES = ["request_rate", "error_ratio", "endpoint_entropy", "mean_interarrival_ms", "mean_payload_bytes"]
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)
model: IsolationForest | None = None

def load_or_train():
    global model
    os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
    if os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
        return
    rng = np.random.default_rng(7)
    normal = np.column_stack([rng.normal(1.2, .45, 300), rng.beta(1, 35, 300), rng.normal(1.1, .6, 300), rng.normal(850, 250, 300), rng.normal(900, 350, 300)])
    model = IsolationForest(n_estimators=150, contamination=.04, random_state=7).fit(normal)
    joblib.dump(model, MODEL_PATH)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_or_train()
    app.state.redis = Redis.from_url(REDIS_URL, decode_responses=True)
    task = asyncio.create_task(score_recent_clients(app.state.redis))
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
    await app.state.redis.aclose()
    await engine.dispose()

app = FastAPI(title="Traffic ML Service", version="0.1.0", lifespan=lifespan)

class ScoreRequest(BaseModel):
    features: dict[str, float]

class ForecastRequest(BaseModel):
    values: list[float] = Field(min_length=2)
    horizon: int = Field(default=12, ge=1, le=96)
    frequency: str = "5min"

@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}

@app.post("/features")
async def features(events: list[dict]):
    return extract_features(events)

@app.post("/score")
async def score(payload: ScoreRequest):
    row = np.array([[float(payload.features.get(name, 0.0)) for name in FEATURES]])
    label = int(model.predict(row)[0])
    anomaly_score = float(-model.score_samples(row)[0])
    return {"anomaly": label == -1, "label": "anomaly" if label == -1 else "normal", "score": anomaly_score, "features": payload.features}

@app.post("/forecast")
async def forecast(payload: ForecastRequest):
    horizon = payload.horizon
    if len(payload.values) >= 10:
        start = datetime.utcnow() - timedelta(minutes=5 * len(payload.values))
        frame = pd.DataFrame({"ds": pd.date_range(start=start, periods=len(payload.values), freq=payload.frequency), "y": payload.values})
        model_forecast = Prophet(daily_seasonality=False, weekly_seasonality=False, yearly_seasonality=False, changepoint_prior_scale=0.05)
        model_forecast.fit(frame)
        future = model_forecast.make_future_dataframe(periods=horizon, freq=payload.frequency, include_history=False)
        result = model_forecast.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        return {"method": "prophet", "predictions": result.to_dict(orient="records")}
    values = np.asarray(payload.values, dtype=float)
    slope = (values[-1] - values[0]) / max(len(values) - 1, 1)
    predictions = [max(0.0, float(values[-1] + slope * (i + 1))) for i in range(horizon)]
    return {"method": "linear_fallback", "predictions": predictions}

async def score_recent_clients(redis: Redis):
    """Background scorer reads persisted traffic; it never runs in the gateway request path."""
    from sqlalchemy import text
    while True:
        try:
            async with Session() as session:
                result = await session.execute(text("SELECT client, route_name, status_code, EXTRACT(EPOCH FROM created_at) AS ts FROM traffic_events WHERE created_at > now() - interval '2 minutes' ORDER BY client, created_at"))
                grouped: dict[str, list[dict]] = {}
                for row in result.mappings():
                    grouped.setdefault(row["client"], []).append({"endpoint": row["route_name"], "status_code": row["status_code"], "timestamp": float(row["ts"]), "payload_bytes": 0})
            for client, events in grouped.items():
                features_row = extract_features(events)
                values = np.array([[features_row[key] for key in FEATURES]])
                anomaly = bool(model.predict(values)[0] == -1)
                score_value = float(-model.score_samples(values)[0])
                await redis.xadd("ml:scores", {"client": client, "anomaly": str(anomaly).lower(), "score": score_value, "features": str(features_row)}, maxlen=10000, approximate=True)
                await redis.set(f"ml:score:{client}", "1" if anomaly else "0", ex=120)
        except Exception:
            pass
        await asyncio.sleep(30)
