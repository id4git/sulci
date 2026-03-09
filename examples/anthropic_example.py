"""
examples/anthropic_example.py
==============================
Production-ready Sulci + Anthropic Claude integration.

Requirements:
    pip install "sulci[chroma]" anthropic
    export ANTHROPIC_API_KEY=sk-ant-...

Run:
    python examples/anthropic_example.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sulci import Cache

# ── Cache configuration ───────────────────────────────────────
cache = Cache(
    backend         = "chroma",     # ChromaDB persists to disk
    threshold       = 0.85,         # tune per your domain
    embedding_model = "minilm",     # free local embeddings
    ttl_seconds     = 86400,        # 24-hour cache
    personalized    = False,        # set True for multi-user apps
)

# ── Anthropic client ──────────────────────────────────────────
try:
    import anthropic
    _client = anthropic.Anthropic()

    def call_claude(query: str, model: str = "claude-sonnet-4-20250514") -> str:
        """Call Claude and return response text."""
        msg = _client.messages.create(
            model      = model,
            max_tokens = 1024,
            messages   = [{"role": "user", "content": query}],
        )
        return msg.content[0].text

    print("✓ Anthropic client ready\n")

except ImportError:
    print("⚠  anthropic not installed — using mock LLM\n")

    def call_claude(query: str, **_) -> str:
        return f"[Mock] Answer to: {query}"


# ── Multi-turn conversation helper ────────────────────────────
class CachedChat:
    """
    Wraps Cache for multi-turn conversations.
    Note: cache keys are per-query only; conversation context
    is NOT included in the cache key (use personalized=True
    + user_id for user-scoped caching).
    """

    def __init__(self, cache: Cache):
        self.cache   = cache
        self.history = []

    def ask(self, question: str) -> str:
        result = self.cache.cached_call(question, call_claude)
        self.history.append({
            "question": question,
            "answer":   result["response"],
            "source":   result["source"],
            "latency":  result["latency_ms"],
        })
        return result

    def print_history(self):
        print("\n── Conversation history ──────────────────────")
        for i, turn in enumerate(self.history, 1):
            icon = "⚡" if turn["source"] == "cache" else "🌐"
            print(f"{i}. {icon} [{turn['source'].upper()}] {turn['latency']:.1f}ms")
            print(f"   Q: {turn['question']}")
            print(f"   A: {turn['answer'][:100]}...")
            print()


# ── Demo ──────────────────────────────────────────────────────
def main():
    print("◈ Sulci + Anthropic Claude\n")

    chat = CachedChat(cache)

    # Round 1 — fresh questions (cache misses)
    print("Round 1: Fresh questions")
    print("-" * 40)
    questions_r1 = [
        "What is semantic caching?",
        "How do Python decorators work?",
        "Explain the CAP theorem",
    ]
    for q in questions_r1:
        r = chat.ask(q)
        print(f"{'⚡' if r['cache_hit'] else '🌐'} [{r['source'].upper()}] "
              f"{r['latency_ms']:.0f}ms — {q}")

    # Round 2 — paraphrased questions (should hit cache)
    print("\nRound 2: Paraphrased questions")
    print("-" * 40)
    questions_r2 = [
        "How does semantic cache work?",       # ≈ question 1
        "Python decorator pattern explained",  # ≈ question 2
        "What does CAP theorem mean?",         # ≈ question 3
    ]
    for q in questions_r2:
        r = chat.ask(q)
        sim = f"  sim={r['similarity']:.0%}" if r["cache_hit"] else ""
        print(f"{'⚡' if r['cache_hit'] else '🌐'} [{r['source'].upper()}] "
              f"{r['latency_ms']:.0f}ms{sim} — {q}")

    # Stats
    print()
    s = cache.stats()
    print("=" * 50)
    print(f"Queries      : {s['total_queries']}")
    print(f"Cache hits   : {s['hits']}  ({s['hit_rate']:.0%} hit rate)")
    print(f"LLM calls    : {s['misses']}")
    print(f"Cost saved   : ${s['saved_cost']:.4f}")
    print("=" * 50)

    chat.print_history()


if __name__ == "__main__":
    main()
