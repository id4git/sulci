"""
tests/test_core.py
==================
Core Cache unit tests.
Uses SQLite backend — zero external dependencies beyond sentence-transformers.

Run:
    pip install "sulci[sqlite]" pytest
    pytest tests/ -v
"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sulci import Cache


@pytest.fixture
def cache(tmp_path):
    """Fresh SQLite-backed cache, isolated per test."""
    return Cache(
        backend         = "sqlite",
        threshold       = 0.85,
        embedding_model = "minilm",
        ttl_seconds     = None,
        db_path         = str(tmp_path / "test_db"),
    )


# ── Basic operations ──────────────────────────────────────────

class TestBasicOperations:

    def test_import(self):
        assert Cache is not None

    def test_version(self):
        import sulci
        assert hasattr(sulci, "__version__")
        assert sulci.__version__

    def test_repr(self, cache):
        assert "Cache" in repr(cache)
        assert "sqlite" in repr(cache)

    def test_miss_on_empty_cache(self, cache):
        result, sim = cache.get("What is Python?")
        assert result is None
        assert sim == 0.0

    def test_set_then_exact_get(self, cache):
        cache.set("What is Python?", "Python is a programming language.")
        result, sim = cache.get("What is Python?")
        assert result == "Python is a programming language."
        assert sim >= 0.99

    def test_semantic_hit(self, cache):
        """Paraphrase should hit the cache."""
        cache.set("What is Python?", "Python is a programming language.")
        result, sim = cache.get("Explain Python to me")
        assert result is not None, "Expected semantic cache hit for paraphrase"
        assert sim >= 0.85

    def test_semantic_miss_different_topic(self, cache):
        """Unrelated query should miss."""
        cache.set("What is Python?", "Python is a programming language.")
        result, sim = cache.get("What is the capital of France?")
        assert result is None

    def test_clear_empties_cache(self, cache):
        cache.set("What is Python?", "Python is a programming language.")
        cache.clear()
        result, _ = cache.get("What is Python?")
        assert result is None

    def test_multiple_entries(self, cache):
        cache.set("What is Python?",  "Python is a language.")
        cache.set("What is Docker?",  "Docker is a container platform.")
        cache.set("What is Kubernetes?", "K8s orchestrates containers.")

        r1, _ = cache.get("Tell me about Python")
        r2, _ = cache.get("Docker containers explained")
        assert r1 is not None
        assert r2 is not None

    def test_ttl_expiry(self, tmp_path):
        import time
        cache = Cache(
            backend     = "sqlite",
            threshold   = 0.85,
            ttl_seconds = 1,            # 1-second TTL
            db_path     = str(tmp_path / "ttl_db"),
        )
        cache.set("What is Python?", "Python is a language.")
        time.sleep(1.1)
        result, _ = cache.get("What is Python?")
        assert result is None, "Entry should have expired"


# ── cached_call ───────────────────────────────────────────────

class TestCachedCall:

    def test_miss_calls_llm(self, cache):
        calls = [0]
        def fake_llm(q): calls[0] += 1; return f"Answer: {q}"

        r = cache.cached_call("What is Python?", fake_llm)
        assert r["source"]    == "llm"
        assert r["cache_hit"] is False
        assert calls[0]       == 1

    def test_hit_skips_llm(self, cache):
        calls = [0]
        def fake_llm(q): calls[0] += 1; return "Python is a language."

        cache.cached_call("What is Python?", fake_llm)
        assert calls[0] == 1

        r = cache.cached_call("Explain Python to me", fake_llm)
        assert r["source"]    == "cache"
        assert r["cache_hit"] is True
        assert calls[0]       == 1          # LLM not called again

    def test_result_has_all_fields(self, cache):
        r = cache.cached_call("test query", lambda q: "test response")
        for field in ["response", "source", "similarity", "latency_ms", "cache_hit"]:
            assert field in r, f"Missing field: {field}"

    def test_latency_is_positive(self, cache):
        r = cache.cached_call("test query", lambda q: "response")
        assert r["latency_ms"] > 0

    def test_similarity_in_range(self, cache):
        r = cache.cached_call("test query", lambda q: "response")
        assert 0.0 <= r["similarity"] <= 1.0

    def test_kwargs_forwarded_to_llm(self, cache):
        received = {}
        def fake_llm(q, model="default", temp=0.5):
            received.update({"model": model, "temp": temp})
            return "response"

        cache.cached_call("test", fake_llm, model="gpt-4", temp=0.9)
        assert received["model"] == "gpt-4"
        assert received["temp"]  == 0.9

    def test_response_stored_after_miss(self, cache):
        cache.cached_call("What is Python?", lambda q: "Python is great.")
        # Now get directly — should find it
        result, sim = cache.get("What is Python?")
        assert result == "Python is great."


# ── Stats ─────────────────────────────────────────────────────

class TestStats:

    def test_initial_stats(self, cache):
        s = cache.stats()
        assert s["hits"]          == 0
        assert s["misses"]        == 0
        assert s["total_queries"] == 0
        assert s["hit_rate"]      == 0.0
        assert s["saved_cost"]    == 0.0

    def test_miss_increments_misses(self, cache):
        cache.cached_call("question", lambda q: "answer")
        assert cache.stats()["misses"] == 1
        assert cache.stats()["hits"]   == 0

    def test_hit_increments_hits(self, cache):
        cache.cached_call("What is Python?", lambda q: "Python is great.")
        cache.cached_call("Explain Python",  lambda q: "should not call")
        s = cache.stats()
        assert s["misses"]   == 1
        assert s["hits"]     == 1
        assert s["hit_rate"] == 0.5

    def test_saved_cost_accumulates(self, cache):
        cache.cached_call("What is Python?", lambda q: "Python.", cost_per_call=0.01)
        cache.cached_call("Explain Python",  lambda q: "x",       cost_per_call=0.01)
        assert cache.stats()["saved_cost"] == pytest.approx(0.01)

    def test_stats_reset_on_clear(self, cache):
        cache.cached_call("question", lambda q: "answer")
        cache.clear()
        s = cache.stats()
        assert s["hits"]   == 0
        assert s["misses"] == 0


# ── Threshold behaviour ───────────────────────────────────────

class TestThreshold:

    def test_strict_threshold_rejects_paraphrase(self, tmp_path):
        cache = Cache(
            backend   = "sqlite",
            threshold = 0.99,           # near-exact match only
            db_path   = str(tmp_path / "strict"),
        )
        cache.set("What is Python?", "Python is a language.")
        result, _ = cache.get("Explain Python to me")
        assert result is None

    def test_lenient_threshold_accepts_loose_match(self, tmp_path):
        cache = Cache(
            backend   = "sqlite",
            threshold = 0.40,           # very lenient
            db_path   = str(tmp_path / "lenient"),
        )
        cache.set("What is Python?", "Python is a language.")
        result, _ = cache.get("Tell me about software programming")
        assert result is not None


# ── Personalization ───────────────────────────────────────────

class TestPersonalization:

    def test_user_scoped_hit(self, tmp_path):
        cache = Cache(
            backend      = "sqlite",
            threshold    = 0.85,
            personalized = True,
            db_path      = str(tmp_path / "personal"),
        )
        cache.set("What is Python?", "Python is a language.", user_id="alice")
        result, _ = cache.get("What is Python?", user_id="alice")
        assert result is not None

    def test_user_scoped_miss_for_other_user(self, tmp_path):
        cache = Cache(
            backend      = "sqlite",
            threshold    = 0.85,
            personalized = True,
            db_path      = str(tmp_path / "personal2"),
        )
        cache.set("What is Python?", "Python is a language.", user_id="alice")
        result, _ = cache.get("What is Python?", user_id="bob")
        assert result is None, "Bob should not see Alice's cached entry"
