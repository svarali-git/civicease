from app import ratelimit


def test_per_client_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    ratelimit.reset()
    codes = [client.post("/api/discover", json={"level": "national"}).status_code for _ in range(4)]
    assert codes[:3] == [503, 503, 503] and codes[3] == 429  # 503 = search not configured, but counted
    r = client.post("/api/discover", json={"level": "national"})
    assert r.json()["error"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
    # different clients are counted separately
    other = client.post("/api/discover", json={"level": "national"}, headers={"x-forwarded-for": "203.0.113.9"})
    assert other.status_code == 503


def test_health_and_config_are_never_limited(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    ratelimit.reset()
    assert all(client.get("/api/health").status_code == 200 for _ in range(5))
    assert all(client.get("/api/config").status_code == 200 for _ in range(5))


def test_global_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("RATE_LIMIT_GLOBAL_PER_MINUTE", "2")
    ratelimit.reset()
    codes = [client.post("/api/discover", json={"level": "national"},
                         headers={"x-forwarded-for": f"198.51.100.{i}"}).status_code for i in range(3)]
    assert codes == [503, 503, 429]


def test_address_is_hashed_not_stored():
    ratelimit.reset()
    key = ratelimit.client_key("203.0.113.7, 10.0.0.1", "10.0.0.1")
    assert "203" not in key and len(key) == 16
