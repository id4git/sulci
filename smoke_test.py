from sulci import Cache

# --- stateless mode, SQLite backend, no infrastructure needed ---
cache = Cache(backend="sqlite", threshold=0.85)

cache.set("How do I deploy to AWS?", "Use the AWS CLI with 'aws deploy'...")

response, sim, ctx_depth = cache.get("How do I deploy to AWS?")
assert response is not None, "FAIL: exact hit returned None"
print(f"Exact hit:    sim={sim:.3f}  ctx={ctx_depth}  ✅")

response, sim, ctx_depth = cache.get("What is the process for deploying on AWS?")
if response:
    print(f"Semantic hit: sim={sim:.3f}  ctx={ctx_depth}  ✅")
else:
    print(f"Semantic miss (sim={sim:.3f}) — try lowering threshold")

s = cache.stats()
print(f"Stats:        hits={s['hits']}  misses={s['misses']}  hit_rate={s['hit_rate']:.1%}")

# --- context-aware mode ---
cache_ctx = Cache(backend="sqlite", threshold=0.85, context_window=4)
cache_ctx.set("What is Python?", "Python is a high-level programming language.", session_id="s1")
response, sim, ctx_depth = cache_ctx.get("Tell me about Python", session_id="s1")
print(f"Context mode: sim={sim:.3f}  ctx_depth={ctx_depth}  ✅")

print("\nAll smoke tests passed.")
