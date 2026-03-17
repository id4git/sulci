# Sulci — Local Setup Guide

Everything you need to clone the repo, install dependencies, run tests, and verify a working local environment from scratch.

---

## Requirements

- Python **3.9, 3.11, or 3.12** (all three are tested in CI)
- `git`
- A terminal with `pip` available

---

## Step 1 — Clone the Repository

```bash
git clone https://github.com/sulci-io/sulci-oss.git
cd sulci-oss
```

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
python --version    # should be 3.9, 3.11, or 3.12
```

---

## Step 3 — Install the Library

Install in editable mode (`-e`) so any changes you make to `sulci/` source code are reflected immediately without reinstalling.

```bash
# base install — editable
pip install -e .

# with the SQLite backend (zero infra, fully offline — recommended for local dev)
pip install -e ".[sqlite]"

# with ChromaDB
pip install -e ".[chroma]"

# with FAISS
pip install -e ".[faiss]"

# multiple backends at once
pip install -e ".[sqlite,chroma,faiss]"
```

> **zsh users:** always wrap extras in quotes — `".[sqlite]"` not `.[sqlite]`.
> Without quotes, zsh treats the brackets as a glob pattern and throws `no matches found`.

Then install pytest for running the test suite:

```bash
pip install pytest pytest-cov
```

---

## Step 4 — Verify the Install

```bash
python -c "from sulci import Cache, ContextWindow, SessionStore; print('Import OK')"
```

Expected output:

```
Import OK
```

If you see a `ModuleNotFoundError` on a backend (e.g. `chromadb`, `faiss`), that backend's
extra is not installed. Install it with `pip install -e ".[backend_name]"`.

---

## Step 5 — Run the Tests

Always use `python -m pytest` rather than bare `pytest` to avoid PATH issues.

```bash
python -m pytest tests/ -v
```

All **53 tests** should pass across three test files:

```
tests/test_core.py      — 26 tests  (cache.get/set, thresholds, TTL, stats)
tests/test_context.py   — 27 tests  (ContextWindow, SessionStore, integration)
tests/test_backends.py  —  n tests  (per-backend smoke tests)
```

### Targeted test runs

```bash
# core cache logic only
python -m pytest tests/test_core.py -v

# context and session tests only
python -m pytest tests/test_context.py -v

# backend tests only
python -m pytest tests/test_backends.py -v

# one specific test by name
python -m pytest tests/test_core.py::test_cache_hit -v

# stop at first failure
python -m pytest tests/ -v -x

# with line-level coverage report
python -m pytest tests/ -v --cov=sulci --cov-report=term-missing
```

---

## Step 6 — Run the Examples

### No API key required

```bash
# stateless cache demo
python examples/basic_usage.py

# context-aware demo — 4 walkthroughs, fully offline
python examples/context_aware.py
```

### Requires `ANTHROPIC_API_KEY`

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python examples/anthropic_example.py
```

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

| Flag | Default | Description |
|---|---|---|
| `--context` | off | Enable context-aware benchmark pass |
| `--no-sweep` | off | Skip threshold sweep (much faster) |
| `--queries N` | 5000 | Number of test queries |
| `--threshold F` | 0.85 | Similarity threshold for stateless pass |
| `--context-threshold F` | 0.58 | Similarity threshold for context pass |
| `--context-window N` | 4 | Turns per session window |
| `--use-sulci` | off | Use real MiniLM embeddings (vs TF-IDF simulation) |
| `--out DIR` | `benchmark/results` | Output directory for result files |

---

## Step 8 — Smoke Test (Quick End-to-End Sanity Check)

Create a file `smoke_test.py` at the repo root and run it to confirm the full
stack is working — import, set, get, semantic hit, context mode, and stats:

```python
# smoke_test.py
from sulci import Cache

# --- stateless mode, SQLite backend, no infrastructure needed ---
cache = Cache(backend="sqlite", threshold=0.85)

# store an entry
cache.set("How do I deploy to AWS?", "Use the AWS CLI with 'aws deploy'...")

# exact match hit
response, sim, ctx_depth = cache.get("How do I deploy to AWS?")
assert response is not None, "FAIL: exact hit returned None"
print(f"Exact hit:    sim={sim:.3f}  ctx={ctx_depth}  ✅")

# semantic match hit
response, sim, ctx_depth = cache.get("What is the process for deploying on AWS?")
if response:
    print(f"Semantic hit: sim={sim:.3f}  ctx={ctx_depth}  ✅")
else:
    print(f"Semantic miss (sim={sim:.3f}) — try lowering threshold")

# stats
s = cache.stats()
print(f"Stats:        hits={s['hits']}  misses={s['misses']}  hit_rate={s['hit_rate']:.1%}")

# --- context-aware mode ---
cache_ctx = Cache(backend="sqlite", threshold=0.85, context_window=4)
cache_ctx.set(
    "What is Python?",
    "Python is a high-level programming language.",
    session_id="s1"
)
response, sim, ctx_depth = cache_ctx.get("Tell me about Python", session_id="s1")
print(f"Context mode: sim={sim:.3f}  ctx_depth={ctx_depth}  ✅")

print("\nAll smoke tests passed.")
```

```bash
python smoke_test.py
```

All four lines should print `✅` and the final line `All smoke tests passed.`

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `pytest: command not found` | pytest not on `PATH` | Use `python -m pytest` |
| `zsh: no matches found: .[sqlite]` | zsh glob expansion | Use quotes: `".[sqlite]"` |
| `ModuleNotFoundError: sulci` | Not installed | Run `pip install -e .` first |
| `ModuleNotFoundError: chromadb` | Backend extra missing | `pip install -e ".[chroma]"` |
| `ValueError: not enough values to unpack` | v0.1 unpacking style | `cache.get()` returns a **3-tuple** in v0.2 — always unpack as `response, sim, ctx_depth = cache.get(...)` |
| MiniLM takes 2–3s on first call | Model cold load | Normal — subsequent embeds run at ~14ms. Warm the model at app startup, not per-request. |
| `git push` returns 403 | Token auth expired | `git remote set-url origin https://YOUR_USER:TOKEN@github.com/sulci-io/sulci-oss.git` |

---

## API Key Notes

The core library and all tests run **without any API key**. The only things that
require a key:

| File | Key needed |
|---|---|
| `examples/anthropic_example.py` | `ANTHROPIC_API_KEY` |
| `sulci/embeddings/openai.py` | `OPENAI_API_KEY` |
| All other code | None |

The default embedding model (`minilm`) runs fully locally via `sentence-transformers`.
No network calls are made unless you explicitly configure `embedding_model="openai"`.

---

## What a Clean Run Looks Like

```
$ python -m pytest tests/ -v

tests/test_core.py::test_cache_miss PASSED
tests/test_core.py::test_cache_hit PASSED
tests/test_core.py::test_semantic_hit PASSED
tests/test_core.py::test_threshold_boundary PASSED
tests/test_core.py::test_ttl_expiry PASSED
...
tests/test_context.py::test_context_window_basic PASSED
tests/test_context.py::test_session_store PASSED
tests/test_context.py::test_context_blending PASSED
tests/test_context.py::test_session_ttl PASSED
...
tests/test_backends.py::test_sqlite_backend PASSED
...

========== 53 passed in 12.4s ==========
```

---

## Project Structure (Reference)

```
sulci/
├── sulci/
│   ├── __init__.py             ← exports Cache, ContextWindow, SessionStore
│   ├── core.py                 ← Cache engine (context-aware)
│   ├── context.py              ← ContextWindow + SessionStore
│   ├── backends/               ← chroma, qdrant, faiss, redis, sqlite, milvus
│   └── embeddings/             ← minilm, openai
├── tests/
│   ├── test_core.py            ← 26 tests
│   ├── test_context.py         ← 27 tests
│   └── test_backends.py
├── examples/
│   ├── basic_usage.py
│   ├── context_aware.py        ← runs offline, no API key needed
│   └── anthropic_example.py    ← requires ANTHROPIC_API_KEY
├── benchmark/
│   ├── run.py
│   ├── README.md
│   └── results/                ← gitignored output directory
├── pyproject.toml              ← name="sulci-cache", version="0.2.2"
├── CHANGELOG.md
├── CONTRIBUTING.md
└── README.md
```

---

## Related Docs

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — branching model, PR process, coding standards
- [`CHANGELOG.md`](./CHANGELOG.md) — version history
- [`benchmark/README.md`](./benchmark/README.md) — benchmark methodology and results
- [PyPI: sulci-cache](https://pypi.org/project/sulci-cache/)
- [GitHub: sulci-io/sulci-oss](https://github.com/sulci-io/sulci-oss)
