"""
examples/basic_usage.py
=======================
Minimal Sulci example — no API key required.
Uses a mock LLM so you can run this immediately.

Run:
    pip install "sulci[sqlite]"
    python examples/basic_usage.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sulci import Cache

# ── 1. Create a cache ─────────────────────────────────────────
cache = Cache(
    backend         = "sqlite",     # zero infra — just a local file
    threshold       = 0.85,         # 85% similarity required for a hit
    embedding_model = "minilm",     # free local model, downloads once
    ttl_seconds     = 3600,         # cache for 1 hour
)

# ── 2. Define your LLM function ───────────────────────────────
def my_llm(query: str) -> str:
    """
    Replace this with your real LLM call:
        anthropic, openai, ollama, etc.
    """
    # Simulate a slow API call
    import time; time.sleep(0.1)
    return f"[LLM Response] Here is the answer to: '{query}'"


# ── 3. Use cached_call ────────────────────────────────────────
print("◈ Sulci Basic Usage Demo\n")

queries = [
    # Original queries (cache misses — will call LLM)
    "What is semantic caching?",
    "How do I use Python for web scraping?",
    "What is the difference between SQL and NoSQL?",

    # Paraphrases (cache hits — LLM skipped)
    "Explain semantic caches to me",
    "Python web scraping guide",
    "SQL versus NoSQL databases",
]

for i, q in enumerate(queries):
    if i == 3:
        print("\n--- Sending paraphrases now ---\n")

    result = cache.cached_call(q, my_llm)

    icon    = "⚡ HIT " if result["cache_hit"] else "🌐 MISS"
    latency = f"{result['latency_ms']:.1f}ms"
    sim     = f"  sim={result['similarity']:.0%}" if result["cache_hit"] else ""

    print(f"{icon}  {latency}{sim}")
    print(f"  Q: {q}")
    print(f"  A: {result['response'][:80]}")
    print()

# ── 4. Print stats ────────────────────────────────────────────
s = cache.stats()
print("=" * 50)
print(f"Total queries : {s['total_queries']}")
print(f"Cache hits    : {s['hits']}")
print(f"Cache misses  : {s['misses']}")
print(f"Hit rate      : {s['hit_rate']:.0%}")
print(f"Cost saved    : ${s['saved_cost']:.4f}")
print("=" * 50)
