# ◈ Sulci

> Semantic caching for LLM apps — stop paying for the same answer twice.

[![PyPI version](https://badge.fury.io/py/sulci.svg)](https://pypi.org/project/sulci/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://github.com/id4git/sulci/actions/workflows/tests.yml/badge.svg)](https://github.com/id4git/sulci/actions/workflows/tests.yml)

**"How do I cancel?" and "cancellation process?" are the same question.**  
Sulci finds meaning-matches, not string-matches — cutting redundant LLM calls
and API costs by 40–85%. And unlike other semantic caches, Sulci understands
*conversation context*, so follow-up queries like **"How do I fix it?"**
resolve correctly based on what was just discussed.

---

## Install

```bash
pip install "sulci[chroma]"    # ChromaDB  — recommended for getting started
pip install "sulci[sqlite]"    # SQLite    — zero infrastructure
pip install "sulci[qdrant]"    # Qdrant    — best production performance
pip install "sulci[faiss]"     # FAISS     — fastest local search
pip install "sulci[redis]"     # Redis     — sub-millisecond latency
pip install "sulci[milvus]"    # Milvus    — enterprise scale
pip install "sulci[all]"       # all backends
```

---

## Quickstart

```python
from sulci import Cache
import anthropic

cache  = Cache(backend="chroma", threshold=0.85)
client = anthropic.Anthropic()

def call_claude(query: str) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": query}],
    )
    return msg.content[0].text

# First call — hits the Claude API (~1.8s)
r1 = cache.cached_call("What is semantic caching?", call_claude)
print(f"[{r1['source']}] {r1['latency_ms']:.0f}ms")      # [llm] 1843ms

# Paraphrase — served from cache (~0.5ms, no API call)
r2 = cache.cached_call("Explain how semantic caches work", call_claude)
print(f"[{r2['source']}] {r2['similarity']:.0%} match")   # [cache] 91% match

print(cache.stats())
# {'hits': 1, 'misses': 1, 'hit_rate': 0.5, 'saved_cost': 0.005, 'total_queries': 2}
```

No API key needed to try it:

```bash
pip install "sulci[sqlite]"
python examples/basic_usage.py
```

---

## Context-aware caching

Standard semantic caches are stateless — every query is matched independently.
That breaks in real conversations.

```
User: "My Docker container crashes on startup"   → cache stores Docker fix
User: "How do I fix it?"                         → ??? could match anything
```

Sulci solves this with a **per-session context window**. Each conversation turn
is embedded and stored in a sliding window. On lookup, the current query
embedding is blended with a decayed summary of recent turns:

```
lookup_vec = 0.70 × embed(query) + 0.30 × Σ wᵢ × embed(turnᵢ)
```

Recent turns get full weight (`w=1.0`), older turns decay exponentially
(`0.5, 0.25, ...`). The result is re-normalised for cosine similarity.

**The same follow-up, two different contexts — two correct answers:**

```python
from sulci import Cache

cache = Cache(backend="sqlite", context_window=6)

# Session A — Docker conversation
cache.cached_call("My Docker container crashes on startup", llm, session_id="user-A")
result = cache.cached_call("How do I fix it?", llm, session_id="user-A")
# → returns Docker fix ✓   (context_depth=1)

# Session B — Billing conversation
cache.cached_call("My payment keeps failing", llm, session_id="user-B")
result = cache.cached_call("How do I fix it?", llm, session_id="user-B")
# → returns billing fix ✓  (context_depth=1)
```

Every result includes `context_depth` — the number of prior turns that
influenced the lookup. `0` means stateless (no context was used).

### Context API

```python
cache = Cache(
    backend        = "sqlite",
    context_window = 6,       # turns to remember per session (0 = stateless)
    query_weight   = 0.70,    # 70% current query, 30% history
    context_decay  = 0.50,    # each older turn contributes half as much
    session_ttl    = 3600,    # evict idle sessions after 1 hour
)

# Pass session_id to any call
result = cache.cached_call(query, llm_fn, session_id="user-42")
print(result["context_depth"])   # 0 = no context, 1+ = history influenced

# Manually inject prior turns (e.g. restore a saved conversation)
ctx = cache.get_context("user-42")
ctx.add_turn("I am using FastAPI on Python 3.11", role="user")
ctx.add_turn("Got it, let me help with FastAPI.", role="assistant")

# Start a new topic without losing cached entries
cache.clear_context("user-42")

# Inspect active sessions
print(cache.context_summary("user-42"))
print(cache.context_summary())    # all active sessions
```

### Context is fully backward-compatible

`context_window=0` (the default) is identical to the original stateless
behaviour — no sessions are created, no overhead is added, and existing
code requires zero changes.

```python
# This still works exactly as before
cache = Cache(backend="chroma", threshold=0.85)
result = cache.cached_call("What is Python?", llm_fn)
# result["context_depth"] == 0  (always, when context_window=0)
```

Try the full context demo with no API key:

```bash
pip install "sulci[sqlite]"
python examples/context_aware.py
```

---

## Benchmark results

10,000-query benchmark across 5 domains (5,000 warmup + 5,000 measured):

| Domain | Hit Rate | p50 Latency |
|---|---|---|
| Customer Support | 85.2% | 0.55ms |
| Developer Q&A | 88.2% | 0.55ms |
| Product FAQ | 85.0% | 0.55ms |
| Medical Info | 81.5% | 0.55ms |
| General Knowledge | 84.4% | 0.55ms |
| **Overall** | **84.9%** | **0.55ms** |

Cache hit latency: **0.55ms p50** vs Claude API: **~1,800ms** — a **3,000× speedup** on hits.  
Estimated cost saving: **$21 per 10,000 queries** at standard API pricing.

Run it yourself:

```bash
python benchmark/run.py
python benchmark/run.py --use-sulci   # with real MiniLM embeddings
```

---

## Backends

| Backend | Extra | Latency | Best for |
|---|---|---|---|
| ChromaDB | `sulci[chroma]` | ~4ms | Getting started, local dev |
| SQLite | `sulci[sqlite]` | 5–50ms | Zero infra, edge, prototyping |
| FAISS | `sulci[faiss]` | <2ms | Fastest local, 100k+ entries |
| Qdrant | `sulci[qdrant]` | <5ms | Production scale |
| Redis | `sulci[redis]` | <1ms | Sub-millisecond, existing Redis |
| Milvus | `sulci[milvus]` | 5–20ms | Enterprise, Zilliz Cloud |

All backends share the same API — swap `backend="chroma"` for `backend="sqlite"`
and nothing else changes.

---

## Embedding models

| Model | Key | Dim | Notes |
|---|---|---|---|
| all-MiniLM-L6-v2 | `"minilm"` | 384 | Default. Fast, free, no API key |
| all-mpnet-base-v2 | `"mpnet"` | 768 | Better quality, still free |
| BAAI/bge-base-en-v1.5 | `"bge"` | 768 | Best open-source quality |
| OpenAI text-embedding-3-small | `"openai"` | 1536 | Highest quality, requires API key |

---

## API reference

### Cache init

```python
from sulci import Cache

cache = Cache(
    # ── core ──────────────────────────────────────────────────
    backend         = "chroma",     # "chroma"|"sqlite"|"faiss"|"qdrant"|"redis"|"milvus"
    threshold       = 0.85,         # cosine similarity threshold (0.0–1.0)
    embedding_model = "minilm",     # "minilm"|"mpnet"|"bge"|"openai"
    ttl_seconds     = 86400,        # entry TTL in seconds. None = no expiry
    personalized    = False,        # True = scope entries per user_id
    db_path         = "./sulci_db", # local storage path (Chroma, SQLite, FAISS)

    # ── context-awareness (new in v0.2.0) ─────────────────────
    context_window  = 0,            # turns to remember per session. 0 = stateless
    query_weight    = 0.70,         # current query weight vs history (0.0–1.0)
    context_decay   = 0.50,         # exponential decay per turn
    session_ttl     = 3600,         # idle session eviction timeout in seconds
)
```

### cached_call

```python
result = cache.cached_call(
    query,
    llm_fn,                  # callable: (query, **kwargs) → str
    user_id       = None,    # for personalized caching
    session_id    = None,    # for context-aware caching (new in v0.2.0)
    cost_per_call = 0.005,   # for savings tracking
    **llm_kwargs,            # forwarded to llm_fn on cache miss
)
# returns:
# {
#   "response":      str,
#   "source":        "cache" | "llm",
#   "similarity":    float,
#   "latency_ms":    float,
#   "cache_hit":     bool,
#   "context_depth": int,    # 0 = no context used (new in v0.2.0)
# }
```

### Manual control

```python
response, similarity, context_depth = cache.get(query, user_id=None, session_id=None)
cache.set(query, response, user_id=None, session_id=None, metadata=None)
```

### Context management (v0.2.0+)

```python
ctx = cache.get_context(session_id)          # ContextWindow for this session
ctx.add_turn(text, role="user")              # manually inject a turn
ctx.add_turn(text, role="assistant")

cache.clear_context(session_id)              # reset session (keep cache entries)
cache.context_summary(session_id)           # dict: depth, turns, weights
cache.context_summary()                      # all active sessions
```

### Stats

```python
cache.stats()
# {
#   "hits": int, "misses": int, "hit_rate": float,
#   "saved_cost": float, "total_queries": int,
#   "active_sessions": int,   # present when context_window > 0
# }
cache.clear()   # remove all entries, reset stats, clear all sessions
```

---

## Run tests

```bash
pip install "sulci[sqlite]" pytest

pytest tests/test_core.py    -v   # core cache operations (26 tests)
pytest tests/test_context.py -v   # context-awareness (27 tests)
pytest tests/test_backends.py -v  # per-backend (skips missing deps)

# All at once
pytest tests/ -v
```

---

## Project structure

```
sulci/
├── sulci/
│   ├── __init__.py             ← exports Cache, ContextWindow, SessionStore
│   ├── core.py                 ← Cache engine
│   ├── context.py              ← ContextWindow + SessionStore (v0.2.0)
│   ├── backends/
│   │   ├── chroma.py
│   │   ├── qdrant.py
│   │   ├── faiss.py
│   │   ├── redis.py
│   │   ├── sqlite.py
│   │   └── milvus.py
│   └── embeddings/
│       ├── minilm.py           ← local (free, default)
│       └── openai.py           ← OpenAI API
├── tests/
│   ├── test_core.py            ← 26 tests: ops, stats, threshold, personalization
│   ├── test_context.py         ← 27 tests: ContextWindow, SessionStore, integration
│   └── test_backends.py        ← per-backend contract tests
├── examples/
│   ├── basic_usage.py          ← stateless, no API key needed
│   ├── context_aware.py        ← context-aware demo, no API key needed (v0.2.0)
│   └── anthropic_example.py    ← full Claude integration with sessions
├── benchmark/
│   ├── run.py                  ← 10k-query benchmark, zero deps
│   ├── README.md
│   └── results/
├── .github/workflows/
│   ├── tests.yml               ← CI: ubuntu/macos/windows × py3.9/3.11/3.12
│   ├── publish.yml             ← auto-publish to PyPI on git tag
│   └── benchmark.yml           ← weekly benchmark runs
├── pyproject.toml
├── CHANGELOG.md
└── CONTRIBUTING.md
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full history.

**v0.2.0** — Context-aware caching
- `context.py`: `ContextWindow` + `SessionStore`
- `Cache` gains `context_window`, `query_weight`, `context_decay`, `session_ttl`
- `cached_call`/`get`/`set` accept `session_id`
- All results include `context_depth` field
- New: `get_context()`, `clear_context()`, `context_summary()`
- New: `examples/context_aware.py`
- Fully backward-compatible — `context_window=0` is unchanged

**v0.1.1** — Benchmark suite, CI fixes  
**v0.1.0** — Initial release

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, how to add a new backend,
and the release process.

---

## Links

- **PyPI**: [pypi.org/project/sulci](https://pypi.org/project/sulci)
- **Issues**: [github.com/id4git/sulci/issues](https://github.com/id4git/sulci/issues)

MIT License © 2025 Sulci
