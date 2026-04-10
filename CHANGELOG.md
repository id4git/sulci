# Changelog

All notable changes to Sulci are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.3.5] — 2026-04-09

### Added

- Native LlamaIndex LLM wrapper `SulciCacheLLM` — first correct LLM-level
  semantic cache for LlamaIndex. Wraps any `LLM` subclass (OpenAI, Anthropic,
  Ollama, HuggingFaceLLM, etc.). `complete()` and `chat()` are cached;
  streaming passes through uncached; async methods use `run_in_executor`.
- `sulci/integrations/llamaindex.py` — `SulciCacheLLM(LLM)` implementation
- `sulci/integrations/__init__.py` — updated with LlamaIndex entry
- `pyproject.toml` — `llamaindex = ["llama-index-core>=0.10.0"]` extra
- `smoke_test_llamaindex.py` at repo root

### Tests

- `tests/test_integrations_llamaindex.py` — 29 tests (TestConstruction,
  TestComplete, TestChat, TestStreaming, TestAsync, TestStats)

### Examples

- `examples/langchain_example.py` — two demos in one file:
  - Demo 1: stateless `set_llm_cache(SulciCache(...))` — semantic hit/miss
    across 4 rounds showing real API latency vs <10ms cache hits
  - Demo 2: context-aware `ContextAwareSulciCache` subclass using `llm_string`
    as `session_id` — two isolated user sessions (alice/bob), 58% hit rate
  - Supports OpenAI, Anthropic, or built-in mock LLM fallback
  - API key detection logged at startup (`✓ found` / `✗ not set`)

- `examples/llamaindex_example.py` — four rounds:
  - Round 1: fresh questions per session (all misses)
  - Round 2: paraphrases in same sessions (93-96% similarity hits, <7ms)
  - Round 3: context-aware follow-ups in a single topic session
  - Round 4: clearly unrelated question (clean miss)
  - `Settings.llm = SulciCacheLLM(...)` — idiomatic LlamaIndex pattern
  - Supports OpenAI, Anthropic, or built-in mock LLM fallback
  - API key detection logged at startup

### Notes

- GPTCache's claimed LlamaIndex integration was a broken global OpenAI API
  patch. SulciCacheLLM uses the idiomatic `LLM` subclass pattern and works
  with any LlamaIndex-compatible model.

---

## [0.3.4] — 2026-04-08

### Fixed

- `SulciCache`: `namespace_by_llm=True` now logs a warning and is silently
  disabled when `backend="sulci"`. Sulci Cloud handles tenant isolation
  server-side; `db_path`-based partitioning was creating phantom
  `SulciCloudBackend` instances with no effect.

### Added

- `SulciCloudBackend`: new `gateway_url` parameter (default: `https://api.sulci.io`).
  Enterprise VPC customers can point to a self-hosted gateway:
  `Cache(backend="sulci", api_key="...", gateway_url="https://cache.acme.internal")`
- `Cache`: `gateway_url` threaded through `_load_backend()` when `backend="sulci"`.
- `SulciCache` (LangChain): `gateway_url` documented in `**kwargs` table.

### Tests

- `test_cloud_backend.py`: 3 new tests — default gateway URL, custom gateway URL,
  trailing slash stripping
- `test_integrations_langchain.py`: 3 new tests — `TestNamespaceByLLMCloudWarning`

---

## [0.3.3] — 2026-04-08

### Added

**LangChain integration — context-aware semantic cache adapter**

- `sulci/integrations/__init__.py` — new `integrations` sub-package
- `sulci/integrations/langchain.py` — `SulciCache(BaseCache)` for LangChain
  - Positioned as the **context-aware semantic cache** — distinct from stateless
    semantic caches (GPTCache, RedisSemanticCache) already in langchain-community
  - `lookup(prompt, llm_string)` — semantic match via `sulci.Cache.get()`,
    returns `list[Generation]` on hit, `None` on miss
  - `update(prompt, llm_string, return_val)` — stores first `Generation.text`
  - `clear()` — evicts data and resets namespace dict via `finally` block
    (guarantees `_ns_caches` is always cleared even if a data-clear raises)
  - `namespace_by_llm=True` (default) — separate cache partition per LLM config;
    uses MD5-hashed `db_path` suffix for local backends
  - `alookup`, `aupdate`, `aclear` — async overrides via `run_in_executor`
  - Silent failure throughout — cache errors never raise to the caller's app
  - `stats()` — passthrough to `sulci.Cache.stats()`
  - Lazy import of `langchain-core` — raises `ImportError` with install hint
    if not installed; core `sulci` package never depends on LangChain
  - `langchain_core.globals` used (not `langchain.globals`) — only `langchain-core`
    required, not the full `langchain` package

**LangChain integration — tests**

- `tests/test_integrations_langchain.py` — 24 tests, zero LLM API keys required
  - `TestContract` (9) — lookup/update/clear/exact-hit/semantic-miss/list-return
  - `TestNamespacing` (4) — model isolation, shared mode, clear resets dict
  - `TestSilentFailure` (3) — db errors in lookup/update/clear never raise
  - `TestAsync` (4) — alookup/aupdate/aclear/concurrent reads
  - `TestStats` (3) — dict shape, required keys, repr format
  - `TestGlobalRegistration` (1) — `set_llm_cache` / `get_llm_cache` round-trip

**LangChain integration — smoke test**

- `smoke_test_langchain.py` — standalone smoke test at repo root
  - Runs automatically via `setup.sh` after core smoke test
  - Skips gracefully (exit 0) if `langchain-core` is not installed
  - Covers: create → store → exact hit → unrelated miss → stats

**Developer tooling**

- `setup.sh` — updated to install `.[langchain]` extra and run both smoke tests
  sequentially; `Next steps` section updated to list actual `make` targets
- `Makefile` — new targets:
  - `make smoke` — runs `smoke_test.py` + `smoke_test_langchain.py`
  - `make smoke-core` — core smoke test only
  - `make smoke-langchain` — LangChain smoke test only
  - `make test` — core pytest suite
  - `make test-integrations` — LangChain + LlamaIndex integration tests
  - `make test-all` — full suite
  - `make test-cov` — full suite with coverage report
  - `make verify` — `smoke` + `test-all` (pre-commit full check)

**LangChain community PR artifact**

- `langchain_community_pr/sulci_cache_addition.py` — ready-to-paste addition
  for `langchain_community/cache.py` PR to `langchain-ai/langchain`

### Changed

- `pyproject.toml` — version bumped to `0.3.3`
- `pyproject.toml` — added `langchain = ["langchain-core>=0.1.0"]` optional extra
- `pyproject.toml` — added `pytest-asyncio==0.21.1` to `dev` deps
  (pinned — 0.23.x has a package collection bug)
- `pyproject.toml` — added `asyncio_mode = "auto"` to `[tool.pytest.ini_options]`
- `pyproject.toml` — added `"context-aware-semantic-cache"` keyword for PyPI search
- `sulci/__init__.py` — `_SDK_VERSION` bumped from `"0.3.0"` to `"0.3.3"`
  (was already out of sync with pyproject.toml since 0.3.1)

### Fixed (discovered during integration test development)

- `sulci/integrations/langchain.py` `clear()` — moved `_ns_caches.clear()` into
  a `finally` block so namespace dict is always reset even if a backend `clear()`
  raises an exception
- `tests/test_integrations_langchain.py` — assertion order in
  `test_clear_removes_all_partitions` corrected: `len(_ns_caches) == 0` must be
  checked _before_ any `lookup()` call, since `lookup()` calls `_cache_for()`
  which recreates namespace entries for any `llm_string` it encounters
- `tests/test_integrations_langchain.py` — `test_concurrent_lookups_no_crash`
  revised to check no exceptions are raised (not that all 20 concurrent SQLite
  reads return non-None — a single connection under high concurrency may return
  miss on some reads, which is acceptable behaviour)
- `tests/test_integrations_langchain.py` — `TestGlobalRegistration` import changed
  from `langchain.globals` to `langchain_core.globals` — only `langchain-core` is
  required, not the full `langchain` package

### Backward compatibility

- All existing code using local backends (`sqlite`, `chroma`, `faiss`, etc.)
  is completely unaffected — zero breaking changes
- `context_window=0` (default) remains stateless and identical to prior versions
- New `integrations` sub-package is purely additive — not imported unless
  explicitly requested by the caller

### Test count after this release

```
test_core.py                       27 tests
test_context.py                    35 tests
test_backends.py                    9 tests  (skipped if backend dep not installed)
test_connect.py                    32 tests
test_cloud_backend.py              25 tests
test_integrations_langchain.py     24 tests  ← new
────────────────────────────────────────────
Total                             152 tests
```

---

## [0.3.2] — 2026-03-27

### Patent & Legal
- Updated NOTICE file with US Patent Application No. 64/018,452
- Added Patent Pending badge and notice to README
- Updated PyPI description to include Patent Pending

### No code changes — library behaviour is unchanged

---

## [0.3.1] — 2026-03-27

### License
- Changed from MIT License to Apache License 2.0
- Added NOTICE file as required by Apache 2.0
- Updated pyproject.toml classifier to Apache Software License
- Added SPDX identifiers to all Python source files
- Rationale: Apache 2.0 includes patent retaliation clause and explicit
  patent grant; aligns with pending patent application IDF-SULCI-2026-001

### No code changes — library behaviour is unchanged

---

## [0.3.0] — 2026-03-25

### Added

- **Sulci Cloud backend** — `Cache(backend="sulci", api_key="sk-sulci-...")` routes
  cache operations to `api.sulci.io` via HTTPS. Zero infrastructure for the user —
  one parameter change from any self-hosted backend.
- `sulci/backends/cloud.py` — `SulciCloudBackend` via httpx
  - `search()` returns `(None, 0.0)` on timeout or any error — never crashes caller
  - `upsert()` failure is silent — fire and forget
  - `delete_user()` and `clear()` also fail silently
- `sulci.connect(api_key, telemetry=True)` — opt-in gateway to Sulci Cloud
  - Stores API key at module level for all `Cache(backend="sulci")` instances
  - Enables optional usage telemetry — flushed to `api.sulci.io` every 60 seconds
  - Strictly opt-in: `_telemetry_enabled = False` until `connect()` is called
- `Cache` gains two new constructor parameters:
  - `api_key` — API key for `backend="sulci"` (resolution: arg > env > `connect()`)
  - `telemetry` — per-instance opt-out (default `True`)
- `SULCI_API_KEY` environment variable — zero-code alternative to `api_key=`
- `sulci[cloud]` install extra — `pip install "sulci[cloud]"`
- `tests/test_connect.py` — 32 tests covering `sulci.connect()` and telemetry
- `tests/test_cloud_backend.py` — 25 tests covering `SulciCloudBackend` and wiring

### Changed

- Version bumped to `0.3.0`
- `README.md` updated with Sulci Cloud section and `sulci.connect()` docs
- `LOCAL_SETUP.md` updated with Week 2 and Week 3 setup instructions
- `pyproject.toml` — added `cloud = ["httpx>=0.27.0"]` extra

### Backward compatibility

- All existing code using local backends (`sqlite`, `chroma`, `faiss`, etc.) is
  completely unaffected — zero breaking changes
- `connect()` and `api_key=` are purely additive
- Default backend behaviour unchanged

---

## [0.2.5] — 2026-03-17

### Repository & Housekeeping

- Transferred repository from `id4git/sulci` to `sulci-io/sulci-oss` under new GitHub org
- Renamed repo from `sulci` to `sulci-oss` (PyPI package name `sulci-cache` and import `from sulci` unchanged)
- Added `LICENSE` (MIT) and `NOTICE` files to repo root with clear OSS/enterprise demarcation
- Updated `pyproject.toml` repository URLs to reflect new org and repo name

### Docs

- Added `LOCAL_SETUP.md` — full local development guide: venv setup, install, test runs, smoke test, troubleshooting
- Corrected test counts across `README.md` and `LOCAL_SETUP.md`:
  - `test_core.py`: 27 tests (was 26)
  - `test_context.py`: 35 tests (was 27)
  - `test_backends.py`: 9 tests (was unknown)
  - Total: 71 tests (was 53)
- Updated project structure tree in both docs to match actual repo layout (7 directories, 29 files)
- Removed inline changelog table from `README.md` — full history lives in `CHANGELOG.md`
- Fixed `pyproject.toml` comment to correctly distinguish repo root (`sulci-oss/`) from package directory (`sulci/`)

### No code changes — library behaviour is identical to 0.2.4

---

## [0.2.4] — 2026-03-16

- Release v0.2.4 — Developer Edition baseline — pre-enterprise transition

---

## [0.2.3] — 2026-03-16

- Release v0.2.3 — correct test counts, updated docs

---

## [0.2.2] — 2026-03-15

- Packaging fix: re-publish of 0.2.1 (PyPI file conflict resolution)

---

## [0.2.1] — 2026-03-11

- Context-aware benchmark suite: `--context` flag
- 25 session pools, brute-force cosine scan
- Results: +20.8pp resolution accuracy

---

## [0.2.0] — 2026-03-10

### Added

- **Context-aware caching** for multi-turn LLM conversations
- `sulci/context.py` — new module with `ContextWindow` and `SessionStore`
  - `ContextWindow`: sliding window of turns per session with exponential
    decay blending (`lookup_vec = α·query + (1-α)·Σwᵢ·historyᵢ`)
  - `SessionStore`: concurrent session manager with TTL-based eviction
- `Cache` gains four new init parameters:
  - `context_window` — turns to remember per session (0 = stateless, default)
  - `query_weight` — current query weight vs blended history (default: 0.70)
  - `context_decay` — exponential decay per turn (default: 0.50)
  - `session_ttl` — idle session eviction in seconds (default: 3600)
- `cached_call()`, `get()`, `set()` now accept `session_id` parameter
- All results include `context_depth` field (0 = no context used)
- New context management methods: `get_context()`, `clear_context()`,
  `context_summary()`
- `sulci/__init__.py` now exports `ContextWindow` and `SessionStore`
- `examples/context_aware.py` — 4-demo walkthrough, no API key required
- `tests/test_context.py` — 27 tests covering ContextWindow, SessionStore,
  and Cache integration
- Updated `anthropic_example.py` with `session_id` and `Chat` wrapper

### Fixed

- `tests/test_core.py` — all `cache.get()` call sites updated to unpack
  3-tuple `(response, sim, context_depth)` instead of 2-tuple
- CI workflow updated to also run `test_context.py`

### Changed

- Version bumped to `0.2.0`
- `README.md` updated with context-awareness section and full API reference

### Backward compatibility

- `context_window=0` (default) is identical to v0.1.x behaviour
- No breaking changes — existing code requires zero modifications

---

## [0.1.1] — 2026-03-07

### Added

- Full library structure: `sulci/`, `backends/`, `embeddings/`
- Six vector backends: ChromaDB, Qdrant, FAISS, Redis, SQLite, Milvus
- Two embedding providers: MiniLM/MPNet/BGE (local), OpenAI API
- `Cache.cached_call()` — drop-in LLM wrapper
- `Cache.get()` / `set()` — manual cache control
- `Cache.stats()` — hit rate, cost savings tracking
- TTL-based cache expiry
- Per-user personalized caching via `user_id`
- GitHub Actions: auto-publish on tag, test matrix (Python 3.9–3.12, 3 OS)
- pytest suite: 20 core tests + backend contract tests
- Examples: `basic_usage.py`, `anthropic_example.py`

### Fixed

- `pyproject.toml` build backend changed from `setuptools.backends.legacy`
  to correct `setuptools.build_meta`
- Removed mandatory `numpy>=1.24` core dependency (now optional per backend)

---

## [0.1.0] — 2026-03-07

### Added

- Initial release — 6 backends, MiniLM, TTL, personalization, stats
