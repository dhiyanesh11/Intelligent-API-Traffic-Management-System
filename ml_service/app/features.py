"""Windowed client behavior features for anomaly detection."""
from collections import Counter
from datetime import datetime
import math

def extract_features(events: list[dict]) -> dict[str, float]:
    if not events:
        return {"request_rate": 0.0, "error_ratio": 0.0, "endpoint_entropy": 0.0, "mean_interarrival_ms": 0.0, "mean_payload_bytes": 0.0}
    ordered = sorted(events, key=lambda event: event.get("timestamp", 0))
    statuses = [int(e.get("status_code", 200)) for e in ordered]
    endpoints = [str(e.get("endpoint", "unknown")) for e in ordered]
    times = [float(e.get("timestamp", i)) for i, e in enumerate(ordered)]
    duration = max(times[-1] - times[0], 1.0)
    counts = Counter(endpoints)
    total = len(endpoints)
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
    gaps = [(b - a) * 1000 for a, b in zip(times, times[1:])]
    return {
        "request_rate": total / duration,
        "error_ratio": sum(status >= 500 for status in statuses) / total,
        "endpoint_entropy": entropy,
        "mean_interarrival_ms": sum(gaps) / len(gaps) if gaps else 0.0,
        "mean_payload_bytes": sum(float(e.get("payload_bytes", 0)) for e in ordered) / total,
    }
