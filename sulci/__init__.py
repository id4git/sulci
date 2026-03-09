"""
sulci — Semantic caching for LLM applications.
Stop paying for the same answer twice.

Install:
    pip install sulci[chroma]   # ChromaDB backend
    pip install sulci[qdrant]   # Qdrant backend
    pip install sulci[faiss]    # FAISS backend
    pip install sulci[sqlite]   # SQLite (zero infra)
    pip install sulci[all]      # everything

Quickstart:
    from sulci import Cache

    cache  = Cache(backend="chroma", threshold=0.85)
    result = cache.cached_call("What is Python?", my_llm_fn)
    print(result["source"])    # "cache" or "llm"
    print(result["response"])
"""
from sulci.core import Cache

__version__ = "0.1.1"
__all__     = ["Cache"]
