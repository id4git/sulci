# Sulci Cache — Local Setup Guide

Everything you need to clone the repo, install dependencies, run tests, and verify a working local environment from scratch.

---

## Requirements

- Python **3.9, 3.10, 3.11, or 3.12** (all four are tested in CI)
- `git`
- A terminal with `pip` available

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/sulci-io/sulci-oss.git
cd sulci-oss
```

All active development is on `main`. Feature branches are short-lived and merge
to `main` via PR.

---

## Step 2 — Create and Activate a Virtual Environment

Always use a virtual environment. Never install Sulci dependencies into your system Python.

```bash
# create
python -m venv .venv

# activate — macOS / Linux
source .venv/bin/activate

# activate — Windows
.venv\Scripts\activate

# confirm you're inside the venv
which python        # should show .venv/bin/python
python --version    # should be 3.9, 3.11, or 3.12  (tested in CI; 3.10 likely works but isn't gated)
```

---

## Step 3 — Install the Library

Install in editable mode (`-e`) so any changes you make to `sulci-oss/` source code are reflected immediately without reinstalling.

```bash
# base install — editable
pip install -e .

# with the SQLite backend (zero infra, fully offline — recommended for local dev)
pip install -e ".[sqlite]"

# with the LangChain integration (langchain-core only, not full langchain)
pip install -e ".[sqlite,langchain]"

# with the LlamaIndex integration
pip install -e ".[sqlite,llamaindex]"

# AsyncCache is included in the base install — no extra required
# pip install -e ".[sqlite]"  ← AsyncCache works with any backend

# with ChromaDB
pip install -e ".[chroma]"

# with FAISS
pip install -e ".[faiss]"

# multiple backends at once
pip install -e ".[sqlite,chroma,faiss]"

# full dev setup — recommended
pip install -e ".[sqlite,langchain,llamaindex,dev]"
```

> **zsh users:** always wrap extras in quotes — `".[sqlite]"` not `.[sqlite]`.
> Without quotes, zsh treats the brackets as a glob pattern and throws `no matches found`.

> **Why httpx?** The `test_connect.py` and `test_cloud_backend.py` suites mock
> `httpx.post` to test telemetry and cloud wiring — httpx must be installed even
> though it is only used in tests.

---

## Step 4 — Verify the Install

```bash
python -c "
from sulci import Cache, ContextWindow, SessionStore, connect
from sulci.backends.cloud import SulciCloudBackend
from sulci.integrations.langchain import SulciCache
from sulci.integrations.llamaindex import SulciCacheLLM
from sulci import AsyncCache
print('Import OK')
"
```

Expected output:

```
Import OK
```

If you see a `ModuleNotFoundError` on a backend (e.g. `chromadb`, `faiss`), that backend's
extra is not installed. Install it with `pip install -e ".[backend_name]"`.

If you see `ModuleNotFoundError: langchain_core`, install the langchain extra:

```bash
pip install -e ".[langchain]"
```

If you see `ModuleNotFoundError: llama_index`, install the llamaindex extra:

```bash
pip install -e ".[llamaindex]"
```

---

## Step 5 — Run the Tests

Always use `python -m pytest` rather than bare `pytest` to avoid PATH issues.

```bash
python -m pytest tests/ -v
```

All **212 tests** should be collected across eight test files (205 pass, 7 skipped if optional backend deps not installed):

```
tests/test_core.py                    — 27 tests  (cache.get/set, thresholds, TTL, stats, personalization)
tests/test_context.py                 — 35 tests  (ContextWindow, SessionStore, integration)
tests/test_backends.py                —  9 tests  (per-backend contract + persistence; skipped if dep missing)
tests/test_connect.py                 — 32 tests  (sulci.connect(), _emit(), _flush(), Cache telemetry flag)
                                                   requires httpx
tests/test_cloud_backend.py           — 28 tests  (SulciCloudBackend, Cache(backend='sulci') wiring)
                                                   requires httpx
tests/test_integrations_langchain.py  — 27 tests  (SulciCache LangChain adapter)     (v0.3.3)
tests/test_integrations_llamaindex.py — 29 tests  (SulciCacheLLM LlamaIndex wrapper) (v0.3.6)
                                                   requires llama-index-core
```

### Targeted test runs

```bash
# core cache logic only
python -m pytest tests/test_core.py -v

# context and session tests only
python -m pytest tests/test_context.py -v

# backend tests only
python -m pytest tests/test_backends.py -v

# telemetry + sulci.connect() tests only
python -m pytest tests/test_connect.py -v

# SulciCloudBackend + Cache wiring tests only
python -m pytest tests/test_cloud_backend.py -v

# LangChain integration tests only
python -m pytest tests/test_integrations_langchain.py -v

# LlamaIndex integration tests only
python -m pytest tests/test_integrations_llamaindex.py -v

# single backend by keyword
python -m pytest tests/test_backends.py -v -k sqlite
python -m pytest tests/test_backends.py -v -k chroma

# one specific test by name
python -m pytest tests/test_core.py::TestBasicOperations::test_semantic_hit -v

# stop at first failure
python -m pytest tests/ -v -x

# with line-level coverage report
python -m pytest tests/ -v --cov=sulci --cov-report=term-missing
```

### Make targets

```bash
make test               # core pytest suite (excludes integrations)
make test-integrations  # LangChain + LlamaIndex integration tests
make test-async         # AsyncCache tests only
make test-all           # full suite (187 tests)
make test-cov           # full suite with coverage report
make verify             # smoke + test-all (run before committing)
```

---

## Step 6 — Run the Examples

### No API key required

```bash
# stateless cache demo
python examples/basic_usage.py

# context-aware demo — 4 walkthroughs, fully offline
python examples/context_aware.py

# additional context-aware patterns
python examples/context_aware_example.py
```

### Requires `ANTHROPIC_API_KEY`

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/anthropic_example.py    # Anthropic Claude + context-aware
```

### LangChain and LlamaIndex integration examples

These work with OpenAI, Anthropic, or a built-in mock LLM — API key is optional.

```bash
# set one or both keys (optional — mock LLM used if neither is set)
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

python examples/langchain_example.py    # LangChain: stateless + context-aware demo
python examples/llamaindex_example.py   # LlamaIndex: Settings.llm = SulciCacheLLM
python examples/async_example.py        # AsyncCache demo — FastAPI pattern shown
```

Each example prints which LLM is active at startup:

```
── API key detection ──────────────────────────────
  OPENAI_API_KEY    : ✓ found
  ANTHROPIC_API_KEY : ✗ not set
  → Using: OpenAI gpt-4o-mini
```

Priority: OpenAI → Anthropic → mock. To force Anthropic: `unset OPENAI_API_KEY`.

---

## Step 7 — Run the Benchmark

```bash
# fast run — stateless, 1,000 queries (~30 seconds)
python benchmark/run.py --no-sweep --queries 1000

# fast run — with context-aware mode
python benchmark/run.py --no-sweep --queries 1000 --context

# full benchmark — stateless, 5,000 queries
python benchmark/run.py

# full benchmark — with context-aware mode
python benchmark/run.py --context
```

Results are written to `benchmark/results/`. The `.gitignore` in that directory
excludes `*.json` and `*.csv` so result files are never committed.

### All benchmark flags

| Flag                    | Default             | Description                                       |
| ----------------------- | ------------------- | ------------------------------------------------- |
| `--context`             | off                 | Enable context-aware benchmark pass               |
| `--no-sweep`            | off                 | Skip threshold sweep (much faster)                |
| `--queries N`           | 5000                | Number of test queries                            |
| `--threshold F`         | 0.85                | Similarity threshold for stateless pass           |
| `--context-threshold F` | 0.58                | Similarity threshold for context pass             |
| `--context-window N`    | 4                   | Turns per session window                          |
| `--use-sulci`           | off                 | Use real MiniLM embeddings (vs TF-IDF simulation) |
| `--out DIR`             | `benchmark/results` | Output directory for result files                 |

---

## Step 8 — Smoke Tests (Quick End-to-End Sanity Check)

Smoke test scripts live at the repo root. Run individually or together via
`make smoke` to confirm the full stack is working end-to-end.

```bash
# All smoke tests in sequence (recommended)
make smoke

# Or individually
python smoke_test.py               # core — no API key needed
python smoke_test_langchain.py     # LangChain integration — no API key needed
python smoke_test_llamaindex.py    # LlamaIndex integration — no API key needed
python smoke_test_async.py         # AsyncCache — no API key needed
```

`smoke_test.py` covers: stateless cache, semantic hit, stats, and context-aware mode.

`smoke_test_langchain.py` covers: `SulciCache` lookup/update/miss/stats via
`langchain_core.globals`. Skips gracefully (exit 0) if `langchain-core` is not installed.

`smoke_test_llamaindex.py` covers: `SulciCacheLLM` wrapping a mock LLM, complete/chat
hit/miss, streaming pass-through, and stats. Skips gracefully if `llama-index-core`
is not installed.

`smoke_test_async.py` covers: `AsyncCache` construction, `aset`, `aget` hit/miss,
`acached_call`, context methods, `astats`, `aclear`, and sync passthrough. No API key
required — runs entirely offline.

### Make targets

```bash
make smoke              # all smoke tests in sequence
make smoke-core         # core smoke test only (smoke_test.py)
make smoke-langchain    # LangChain smoke test only (smoke_test_langchain.py)
make smoke-llamaindex   # LlamaIndex smoke test only (smoke_test_llamaindex.py)
make smoke-async        # AsyncCache smoke test only (smoke_test_async.py)
```

---

## Step 8.5 — Pre-PR Verification with Runner Scripts

When you're about to open a PR, the `scripts/` directory provides three
runners that wrap the most common pre-commit verification flows. Each one
runs sequentially across many files in fresh subprocesses, captures
pass/fail per file, and prints a summary table at the end. Failure logs
are saved to `/tmp/sulci-*-runner/` for later inspection.

### Why these scripts exist

Several integration tests construct multiple `MiniLMEmbedder` instances
in one process. On Apple Silicon (MPS), this occasionally deadlocks at
`embeddings.cpu()` under memory pressure. The runner scripts launch each
test file (or example) in its own Python subprocess, giving each a clean
MiniLM cold-start and avoiding the deadlock. Trade-off: each subprocess
pays its own ~30-40s warmup, so wall-clock is longer than a single
`pytest tests/` invocation. CI doesn't need this — it runs on Linux
without MPS — but local development on M-series Macs benefits.

### Make targets

```bash
make test-per-file              # all test files in fresh subprocesses (~10-15 min)
make test-per-file-fast         # skip the slowest 4 files (~3-5 min, faster iteration)
make examples                   # all examples + smoke tests with timeout (~10-15 min)
make verify-integration-examples  # full 4-scenario LLM-provider matrix for langchain
                                  # + llamaindex (~10-15 min, requires both API keys,
                                  # ~$0.10-0.20 in real LLM calls per run)
make benchmark-verify           # run TF-IDF benchmark, verify against baseline.json (~15s)
make checkin                    # smoke + test-per-file + examples + benchmark-verify (pre-PR check)
```

### When to use which

| If you changed... | Run |
|---|---|
| `sulci/` source code | `make test-per-file` |
| `examples/*.py` or `smoke_test*.py` | `make examples` |
| `examples/langchain_example.py` or `examples/llamaindex_example.py` | `make verify-integration-examples` |
| `benchmark/` files or anything that touches headline numbers | `make benchmark-verify` |
| Anything before opening a PR | `make checkin` |

### Direct script invocation

The runners support direct invocation if you want to override defaults
like timeout or filter to specific files:

```bash
python scripts/run_tests_per_file.py --help
python scripts/run_examples.py --help
python scripts/verify_integration_examples.py --help
```

For example, to run only the four fast test files with a tight
60-second timeout:

```bash
python scripts/run_tests_per_file.py \
    --files tests/test_backends.py tests/test_cloud_backend.py \
            tests/test_connect.py tests/compat/ \
    --timeout 60
```

### What `make checkin` produces

A successful run prints a summary like
`TOTAL: 285 passed, 0 failed, 0 errors, 38 skipped`, then the examples
summary `TOTAL: 12/12 passed`, then a final banner. If anything fails,
the failure log path is printed in the per-file summary table so you
can `cat` the relevant log rather than re-running with extra flags.

### Adding new runner scripts

If you add a new dev-tooling script:

1. Make it a `#!/usr/bin/env python3` script in `scripts/` with `chmod +x`
2. Use `argparse` with a `--help` that explains preconditions and exit codes
3. Use `subprocess.run(timeout=...)` rather than the GNU `timeout` command
   (macOS doesn't ship `timeout` by default; `subprocess.run` is portable)
4. Save per-target logs to `/tmp/<runner-name>/`
5. Add a Makefile target so contributors don't have to remember the
   invocation
6. Update `scripts/README.md` and this section

---

## Step 9 — Test sulci.connect() Locally

`sulci.connect()` is the opt-in telemetry gate. The default state
is **silent** — nothing is sent until you explicitly call `connect()`.

### Verify default state

```python
import sulci

# Before connect() — everything is off
print(sulci._telemetry_enabled)    # False
print(sulci._api_key)              # None
print(sulci._event_buffer)         # []
```

### Test connect() with a real key

```python
import sulci

# Option 1 — explicit key
sulci.connect(api_key="sk-sulci-...")
print(sulci._telemetry_enabled)    # True
print(sulci._api_key)              # sk-sulci-...

# Option 2 — from environment variable
# export SULCI_API_KEY=sk-sulci-...
sulci.connect()
print(sulci._api_key)              # sk-sulci-...

# Option 3 — connect but disable telemetry reporting
sulci.connect(api_key="sk-sulci-...", telemetry=False)
print(sulci._telemetry_enabled)    # False (key stored, no reporting)
```

### Disable telemetry per Cache instance

```python
# Even after connect(), an individual Cache can opt out
cache = sulci.Cache(backend="sqlite", telemetry=False)
print(cache._telemetry)            # False
```

### Key resolution order

When `backend="sulci"` is used, the API key is resolved in this order:

```
1. Explicit api_key= argument to Cache()
2. SULCI_API_KEY environment variable
3. Key stored by a prior sulci.connect() call
```

### Run only the connect tests

```bash
python -m pytest tests/test_connect.py -v

# Run a specific class
python -m pytest tests/test_connect.py::TestDefaultState -v
python -m pytest tests/test_connect.py::TestConnect -v
python -m pytest tests/test_connect.py::TestEmit -v
python -m pytest tests/test_connect.py::TestFlush -v
python -m pytest tests/test_connect.py::TestCacheIntegration -v
python -m pytest tests/test_connect.py::TestThreadSafety -v
```

---

## Step 10 — Test SulciCloudBackend Locally

`SulciCloudBackend` is the cloud backend driver. It routes cache operations
to `api.sulci.io` via httpx.

### Verify the import and basic construction

```python
from sulci.backends.cloud import SulciCloudBackend

# Confirm ValueError on missing key
try:
    b = SulciCloudBackend(api_key=None)
except ValueError as e:
    print(f"ValueError ok: {e}")

# Confirm repr
b = SulciCloudBackend(api_key="sk-sulci-testkey1234567")
print(b)
# SulciCloudBackend(url='https://api.sulci.io', key_prefix='sk-sulci-testke', timeout=5.0)
```

### Verify Cache constructor wiring

```python
from unittest.mock import patch
from sulci import Cache

# Explicit key
with patch("sulci.backends.cloud.SulciCloudBackend") as MockBackend:
    MockBackend.return_value = MockBackend
    cache = Cache(backend="sulci", api_key="sk-sulci-testkey1234567")
    print(f"Cache with sulci backend: {cache}")

# Via env var
import os
os.environ["SULCI_API_KEY"] = "sk-sulci-testkey1234567"
with patch("sulci.backends.cloud.SulciCloudBackend") as MockBackend:
    MockBackend.return_value = MockBackend
    cache = Cache(backend="sulci")
    print("Env var resolution ok")
del os.environ["SULCI_API_KEY"]
```

### Run only the cloud backend tests

```bash
python -m pytest tests/test_cloud_backend.py -v

# Run a specific class
python -m pytest tests/test_cloud_backend.py::TestConstruction -v
python -m pytest tests/test_cloud_backend.py::TestSearch -v
python -m pytest tests/test_cloud_backend.py::TestUpsert -v
python -m pytest tests/test_cloud_backend.py::TestDeleteAndClear -v
python -m pytest tests/test_cloud_backend.py::TestCacheWiring -v
```

---

## Step 11 — Test LangChain Integration Locally

`SulciCache(BaseCache)` is the LangChain cache adapter added in v0.3.3.

### Verify the import

```bash
python -c "from sulci.integrations.langchain import SulciCache; print('✅ Import OK')"
```

### Run the integration tests

```bash
python -m pytest tests/test_integrations_langchain.py -v
# Expected: 27 passed
```

### Run the LangChain smoke test

```bash
python smoke_test_langchain.py
# or: make smoke-langchain
```

---

## Step 12 — Test LlamaIndex Integration Locally

`SulciCacheLLM(LLM)` is the native LlamaIndex LLM wrapper added in v0.3.6.

### Verify the import

```bash
python -c "from sulci.integrations.llamaindex import SulciCacheLLM; print('✅ Import OK')"
```

### Run the integration tests

```bash
python -m pytest tests/test_integrations_llamaindex.py -v
# Expected: 29 passed
```

### Run the LlamaIndex smoke test

```bash
python smoke_test_llamaindex.py
# or: make smoke-llamaindex
```

---

## Step 13 — Test AsyncCache Locally

`AsyncCache` is the non-blocking async wrapper added in v0.3.7.

### Verify the import

```bash
python -c "from sulci import AsyncCache; print('✅ Import OK')"
```

### Run the integration tests

```bash
python -m pytest tests/test_async_cache.py -v
# Expected: 25 passed
```

### Run the AsyncCache smoke test

```bash
python smoke_test_async.py
# or: make smoke-async
```

---

## Troubleshooting

| Symptom                                   | Cause                      | Fix                                                                                                        |
| ----------------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `pytest: command not found`               | pytest not on `PATH`       | Use `python -m pytest`                                                                                     |
| `zsh: no matches found: .[sqlite]`        | zsh glob expansion         | Use quotes: `".[sqlite]"`                                                                                  |
| `ModuleNotFoundError: sulci`              | Not installed              | Run `pip install -e .` first                                                                               |
| `ModuleNotFoundError: chromadb`           | Backend extra missing      | `pip install -e ".[chroma]"`                                                                               |
| `ModuleNotFoundError: langchain_core`     | LangChain extra missing    | `pip install -e ".[langchain]"`                                                                            |
| `ModuleNotFoundError: llama_index`        | LlamaIndex extra missing   | `pip install -e ".[llamaindex]"`                                                                           |
| `ModuleNotFoundError: httpx`              | httpx not installed        | `pip install httpx` — needed for test_connect.py                                                           |
| `ValueError: not enough values to unpack` | v0.1 unpacking style       | `cache.get()` returns a **3-tuple** in v0.2+ — always unpack as `response, sim, ctx_depth = cache.get(...)` |
| MiniLM takes 2–3s on first call           | Model cold load            | Normal — subsequent embeds run at ~14ms. Warm the model at app startup, not per-request.                   |
| `git push` returns 403                    | Token auth expired         | `git remote set-url origin https://YOUR_USER:TOKEN@github.com/sulci-io/sulci-oss.git`                      |
| `_telemetry_enabled` is True unexpectedly | connect() called elsewhere | Check if `sulci.connect()` is being called in app code or test fixtures — telemetry is opt-in only         |

---

## API Key Notes

The core library and all tests run **without any API key**. The only things that
require a key:

| File                                                | Key needed                                                        |
| --------------------------------------------------- | ----------------------------------------------------------------- |
| `examples/anthropic_example.py`                     | `ANTHROPIC_API_KEY`                                               |
| `examples/langchain_example.py`                     | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (optional — mock fallback)|
| `examples/llamaindex_example.py`                    | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (optional — mock fallback)|
| `sulci/embeddings/openai.py`                        | `OPENAI_API_KEY`                                                  |
| `sulci.connect()` / `Cache(backend="sulci")`        | `SULCI_API_KEY` (Sulci Cloud — optional)                          |
| All other code                                      | None                                                              |

The default embedding model (`minilm`) runs fully locally via `sentence-transformers`.
No network calls are made unless you explicitly configure `embedding_model="openai"`
or use `backend="sulci"` with `sulci.connect()`.

> **`SULCI_API_KEY`** is the environment variable for the Sulci Cloud managed backend.
> Get a free key at [sulci.io/signup](https://sulci.io/signup). Setting this variable
> is optional — the library works fully offline without it.

---

## What a Clean Run Looks Like

```
$ python -m pytest tests/ -v

tests/test_backends.py::TestSQLiteBackend::test_contract PASSED
tests/test_backends.py::TestSQLiteBackend::test_persistence PASSED
tests/test_backends.py::TestChromaBackend::test_contract SKIPPED (chromadb not installed)
tests/test_backends.py::TestFAISSBackend::test_contract SKIPPED (faiss-cpu not installed)
tests/test_backends.py::TestQdrantBackend::test_contract SKIPPED (qdrant-client not installed)
tests/test_backends.py::TestRedisBackend::test_contract_local SKIPPED (redis not installed)
tests/test_backends.py::TestMilvusBackend::test_contract SKIPPED (pymilvus not installed)
tests/test_connect.py::TestDefaultState::test_telemetry_disabled_by_default PASSED
...
tests/test_connect.py::TestThreadSafety::test_concurrent_emits_do_not_lose_events PASSED
tests/test_context.py::TestContextWindow::test_empty_window_returns_query_vec PASSED
...
tests/test_context.py::TestCacheContextIntegration::test_clear_context_resets_depth PASSED
tests/test_core.py::TestBasicOperations::test_import PASSED
...
tests/test_core.py::TestPersonalization::test_user_scoped_miss_for_other_user PASSED
tests/test_integrations_langchain.py::TestContract::test_miss_on_empty_cache PASSED
...
tests/test_integrations_langchain.py::TestGlobalRegistration::test_set_and_get_llm_cache PASSED
tests/test_integrations_llamaindex.py::TestConstruction::test_wraps_llm PASSED
...
tests/test_integrations_llamaindex.py::TestStats::test_repr_contains_hit_rate PASSED

========== 205 passed, 7 skipped in ~380s ==========
```

> **Backend tests are skipped — not failed — when the dependency isn't installed.** This is expected.
> Install a backend extra (e.g. `pip install -e ".[chroma]"`) to run its tests.

---

## Project Structure (Reference)

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
│   ├── anthropic_example.py    ← Anthropic Claude + context-aware (ANTHROPIC_API_KEY)
│   ├── basic_usage.py          ← stateless cache demo, no API key needed
│   ├── context_aware.py        ← 4-demo walkthrough, fully offline
│   ├── context_aware_example.py← additional context-aware patterns
│   ├── langchain_example.py    ← LangChain demo, OpenAI/Anthropic/mock  (v0.3.5)
│   └── llamaindex_example.py   ← LlamaIndex demo, OpenAI/Anthropic/mock (v0.3.5)
├── pyproject.toml              ← name="sulci", version="0.5.0"
├── setup.py
├── setup.sh                    ← one-shot setup: venv + install + smoke tests
├── smoke_test.py               ← core smoke test
├── smoke_test_langchain.py     ← LangChain integration smoke test           (v0.3.3)
├── smoke_test_llamaindex.py    ← LlamaIndex integration smoke test          (v0.3.5)
├── sulci
│   ├── __init__.py             ← exports Cache, ContextWindow, SessionStore, connect()
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
│   ├── async_cache.py          ← AsyncCache non-blocking wrapper   (v0.3.7)
│   ├── context.py              ← ContextWindow + SessionStore
│   ├── core.py                 ← Cache engine (context-aware)
│   │                              telemetry= param, api_key= param
│   ├── embeddings
│   │   ├── __init__.py
│   │   ├── minilm.py           ← default: all-MiniLM-L6-v2 (free, local)
│   │   └── openai.py           ← requires OPENAI_API_KEY
│   └── integrations
│       ├── __init__.py
│       ├── langchain.py        ← SulciCache(BaseCache) for LangChain  (v0.3.3)
│       └── llamaindex.py       ← SulciCacheLLM(LLM) for LlamaIndex    (v0.3.6)
└── tests
    ├── test_backends.py                —  9 tests: per-backend contract + persistence
    ├── test_cloud_backend.py           — 28 tests: SulciCloudBackend + Cache wiring
    ├── test_connect.py                 — 32 tests: sulci.connect(), _emit(), _flush()
    ├── test_context.py                 — 35 tests: ContextWindow, SessionStore, integration
    ├── test_core.py                    — 27 tests: cache.get/set, TTL, stats, personalization
    ├── test_integrations_langchain.py  — 27 tests: SulciCache LangChain adapter        (v0.3.3)
    ├── test_integrations_llamaindex.py — 29 tests: SulciCacheLLM LlamaIndex wrapper     (v0.3.5)
    ├── test_async_cache.py             — 25 tests: AsyncCache non-blocking wrapper       (v0.3.7)
    ├── test_qdrant_tenant_isolation.py — 11 tests: tenant_id partition isolation         (v0.4.0)
    ├── test_sessions.py                — 24 tests: SessionStore protocol + tenant isol.  (v0.5.0)
    ├── test_sinks.py                   — 15 tests: EventSink protocol + privacy allowlist (v0.5.0)
    ├── test_session_store_injection.py — 12 tests: Cache(session_store=, event_sink=)    (v0.5.0)
    └── compat/                         —  Backend + Embedder conformance suites

Plus: sulci/tests/compat/ — SessionStore + EventSink conformance suites (v0.5.0)

Total: ~290 tests at v0.5.0 (varies with optional deps installed)
```

> **Redis-dependent tests:** the per-file runner exercises `RedisBackend`,
> `RedisSessionStore`, and `RedisStreamSink` against a real Redis daemon. Make sure
> one is running on `localhost:6379` before `make checkin`. Two ways:
>
> ```bash
> # Option A — Docker (no install needed)
> docker run -d --rm -p 6379:6379 --name sulci-test-redis redis:7-alpine
>
> # Option B — Homebrew (macOS)
> brew install redis && brew services start redis
> ```
>
> Without Redis up, the relevant tests skip gracefully via the fixture, so the
> suite still completes — but you lose coverage of the new v0.5.0 sessions/sinks
> Redis paths.

---

## Related Docs

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — branching model, PR process, coding standards
- [`CHANGELOG.md`](./CHANGELOG.md) — version history
- [`benchmark/README.md`](./benchmark/README.md) — benchmark methodology and results
- [PyPI: sulci](https://pypi.org/project/sulci/)
- [GitHub: sulci-io/sulci-oss](https://github.com/sulci-io/sulci-oss)

---

## Branch Reference

| Branch                            | Purpose                          | Status                      |
| --------------------------------- | -------------------------------- | --------------------------- |
| `main`                            | Stable release — v0.5.0          | All work merges here via PR |
| `feature/context-aware`           | v0.2.0 context-aware library     | Merged                      |
| `feature/benchmark-context-aware` | v0.2.5 benchmark suite           | Merged                      |
| `feature/saas-onramp`             | v0.3.0 cloud backend + telemetry | Merged                      |
| `feat/langchain-integration`      | v0.3.3 LangChain integration     | Merged                      |
| `feat/llamaindex-integration`     | v0.3.5 LlamaIndex + examples     | Merged                      |
| `feat/async-cache`                | v0.3.7 AsyncCache wrapper        | Merged                      |
