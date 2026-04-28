# Sulci Cache

**The AI native context-aware semantic caching for LLM apps — stop paying for the same answer twice**

[![Patent Pending](https://img.shields.io/badge/Patent-Pending-blue.svg)](https://sulci.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://github.com/sulci-io/sulci-oss/actions/workflows/tests.yml/badge.svg)](https://github.com/sulci-io/sulci-oss/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/sulci)](https://pypi.org/project/sulci/)
[![Python](https://img.shields.io/pypi/pyversions/sulci)](https://pypi.org/project/sulci/)
[![Downloads](https://pepy.tech/badge/sulci/month)](https://pepy.tech/project/sulci)
[![Downloads](https://pepy.tech/badge/sulci)](https://pepy.tech/project/sulci)

Sulci Cache is a drop-in Python library that caches LLM responses by **semantic meaning**, not exact string match. When a user asks _"How do I deploy to AWS?"_ and someone else later asks _"What's the process for deploying on AWS?"_, Sulci Cache returns the cached answer instead of calling the LLM again — saving cost and latency.

---

## Why Sulci Cache

| Without Sulci Cache          | With Sulci Cache                                         |
| ---------------------------- | -------------------------------------------------------- |
| Every query hits the LLM API | Semantically similar queries return instantly from cache |
| $0.005 per call, every time  | Cache hits cost ~$0.0001 (embedding only)                |
| 1–3 second response time     | Cache hits return in <10ms                               |
| No memory across sessions    | Context-aware: understands conversation history          |

**Benchmark results (v0.5.0, 5,000 queries):**

- Overall hit rate: **85.9%**
- Hit latency p50: **0.74ms** (vs ~1,840ms for a live LLM call)
- Cost saved per 10k queries: **$21.47**
- Context-aware mode: **+20.8pp resolution accuracy** over stateless

---

## Install

**Step 1 — Install Sulci Cache with a backend:**

```bash
pip install "sulci[sqlite]"    # SQLite — zero infra, local dev (start here)
pip install "sulci[chroma]"    # ChromaDB
pip install "sulci[faiss]"     # FAISS
pip install "sulci[qdrant]"    # Qdrant
pip install "sulci[redis]"     # Redis + RedisVL
pip install "sulci[milvus]"    # Milvus Lite
pip install "sulci[cloud]"     # Sulci Cloud managed backend
```

**LangChain integration:**

```bash
pip install "sulci[sqlite,langchain]"   # + LangChain integration
```

**LlamaIndex integration:**

```bash
pip install "sulci[sqlite,llamaindex]"  # + LlamaIndex native integration
```

**AsyncCache (non-blocking async wrapper):**

```bash
pip install "sulci[sqlite]"   # AsyncCache is included — no extra install needed
```

**Step 2 — Install your LLM SDK** (required for `cached_call` with a live model):

```bash
pip install anthropic           # for Anthropic / Claude
pip install openai              # for OpenAI
```

> **zsh users:** always wrap extras in quotes — `"sulci[sqlite]"` not `sulci[sqlite]`.

---

## LangChain Integration

Sulci Cache is the only LangChain cache that implements context-aware lookup
vector blending — blending prior conversation turns into the similarity lookup,
not just matching the current prompt in isolation.

```python
from langchain_core.globals import set_llm_cache
from sulci.integrations.langchain import SulciCache

# Stateless semantic — drop-in for GPTCache
set_llm_cache(SulciCache(backend="sqlite"))

# Context-aware — chatbot / agent (+56pp hit rate in customer support)
set_llm_cache(SulciCache(backend="sqlite", context_window=4, threshold=0.75))

# Managed Sulci Cloud
set_llm_cache(SulciCache(backend="sulci", api_key="sk-sulci-..."))
```

Install: `pip install "sulci[sqlite,langchain]"`

---

## LlamaIndex Integration

`SulciCacheLLM` is a native LLM-level semantic cache for LlamaIndex with
no LangChain dependency required. It wraps any LlamaIndex-compatible LLM (`OpenAI`, `Anthropic`, `Ollama`, `HuggingFaceLLM`, etc.) — `complete()` and `chat()` are cached, streaming passes through uncached, async methods use `run_in_executor`.

```python
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from sulci.integrations.llamaindex import SulciCacheLLM

# Stateless — drop-in for any LlamaIndex LLM
Settings.llm = SulciCacheLLM(
    llm       = OpenAI(model="gpt-4o"),
    backend   = "sqlite",
    threshold = 0.85,
)

# Context-aware — RAG chatbot / agent (+56pp hit rate in customer support)
Settings.llm = SulciCacheLLM(
    llm            = OpenAI(model="gpt-4o"),
    backend        = "sqlite",
    threshold      = 0.75,
    context_window = 4,
)

# Managed Sulci Cloud
Settings.llm = SulciCacheLLM(
    llm     = OpenAI(model="gpt-4o"),
    backend = "sulci",
    api_key = "sk-sulci-...",
)
```

Install: `pip install "sulci[sqlite,llamaindex]"`

**Via LangChain (alternative — works today, no extra install):**

```python
from langchain_core.globals import set_llm_cache
from sulci.integrations.langchain import SulciCache
from llama_index.llms.langchain import LangChainLLM
from langchain_openai import ChatOpenAI

set_llm_cache(SulciCache(backend="sqlite", context_window=4))

from llama_index.core import Settings
Settings.llm = LangChainLLM(llm=ChatOpenAI(model="gpt-4o"))
```

Install: `pip install "sulci[sqlite,langchain]" llama-index-llms-langchain langchain-openai`

---


## AsyncCache — non-blocking async wrapper

`AsyncCache` wraps `sulci.Cache` with `asyncio.to_thread()` so every cache
operation yields the event loop. The correct pattern for FastAPI, LangChain
async chains, LlamaIndex async agents, and any asyncio-based application.

```python
from sulci import AsyncCache

cache = AsyncCache(backend="sqlite", context_window=4)

# FastAPI endpoint — event loop never blocked
@app.post("/chat")
async def chat(query: str, session_id: str):
    response, sim, depth = await cache.aget(query, session_id=session_id)
    if response:
        return {"response": response, "source": "cache", "sim": sim}
    response = await call_llm(query)
    await cache.aset(query, response, session_id=session_id)
    return {"response": response, "source": "llm"}

# All Cache parameters work identically
cache = AsyncCache(
    backend        = "sqlite",
    threshold      = 0.85,
    context_window = 4,
    query_weight   = 0.70,
    api_key        = "sk-sulci-...",   # for Sulci Cloud
)
```

**Async methods:** `aget()`, `aset()`, `acached_call()`, `aget_context()`,
`aclear_context()`, `acontext_summary()`, `astats()`, `aclear()`

**Sync passthrough:** All sync methods (`get`, `set`, `stats`, `clear`) also
available — `AsyncCache` works in mixed sync/async codebases without switching types.

---
## Sulci Cloud — zero infrastructure option

Get a free API key at **[sulci.io/signup](https://sulci.io/signup)** and switch
to the managed backend with a single parameter change. Everything else stays identical.

```python
# Before — self-hosted (works today)
cache = Cache(backend="sqlite", threshold=0.85)

# After — managed cloud (zero other code changes)
cache = Cache(backend="sulci", api_key="sk-sulci-...", threshold=0.85)

# Or via environment variable — zero code changes at all
# export SULCI_API_KEY=sk-sulci-...
cache = Cache(backend="sulci", threshold=0.85)
```

**Free tier:** 50,000 requests/month. No credit card required.

### sulci.connect()

For apps that want to set the key once at startup and enable optional telemetry:

```python
import sulci

sulci.connect(
    api_key   = "sk-sulci-...",   # or set SULCI_API_KEY env var
    telemetry = True,             # default True — set False to disable reporting
)

cache = Cache(backend="sulci")    # picks up key from connect() automatically
```

**Telemetry is strictly opt-in.** Nothing is sent unless `sulci.connect()` is called.
`_telemetry_enabled = False` until you explicitly connect. Disable per-instance with
`Cache(backend="sulci", telemetry=False)`.

**Key resolution order:**

```
1. Explicit api_key= argument to Cache()
2. SULCI_API_KEY environment variable
3. Key stored by a prior sulci.connect() call
```

---

## Quickstart

### Stateless (v0.1 style)

```python
from sulci import Cache

cache = Cache(backend="sqlite", threshold=0.85)

# store a response
cache.set("How do I deploy to AWS?", "Use the AWS CLI with 'aws deploy'...")

# exact or semantic hit — returns 3-tuple
response, similarity, context_depth = cache.get("What's the process for deploying on AWS?")

if response:
    print(f"Cache hit (sim={similarity:.2f}): {response}")
else:
    # call your LLM here
    pass
```

### Context-aware (v0.2 style)

```python
from sulci import Cache

cache = Cache(
    backend        = "sqlite",
    threshold      = 0.85,
    context_window = 4,     # remember last 4 turns
    query_weight   = 0.70,  # α — weight of current query vs context
    context_decay  = 0.50,  # halve weight per older turn
)

# turn 1
cache.set("What is Python?", "Python is a high-level programming language.", session_id="s1")

# turn 2 — context from turn 1 blended into the lookup vector
response, sim, depth = cache.get("Tell me more about it", session_id="s1")
```

### Drop-in with `cached_call`

> **Requires:** `pip install "sulci[sqlite]" anthropic`
>
> ```bash
> export ANTHROPIC_API_KEY=sk-ant-...
> ```

```python
import anthropic
from sulci import Cache

cache = Cache(backend="chroma", threshold=0.85)
client = anthropic.Anthropic()

def call_llm(prompt: str) -> str:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

result = cache.cached_call(
    query  = "How do I deploy to AWS?",
    llm_fn = call_llm,
)

print(result["response"])
print(f"Source:  {result['source']}")       # "cache" or "llm"
print(f"Latency: {result['latency_ms']:.1f}ms")
```

Run it a second time with the same (or similar) question — `source` switches to `"cache"` and latency drops from ~2,000ms to under 10ms.

---

## API Reference

### Constructor

```python
cache = Cache(
    backend         = "sqlite",   # sqlite | chroma | faiss | qdrant | redis | milvus | sulci
    threshold       = 0.85,       # cosine similarity cutoff (0–1)
    embedding_model = "minilm",   # minilm | openai
    ttl_seconds     = None,       # None = no expiry
    personalized    = False,      # partition cache per user_id
    db_path         = "./sulci",  # on-disk path for sqlite / faiss
    context_window  = 0,          # turns to remember; 0 = stateless
    query_weight    = 0.70,       # α in blending formula
    context_decay   = 0.50,       # per-turn decay weight
    session_ttl     = 3600,       # session expiry in seconds
    api_key         = None,       # required when backend="sulci"
    telemetry       = True,       # set False to disable per-instance
)
```

### Methods

| Method                                                                                 | Returns                   | Description                                                        |
| -------------------------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------ |
| `cache.get(query, *, tenant_id=None, user_id=None, session_id=None)`                   | `(str\|None, float, int)` | response, similarity, context_depth (tenant_id added in v0.4.0)    |
| `cache.set(query, response, *, tenant_id=None, user_id=None, session_id=None, metadata=None)` | `None`                    | Store entry, advance context window                                |
| `cache.cached_call(query, llm_fn, *, tenant_id=None, user_id=None, session_id=None, cost_per_call=0.005)` | `dict`        | response, source, similarity, latency_ms, cache_hit, context_depth |
| `cache.get_context(session_id)`                                                        | `ContextWindow`           | Return session's context window                                    |
| `cache.clear_context(session_id)`                                                      | `None`                    | Reset session history                                              |
| `cache.context_summary(session_id=None)`                                               | `dict`                    | Snapshot of one or all sessions                                    |
| `cache.stats()`                                                                        | `dict`                    | hits, misses, hit_rate, saved_cost, total_queries, active_sessions |
| `cache.clear()`                                                                        | `None`                    | Evict all entries, reset stats and sessions                        |

> **Important:** `cache.get()` returns a **3-tuple** `(response, similarity, context_depth)` — not a 2-tuple like v0.1. Always unpack all three values.

### v0.5.0 additions

Two additive constructor kwargs for advanced deployments:

```python
from sulci import Cache, RedisSessionStore, TelemetrySink

cache = Cache(
    backend        = "sqlite",
    context_window = 4,
    session_store  = RedisSessionStore(redis_client),         # horizontal-scale sessions
    event_sink     = TelemetrySink("https://your.endpoint"),  # privacy-firewalled events
)
```

- `session_store=` accepts any `sulci.sessions.SessionStore` impl. Default `None` uses the legacy in-process manager (unchanged from v0.4.x).
- `event_sink=` accepts any `sulci.sinks.EventSink` impl. Default `None` uses `NullSink()` (no-op). Shipped sinks (`TelemetrySink`, `RedisStreamSink`) enforce a strict field allowlist — query text, response text, and embeddings never leave the process.
- `SyncCache` is now exported as a naming-symmetric alias for `Cache` (parallel to `AsyncCache`).

---

## Context-Aware Blending

When `context_window > 0`, Sulci Cache blends the current query vector with recent
conversation history before performing the similarity lookup:

```
lookup_vec = α · embed(query) + (1−α) · Σ(decay^i · turn_i)
```

- `α` = `query_weight` (default **0.70**) — how much the current query dominates
- `decay` = `context_decay` (default **0.50**) — halves weight per older turn
- Only **user query** vectors are stored in context (not LLM responses)
- Raw un-blended vectors stored in cache; blending happens at lookup time only

**Context-aware benchmark results (800 conversation pairs, context_window=4):**

| Domain              | Stateless | Context-aware | Δ           |
| ------------------- | --------- | ------------- | ----------- |
| customer_support    | 32%       | 88%           | **+56pp**   |
| developer_qa        | 80%       | 96%           | +16pp       |
| medical_information | 40%       | 60%           | +20pp       |
| **overall**         | **64.0%** | **81.6%**     | **+17.6pp** |

---

## Backends

| Backend         | ID       | Hit latency | Best for                                |
| --------------- | -------- | ----------- | --------------------------------------- |
| SQLite          | `sqlite` | <8ms        | Local dev, edge, serverless, zero infra |
| ChromaDB        | `chroma` | <10ms       | Fastest path to working, Python-native  |
| FAISS           | `faiss`  | <3ms        | GPU acceleration, massive scale         |
| Qdrant          | `qdrant` | <5ms        | Production, metadata filtering          |
| Redis + RedisVL | `redis`  | <1ms        | Existing Redis infra, lowest latency    |
| Milvus Lite     | `milvus` | <7ms        | Dev-to-prod without code changes        |
| **Sulci Cloud** | `sulci`  | <8ms        | **Zero infra — managed service**        |

All self-hosted backends are free tier or self-hostable at zero cost.

---

## Embedding Models

| ID       | Model                  | Dims | Latency | Notes                                        |
| -------- | ---------------------- | ---- | ------- | -------------------------------------------- |
| `minilm` | all-MiniLM-L6-v2       | 384  | 14ms    | **Default** — free, local, excellent quality |
| `openai` | text-embedding-3-small | 1536 | ~100ms  | Requires `OPENAI_API_KEY`                    |

The default `minilm` model runs entirely locally via `sentence-transformers`.
No network calls are made unless you explicitly configure `embedding_model="openai"`.

---

## Project Structure

```
.
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── LOCAL_SETUP.md
├── Makefile                    ← make smoke, make test, make test-all, make verify
├── NOTICE
├── README.md
├── benchmark
│   ├── README.md               ← benchmark methodology and results
│   └── run.py                  ← benchmark CLI (--context for context-aware pass)
├── examples
│   ├── anthropic_example.py    ← Anthropic Claude, context-aware, requires ANTHROPIC_API_KEY
│   ├── basic_usage.py          ← stateless cache demo, no API key needed
│   ├── context_aware.py        ← 4-demo walkthrough, fully offline
│   ├── context_aware_example.py← additional context-aware patterns
│   ├── langchain_example.py    ← LangChain integration, OpenAI/Anthropic/mock
│   ├── llamaindex_example.py   ← LlamaIndex integration, OpenAI/Anthropic/mock
│   └── async_example.py        ← AsyncCache demo, OpenAI/Anthropic/mock    (v0.3.7)
├── pyproject.toml              ← name="sulci", version="0.5.0"
├── setup.py
├── setup.sh                    ← one-shot setup: venv + install + smoke tests
├── smoke_test.py               ← core smoke test
├── smoke_test_langchain.py     ← LangChain integration smoke test
├── smoke_test_llamaindex.py    ← LlamaIndex integration smoke test
├── smoke_test_async.py         ← AsyncCache smoke test                     (v0.3.7)
├── sulci
│   ├── __init__.py             ← exports Cache, SyncCache, AsyncCache, ContextWindow,
│   │                              SessionStore (legacy), InMemorySessionStore,
│   │                              RedisSessionStore, EventSink, NullSink,
│   │                              TelemetrySink, RedisStreamSink, CacheEvent, connect()
│   │                              _SDK_VERSION = __version__   # derived from pyproject.toml
│   ├── backends
│   │   ├── __init__.py         ← empty — core.py loads backends via importlib
│   │   ├── chroma.py
│   │   ├── cloud.py            ← SulciCloudBackend (backend="sulci")
│   │   ├── faiss.py
│   │   ├── milvus.py
│   │   ├── qdrant.py
│   │   ├── redis.py
│   │   └── sqlite.py
│   ├── async_cache.py          ← AsyncCache non-blocking wrapper         (v0.3.7)
│   ├── context.py              ← ContextWindow + legacy SessionStore manager
│   ├── core.py                 ← Cache engine + B1 adapter (v0.5.0)
│   │                              telemetry= param, api_key= param,
│   │                              session_store= + event_sink= kwargs (v0.5.0)
│   ├── embeddings
│   │   ├── __init__.py
│   │   ├── minilm.py           ← default: all-MiniLM-L6-v2 (free, local)
│   │   └── openai.py           ← requires OPENAI_API_KEY
│   ├── sessions                ← v0.5.0 — SessionStore protocol package
│   │   ├── __init__.py
│   │   ├── protocol.py         ← public stable SessionStore protocol
│   │   ├── memory.py           ← InMemorySessionStore (default)
│   │   └── redis.py            ← RedisSessionStore (multi-replica)
│   ├── sinks                   ← v0.5.0 — EventSink protocol package
│   │   ├── __init__.py
│   │   ├── protocol.py         ← public stable EventSink + CacheEvent
│   │   ├── null.py             ← NullSink (default no-op)
│   │   ├── telemetry.py        ← TelemetrySink (HTTPS POST, allowlist-scrubbed)
│   │   └── redis_stream.py     ← RedisStreamSink (XADD, allowlist-scrubbed)
│   └── integrations
│       ├── __init__.py
│       ├── langchain.py        ← SulciCache(BaseCache) for LangChain  (v0.3.3)
│       └── llamaindex.py       ← SulciCacheLLM(LLM) for LlamaIndex    (v0.3.5)
└── tests
    ├── test_backends.py                —   9 tests: per-backend contract + persistence
    ├── test_cloud_backend.py           —  28 tests: SulciCloudBackend + Cache wiring
    ├── test_connect.py                 —  32 tests: sulci.connect(), _emit(), _flush()
    ├── test_context.py                 —  35 tests: ContextWindow, legacy SessionStore
    ├── test_core.py                    —  31 tests: cache.get/set, TTL, stats, personalization, tenant_id
    ├── test_integrations_langchain.py  —  27 tests: SulciCache LangChain adapter
    ├── test_integrations_llamaindex.py —  29 tests: SulciCacheLLM LlamaIndex wrapper
    ├── test_async_cache.py             —  25 tests: AsyncCache non-blocking wrapper       (v0.3.7)
    ├── test_qdrant_tenant_isolation.py —  11 tests: tenant_id partition isolation         (v0.4.0)
    ├── test_sessions.py                —  24 tests: SessionStore protocol + tenant isol.  (v0.5.0)
    ├── test_sinks.py                   —  15 tests: EventSink protocol + privacy allowlist (v0.5.0)
    ├── test_session_store_injection.py —  12 tests: Cache(session_store=, event_sink=)    (v0.5.0)
    └── compat/                         —  Backend + Embedder conformance suites

Plus: sulci/tests/compat/ — SessionStore + EventSink conformance suites (v0.5.0)
```

---

## Running Tests

```bash
# full suite — 212 tests total (7 skipped if optional backend deps not installed)
python -m pytest tests/ -v

# by file
python -m pytest tests/test_core.py -v                       # 27 tests
python -m pytest tests/test_context.py -v                    # 35 tests
python -m pytest tests/test_backends.py -v                   #  9 tests (skipped if dep missing)
python -m pytest tests/test_connect.py -v                    # 32 tests — sulci.connect() + telemetry
python -m pytest tests/test_cloud_backend.py -v              # 28 tests — SulciCloudBackend
python -m pytest tests/test_integrations_langchain.py -v     # 27 tests — LangChain integration
python -m pytest tests/test_integrations_llamaindex.py -v    # 29 tests — LlamaIndex integration
python -m pytest tests/test_async_cache.py -v                # 25 tests — AsyncCache wrapper

# single backend only
python -m pytest tests/test_backends.py -v -k sqlite
python -m pytest tests/test_backends.py -v -k chroma

# with coverage
python -m pytest tests/ -v --cov=sulci --cov-report=term-missing
```

### Make targets

```bash
make smoke              # all smoke tests (core + LangChain + LlamaIndex)
make smoke-core         # core smoke test only
make smoke-langchain    # LangChain smoke test only
make smoke-llamaindex   # LlamaIndex smoke test only
make smoke-async        # AsyncCache smoke test only
make test               # core pytest suite
make test-integrations  # LangChain + LlamaIndex integration tests
make test-async         # AsyncCache tests only
make test-all           # full suite (212 tests)
make test-cov           # full suite with coverage
make verify             # smoke + test-all (run before committing)
```

`test_connect.py` (32 tests) — `sulci.connect()`, `_emit()`, `_flush()`, `Cache(telemetry=)`. Requires `httpx`.

`test_cloud_backend.py` (28 tests) — `SulciCloudBackend` construction, `search()`, `upsert()`, `delete_user()`, `clear()`, and `Cache(backend='sulci')` wiring. Requires `httpx`.

`test_integrations_langchain.py` (27 tests) — `SulciCache(BaseCache)` LangChain adapter. Requires `langchain-core`.

`test_integrations_llamaindex.py` (29 tests) — `SulciCacheLLM(LLM)` LlamaIndex wrapper. Requires `llama-index-core`.

Backend tests are **skipped — not failed** when their dependency isn't installed.
Install the backend extra to run its tests: `pip install -e ".[chroma]"`.

See [`LOCAL_SETUP.md`](./LOCAL_SETUP.md) for the full local development guide including
venv setup, backend installation, smoke testing, and troubleshooting.

---

## Examples

```bash
python examples/basic_usage.py          # stateless cache — no API key needed
python examples/context_aware.py        # context-aware — no API key needed
python examples/anthropic_example.py    # requires ANTHROPIC_API_KEY
python examples/langchain_example.py    # OpenAI or Anthropic or mock fallback
python examples/llamaindex_example.py   # OpenAI or Anthropic or mock fallback
python examples/async_example.py        # AsyncCache demo, OpenAI/Anthropic/mock
```

---

## Benchmark

```bash
# fast run (~30 seconds)
python benchmark/run.py --no-sweep --queries 1000

# with context-aware pass
python benchmark/run.py --no-sweep --queries 1000 --context

# full benchmark
python benchmark/run.py --context
```

See [`benchmark/README.md`](./benchmark/README.md) for full methodology and results.

---

## Troubleshooting

### `ImportError: cannot import name 'HfFolder' from 'huggingface_hub'`

Conda environments often have a stale `huggingface_hub` that conflicts with `sentence-transformers`. Fix by upgrading all three together:

```bash
pip install --upgrade huggingface_hub datasets sentence-transformers
```

Or use a clean venv (avoids conda transitive dependency conflicts entirely):

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install "sulci[sqlite]" anthropic
python your_script.py
```

### `huggingface/tokenizers: The current process just got forked...` warning

Harmless — suppress it with:

```bash
export TOKENIZERS_PARALLELISM=false
```

### `anthropic.OverloadedError: Error code: 529`

Transient API congestion — not a Sulci Cache issue. Wait a moment and retry, or check [status.anthropic.com](https://status.anthropic.com).

### `zsh: no matches found: sulci[chroma]`

Wrap extras in quotes:

```bash
pip install "sulci[chroma]"    # ✓
pip install sulci[chroma]      # ✗ — zsh glob expansion breaks this
```

### `pytest: command not found`

```bash
python -m pytest tests/ -v
```

---

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for branching model, PR process, and coding standards.

---

## License

Apache License 2.0 — see [`LICENSE`](./LICENSE).

Copyright 2026 Kathiravan Sengodan.

U.S. Patent Application No. 64/018,452 (pending) covers the
context-aware semantic caching algorithm. Apache 2.0 grants users
a royalty-free patent license for use of this code.

---

## Links

- **Website:** [sulci.io](https://sulci.io?utm_source=github&utm_medium=readme&utm_campaign=oss)
- **Sign up (free key):** [sulci.io/signup](https://sulci.io/signup?utm_source=github&utm_medium=readme&utm_campaign=oss)
- **API:** [api.sulci.io](https://api.sulci.io)
- **PyPI:** [sulci](https://pypi.org/project/sulci/)
- **GitHub:** [sulci-io/sulci-oss](https://github.com/sulci-io/sulci-oss)
- **Issues:** [github.com/sulci-io/sulci-oss/issues](https://github.com/sulci-io/sulci-oss/issues)
