# ◈ Sulci

> Semantic caching for LLM apps — stop paying for the same answer twice.

[![PyPI version](https://badge.fury.io/py/sulci.svg)](https://pypi.org/project/sulci/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://github.com/id4git/sulci/actions/workflows/tests.yml/badge.svg)](https://github.com/id4git/sulci/actions/workflows/tests.yml)

**"How do I cancel?" and "cancellation process?" are the same question.**
Sulci finds meaning-matches, not just string-matches — eliminating
redundant LLM calls and cutting API costs by 40–85%.

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
print(f"[{r1['source']}] {r1['latency_ms']:.0f}ms")     # [llm] 1843ms

# Paraphrase — served from cache (~0.5ms, no API call)
r2 = cache.cached_call("Explain how semantic caches work", call_claude)
print(f"[{r2['source']}] {r2['similarity']:.0%} match")  # [cache] 91% match

print(cache.stats())
# {'hits': 1, 'misses': 1, 'hit_rate': 0.5, 'saved_cost': 0.005, 'total_queries': 2}
```

No API key needed to try it — use the SQLite backend with a mock function:

```bash
pip install "sulci[sqlite]"
python examples/basic_usage.py
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

Cache hit latency: **0.55ms p50** vs Claude API: **~1,800ms** — a 3,000x speedup on hits.
Estimated cost saving at scale: **$21 per 10,000 queries** at standard API pricing.

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

All backends share the same API — swap `backend="chroma"` for `backend="sqlite"` and nothing else changes.

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

```python
from sulci import Cache

cache = Cache(
    backend         = "chroma",     # "chroma" | "sqlite" | "faiss" | "qdrant" | "redis" | "milvus"
    threshold       = 0.85,         # cosine similarity threshold (0.0–1.0)
    embedding_model = "minilm",     # "minilm" | "mpnet" | "bge" | "openai"
    ttl_seconds     = 86400,        # entry TTL in seconds. None = no expiry
    personalized    = False,        # True = scope cache entries per user_id
    db_path         = "./sulci_db", # local storage path (Chroma, SQLite, FAISS)
)

# ── Drop-in LLM wrapper ───────────────────────────────────────
result = cache.cached_call(
    query,
    llm_fn,                 # any callable: (query, **kwargs) → str
    user_id      = None,    # optional: for personalized caching
    cost_per_call= 0.005,   # for savings tracking
    **llm_kwargs,           # forwarded to llm_fn on cache miss
)
# returns: {"response", "source", "similarity", "latency_ms", "cache_hit"}

# ── Manual control ────────────────────────────────────────────
response, similarity = cache.get(query, user_id=None)
cache.set(query, response, user_id=None, metadata=None)

# ── Session stats ─────────────────────────────────────────────
cache.stats()   # {"hits", "misses", "hit_rate", "saved_cost", "total_queries"}
cache.clear()   # remove all entries and reset stats
```

---

## Run tests

```bash
pip install "sulci[sqlite]" pytest
pytest tests/ -v

# Run only core tests (fastest)
pytest tests/test_core.py -v

# Run backend-specific tests (skips backends whose deps aren't installed)
pytest tests/test_backends.py -v
```

---

## Project structure

```
sulci/
├── sulci/
│   ├── __init__.py             ← exports Cache
│   ├── core.py                 ← Cache engine
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
│   ├── test_core.py            ← 20 tests: ops, stats, threshold, personalization
│   └── test_backends.py        ← per-backend contract tests
├── examples/
│   ├── basic_usage.py          ← runs with no API key
│   └── anthropic_example.py    ← full Claude integration
├── .github/workflows/
│   ├── tests.yml               ← CI on every push/PR
│   └── publish.yml             ← auto-publish to PyPI on git tag
├── pyproject.toml
├── setup.py
├── CHANGELOG.md
├── CONTRIBUTING.md
└── LICENSE
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, how to add a new backend, and the release process.

---

## Links

- **PyPI**: [pypi.org/project/sulci](https://pypi.org/project/sulci)
- **Issues**: [github.com/id4git/sulci/issues](https://github.com/id4git/sulci/issues)

MIT License © 2025 Sulci
