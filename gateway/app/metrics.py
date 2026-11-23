from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

REQUESTS = Counter("gateway_requests_total", "Gateway requests", ["method", "status"])
LATENCY = Histogram("gateway_request_duration_seconds", "Gateway request duration", ["method"], buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
BLOCKED = Counter("gateway_rate_limited_total", "Requests blocked by rate limit")
CIRCUIT = Gauge("gateway_circuit_open", "Circuit breaker open state", ["backend"])

def metrics_response():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
