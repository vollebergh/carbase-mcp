import json
import os
import time

from carbase_mcp.cache import DAY, DiskCache, ttl_for


def test_ttl_per_kind():
    assert ttl_for("/auto/1/golf/") == 30 * DAY
    assert ttl_for("/carbase/?format=json") == 7 * DAY
    assert ttl_for("/carbase/toyota/?format=json") == 7 * DAY
    assert ttl_for("/carbase/toyota/rav4/?format=json") == DAY
    assert ttl_for("/carbase/toyota/?brandstof=diesel&format=json") == DAY


def test_round_trip_and_permissions(tmp_path):
    root = tmp_path / "c"
    cache = DiskCache(root)
    cache.put("/a", "body")
    assert cache.get("/a", DAY) == "body"
    assert root.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in root.iterdir())
    assert cache.get("/b", DAY) is None


def test_expiry_uses_shortest_of_ttl_and_max_age(tmp_path):
    cache = DiskCache(tmp_path, max_days=2)
    cache.put("/a", "x")
    old = time.time() - 3 * DAY
    for p in tmp_path.iterdir():
        os.utime(p, (old, old))
    assert cache.get("/a", 30 * DAY) is None  # older than max_days
    cache.put("/b", "y")
    assert cache.get("/b", 0) is None  # ttl 0


def test_corrupt_or_foreign_entries_are_misses(tmp_path):
    cache = DiskCache(tmp_path)
    cache.put("/a", "x")
    (entry,) = tmp_path.iterdir()
    entry.write_text(json.dumps({"key": "/other", "body": "evil"}))
    assert cache.get("/a", DAY) is None
    entry.write_text("{not json")
    assert cache.get("/a", DAY) is None


def test_evicts_oldest_beyond_size_and_age(tmp_path):
    cache = DiskCache(tmp_path, max_mb=0.00035)  # 350 bytes: three entries of ~105 bytes
    for i in range(5):
        cache.put(f"/p{i}", "x" * 80)
        t = time.time() - (10 - i)
        os.utime(cache._file(f"/p{i}"), (t, t))
    cache.save_cookies([{"name": "authId", "value": "v", "domain": ".autoweek.nl", "path": "/"}])
    cache.put("/p5", "x" * 80)
    kept = [i for i in range(6) if cache.get(f"/p{i}", DAY)]
    assert kept == [3, 4, 5]
    assert cache.load_cookies()[0]["name"] == "authId"  # never evicted


def test_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CARBASE_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("CARBASE_MCP_CACHE_MB", "5")
    monkeypatch.setenv("CARBASE_MCP_CACHE_DAYS", "onzin")
    cache = DiskCache.from_env()
    assert cache.root == tmp_path and cache.max_bytes == 5_000_000 and cache.max_age == 30 * DAY
    monkeypatch.setenv("CARBASE_MCP_CACHE_MB", "0")
    assert DiskCache.from_env() is None


def test_unwritable_dir_only_costs_the_cache(tmp_path):
    (tmp_path / "file").write_text("")
    cache = DiskCache(tmp_path / "file" / "sub")  # parent is a file
    cache.put("/a", "x")
    assert cache.get("/a", DAY) is None


def test_shared_or_foreign_dir_disables_cache(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    cache = DiskCache(shared)
    cache.put("/a", "x")
    assert cache.get("/a", DAY) is None and list(shared.iterdir()) == []
    target = tmp_path / "real"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target)
    assert DiskCache(link).get("/a", DAY) is None
    DiskCache(link).put("/a", "x")
    assert list(target.iterdir()) == []


def test_tmp_file_symlink_is_not_followed(tmp_path):
    cache = DiskCache(tmp_path / "c")
    cache.put("/warmup", "x")
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    cache._file("/a").with_suffix(f".{os.getpid()}.tmp").symlink_to(victim)
    cache.put("/a", "x")
    assert victim.read_text() == "keep"
