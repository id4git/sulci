"""
sulci/core.py
================
Core semantic cache engine — backend-agnostic.

Supports backends : ChromaDB, Qdrant, FAISS, Redis, SQLite, Milvus
Embedding models  : MiniLM / MPNet / BGE (local, free) or OpenAI API
"""
import time
import hashlib
import importlib
from typing import Optional, Callable, Any


class Cache:
    """
    Semantic cache for LLM applications.

    Args:
        backend:         Vector store backend. One of:
                         "chroma" | "qdrant" | "faiss" | "redis" | "sqlite" | "milvus"
        threshold:       Cosine similarity threshold (0.0–1.0).
                         0.85 is a good starting point for most use cases.
                         Higher → fewer hits, fewer false positives.
        embedding_model: Local: "minilm" (default), "mpnet", "bge"
                         API:   "openai" (requires OPENAI_API_KEY)
        ttl_seconds:     Cache entry time-to-live. None = no expiry.
        personalized:    Scope cache per user_id to prevent cross-user hits.
        db_path:         Local storage path (ChromaDB, SQLite, FAISS).

    Example:
        cache = Cache(backend="chroma", threshold=0.85)

        # Drop-in LLM wrapper
        result = cache.cached_call("What is Python?", call_claude)
        print(result["source"])     # "llm" (first call)

        result = cache.cached_call("Explain Python to me", call_claude)
        print(result["source"])     # "cache" (semantic match)
        print(result["similarity"]) # 0.91

        # Manual get / set
        response, sim = cache.get("What is Python?")
        if response is None:
            response = call_claude("What is Python?")
            cache.set("What is Python?", response)
    """

    def __init__(
        self,
        backend:         str           = "chroma",
        threshold:       float         = 0.85,
        embedding_model: str           = "minilm",
        ttl_seconds:     Optional[int] = 86400,
        personalized:    bool          = False,
        db_path:         str           = "./sulci_db",
    ):
        self.backend      = backend
        self.threshold    = threshold
        self.ttl_seconds  = ttl_seconds
        self.personalized = personalized
        self._stats       = {"hits": 0, "misses": 0, "saved_cost": 0.0}

        self._embedder = self._load_embedder(embedding_model)
        self._backend  = self._load_backend(backend, db_path)

    # ── private ───────────────────────────────────────────────────

    def _load_embedder(self, name: str):
        if name == "openai":
            from sulci.embeddings.openai import OpenAIEmbedder
            return OpenAIEmbedder()
        from sulci.embeddings.minilm import MiniLMEmbedder
        return MiniLMEmbedder(name)

    def _load_backend(self, name: str, db_path: str):
        registry = {
            "chroma": "sulci.backends.chroma.ChromaBackend",
            "qdrant": "sulci.backends.qdrant.QdrantBackend",
            "faiss":  "sulci.backends.faiss.FAISSBackend",
            "redis":  "sulci.backends.redis.RedisBackend",
            "sqlite": "sulci.backends.sqlite.SQLiteBackend",
            "milvus": "sulci.backends.milvus.MilvusBackend",
        }
        if name not in registry:
            raise ValueError(
                f"Unknown backend '{name}'. Choose from: {list(registry.keys())}"
            )
        module_path, cls_name = registry[name].rsplit(".", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name)(db_path=db_path)

    # ── public API ────────────────────────────────────────────────

    def get(
        self,
        query:   str,
        user_id: Optional[str] = None,
    ) -> tuple[Optional[str], float]:
        """
        Check cache for a semantically similar query.

        Returns:
            (cached_response, similarity_score)
            response is None on cache miss.
        """
        vec = self._embedder.embed(query)
        return self._backend.search(
            embedding = vec,
            threshold = self.threshold,
            user_id   = user_id if self.personalized else None,
            now       = time.time(),
        )

    def set(
        self,
        query:    str,
        response: str,
        user_id:  Optional[str]  = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Store a query-response pair in the cache."""
        key     = hashlib.sha256(query.encode()).hexdigest()[:16]
        vec     = self._embedder.embed(query)
        expires = time.time() + self.ttl_seconds if self.ttl_seconds else None
        self._backend.store(
            key       = key,
            query     = query,
            response  = response,
            embedding = vec,
            user_id   = user_id if self.personalized else None,
            expires   = expires,
            metadata  = metadata or {},
        )

    def cached_call(
        self,
        query:         str,
        llm_fn:        Callable[..., str],
        user_id:       Optional[str] = None,
        cost_per_call: float         = 0.005,
        **llm_kwargs:  Any,
    ) -> dict:
        """
        Drop-in LLM wrapper. Checks cache first; calls LLM on miss.

        Args:
            query:         User query string.
            llm_fn:        Any callable (query, **kwargs) → str.
            user_id:       For personalized caching.
            cost_per_call: Estimated API cost per call (for savings tracking).
            **llm_kwargs:  Forwarded to llm_fn on cache miss.

        Returns:
            {
                "response":   str,
                "source":     "cache" | "llm",
                "similarity": float,
                "latency_ms": float,
                "cache_hit":  bool,
            }
        """
        t0       = time.perf_counter()
        hit, sim = self.get(query, user_id=user_id)
        ms       = (time.perf_counter() - t0) * 1000

        if hit is not None:
            self._stats["hits"]       += 1
            self._stats["saved_cost"] += cost_per_call
            return {
                "response":   hit,
                "source":     "cache",
                "similarity": round(sim, 4),
                "latency_ms": round(ms, 2),
                "cache_hit":  True,
            }

        response = llm_fn(query, **llm_kwargs)
        self.set(query, response, user_id=user_id)
        ms = (time.perf_counter() - t0) * 1000
        self._stats["misses"] += 1
        return {
            "response":   response,
            "source":     "llm",
            "similarity": round(sim, 4),
            "latency_ms": round(ms, 2),
            "cache_hit":  False,
        }

    def stats(self) -> dict:
        """Return session hit/miss statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        return {
            **self._stats,
            "total_queries": total,
            "hit_rate":      round(self._stats["hits"] / total, 4) if total else 0.0,
        }

    def clear(self) -> None:
        """Remove all cached entries and reset stats."""
        self._backend.clear()
        self._stats = {"hits": 0, "misses": 0, "saved_cost": 0.0}

    def __repr__(self) -> str:
        return (
            f"Cache(backend={self.backend!r}, "
            f"threshold={self.threshold}, "
            f"hits={self._stats['hits']}, "
            f"misses={self._stats['misses']})"
        )
