# Contributing to Sulci

Thank you for your interest in contributing!

## Development setup

```bash
git clone https://github.com/id4git/semanticache.git
cd semanticache/lib
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[sqlite,dev]"
```

## Running tests

```bash
# Core tests (no extra dependencies)
pytest tests/test_core.py -v

# All tests (skips backends whose deps aren't installed)
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=sulci --cov-report=term-missing
```

## Adding a new backend

1. Create `sulci/backends/yourbackend.py`
2. Implement `store()` and `search()` — follow the contract in any existing backend
3. Register it in `sulci/core.py` `_load_backend()` registry dict
4. Add an extra in `pyproject.toml` `[project.optional-dependencies]`
5. Add tests in `tests/test_backends.py` using `_run_backend_contract()`

## Releasing

```bash
# 1. Bump version in pyproject.toml and CHANGELOG.md
# 2. Commit and tag
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version to 0.x.x"
git tag v0.x.x
git push origin main --tags
# GitHub Actions publishes to PyPI automatically
```

## Code style

- Black formatting: `pip install black && black sulci/`
- Type hints encouraged but not required
- Docstrings on all public classes and methods
