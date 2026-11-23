from ml_service.app.features import extract_features

def test_extract_features_counts_rate_errors_and_entropy():
    events = [
        {"timestamp": 1.0, "status_code": 200, "endpoint": "/a", "payload_bytes": 100},
        {"timestamp": 2.0, "status_code": 503, "endpoint": "/b", "payload_bytes": 300},
        {"timestamp": 3.0, "status_code": 200, "endpoint": "/a", "payload_bytes": 200},
    ]
    features = extract_features(events)
    assert features["request_rate"] == 1.5
    assert features["error_ratio"] == 1 / 3
    assert features["endpoint_entropy"] > 0
    assert features["mean_interarrival_ms"] == 1000
    assert features["mean_payload_bytes"] == 200

def test_empty_window_has_zeroed_features():
    assert all(value == 0 for value in extract_features([]).values())
