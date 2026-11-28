from __future__ import annotations

from rtfs.api.server import (
    _parse_api_keys,
    _render_prometheus_metrics,
    _SlidingWindowLimiter,
    _verify_api_key,
)


def test_parse_and_verify_api_keys() -> None:
    keys = _parse_api_keys("key-1, key-2 , ")
    assert keys == {"key-1", "key-2"}
    assert _verify_api_key("key-1", keys) is True
    assert _verify_api_key("wrong", keys) is False
    assert _verify_api_key(None, keys) is False
    # Empty key set disables auth
    assert _verify_api_key(None, set()) is True


def test_sliding_window_limiter_enforces_quota() -> None:
    limiter = _SlidingWindowLimiter(max_requests=2, window_seconds=60.0)
    assert limiter.allow("1.2.3.4", now=100.0) is True
    assert limiter.allow("1.2.3.4", now=101.0) is True
    assert limiter.allow("1.2.3.4", now=102.0) is False
    # Different client is unaffected
    assert limiter.allow("5.6.7.8", now=102.0) is True
    # Window expires
    assert limiter.allow("1.2.3.4", now=161.0) is True


def test_render_prometheus_metrics_format() -> None:
    text = _render_prometheus_metrics({("GET", "/health", 200): 3}, rate_limited=1)
    assert "# TYPE rtfs_http_requests_total counter" in text
    assert 'rtfs_http_requests_total{method="GET",path="/health",status="200"} 3' in text
    assert "rtfs_http_rate_limited_total 1" in text


def test_api_security_edge_cases() -> None:
    assert _parse_api_keys(None) == set()
    unlimited = _SlidingWindowLimiter(max_requests=0)
    assert unlimited.allow("1.2.3.4") is True
