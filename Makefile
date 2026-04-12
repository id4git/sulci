# sulci-oss Makefile
# ─────────────────────────────────────────────────────────────────────────────

PYTHON = python3

# ── Smoke tests ───────────────────────────────────────────────────────────────

## Run all smoke tests (core + LangChain + LlamaIndex + AsyncCache)
smoke:
	@echo "── Core smoke test ─────────────────────────────────────────────────"
	$(PYTHON) smoke_test.py
	@echo ""
	@echo "── LangChain integration smoke test ────────────────────────────────"
	$(PYTHON) smoke_test_langchain.py
	@echo ""
	@echo "── LlamaIndex integration smoke test ───────────────────────────────"
	$(PYTHON) smoke_test_llamaindex.py
	@echo ""
	@echo "── AsyncCache smoke test ───────────────────────────────────────────"
	$(PYTHON) smoke_test_async.py

## Run core smoke test only (no LangChain required)
smoke-core:
	$(PYTHON) smoke_test.py

## Run LangChain integration smoke test only
## Requires: pip install "sulci[sqlite,langchain]"
smoke-langchain:
	$(PYTHON) smoke_test_langchain.py

## Run LlamaIndex integration smoke test only
## Requires: pip install "sulci[sqlite,llamaindex]"
smoke-llamaindex:
	$(PYTHON) smoke_test_llamaindex.py

## Run AsyncCache smoke test only
## Requires: pip install "sulci[sqlite]"
smoke-async:
	$(PYTHON) smoke_test_async.py

# ── Tests ─────────────────────────────────────────────────────────────────────

## Run core test suite (test_core, test_context, test_backends, test_connect, test_cloud_backend)
test:
	python -m pytest tests/test_core.py \
	                 tests/test_context.py \
	                 tests/test_backends.py \
	                 tests/test_connect.py \
	                 tests/test_cloud_backend.py \
	                 -v --tb=short

## Run AsyncCache tests only
test-async:
	python -m pytest tests/test_async_cache.py -v --tb=short

## Run integration tests (LangChain + LlamaIndex)
test-integrations:
	python -m pytest tests/test_integrations_langchain.py \
	                 tests/test_integrations_llamaindex.py \
	                 -v --tb=short

## Run all tests (core + async + all integrations)
test-all:
	python -m pytest tests/ -v --tb=short

## Run all tests with coverage report
test-cov:
	python -m pytest tests/ -v --cov=sulci --cov-report=term-missing

# ── Combined: smoke + tests ───────────────────────────────────────────────────

## Full local verification: smoke tests + full test suite
verify: smoke test-all

.PHONY: smoke smoke-core smoke-langchain smoke-llamaindex smoke-async \
        test test-async test-integrations test-all test-cov \
        verify
