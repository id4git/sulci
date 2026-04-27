# Contributing to Sulci

Thank you for your interest in contributing!

## Development setup

```bash
git clone https://github.com/sulci-io/sulci-oss.git
cd sulci-oss
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

Sulci's `Backend` protocol (`sulci/backends/protocol.py`) defines the
contract every backend must satisfy.

1. **Create `sulci/backends/yourbackend.py`** implementing the protocol:
   `store()`, `search()`, `clear()`. Use the keyword-only convention
   (`*,` separator) for `tenant_id`, `user_id`, and other partition
   kwargs — see existing backends for the pattern.

2. **Declare `ENFORCES_TENANT_ISOLATION`** as a class attribute. `True`
   if `search()` actually filters out other tenants (Qdrant pattern);
   `False` if `tenant_id` is stored as a label only.

3. **Register in `sulci/core.py` `_load_backend()`** so users can
   construct `Cache(backend="yourbackend")`.

4. **Add an extra in `pyproject.toml` `[project.optional-dependencies]`**
   so users install via `pip install "sulci[yourbackend]"`.

5. **Register the class in `tests/compat/conftest.py` `BACKEND_CLASSES`**.
   The conformance suite (`tests/compat/`) automatically runs structural,
   round-trip, and tenant-isolation tests against every entry.

6. **Optionally add backend-specific tests** in `tests/test_backends.py`
   using `_run_backend_contract()` for edge cases the protocol contract
   doesn't cover.

Worked example: `examples/extending_sulci/custom_backend.py` is a
~150-line in-memory `InMemoryBackend` that satisfies the full protocol.

## Pre-publish review

Before publishing anything to a public repo (issue body, issue comment,
PR description, commit message, or release notes), do a quick scan for
content that shouldn't appear in public.

**Don't publish in public repos:**

- Tier names (Free, Pro, Business, Enterprise) unless the tiers are
  already publicly announced on sulci.io
- Monetization mechanics (which features are paid, what's gated, pricing)
- Concrete feature candidates being evaluated for paid tiers (e.g.,
  "we'd gate X behind Y") — even hypothetically
- Internal cross-references like "FU-14" or "internal Notion doc" —
  if a reader can't act on a reference, leaving it visible just signals
  that internal planning exists at a specific pointer
- Competitor names alongside strategy commentary — factual mentions
  are fine, comparative monetization claims aren't
- Customer or contract specifics (logos, MRR, deal mechanics)

**Always fine in public:**

- Technical rationale (why a flag is keyword-only, why a backend
  enforces isolation, what a protocol guarantees)
- API design tradeoffs and alternatives considered
- Test outcomes, benchmark numbers, performance trade-offs
- Public follow-up issue numbers (FU-N where N maps to a GitHub issue
  in the same public repo)
- Honest acknowledgments of limitations or known issues

**Suggested workflow before any commit on a public repo:**

1. Read the message you're about to commit, not just the title.
2. Search for words like `tier`, `Pro`, `Enterprise`, `monetize`,
   `gate`, `paywall`, `internal`, `FU-` (if FU-N is internal-only).
3. If anything matches, ask: would the same point work without that
   word? Usually yes — rewrite to keep the technical content and drop
   the strategic framing.
4. If you can't avoid the word, the content probably belongs in
   internal planning docs instead of a public commit.

The same rule applies to issue bodies and comments. Issues on public
repos are even more searchable than commit history.

If you discover an existing public artifact already contains something
that shouldn't have been published, the standard response is: edit the
body in-place if possible, file a follow-up note to track the cleanup,
and improve process going forward. Force-pushing to rewrite published
commit history is generally not worth the operational disruption for
moderate leaks — the content is already distributed via clones and
reflog regardless.

## Releasing

The release workflow ships v0.X.Y to PyPI and creates a GitHub Release
when an annotated `vX.Y.Z` tag is pushed.

```bash
# 1. Bump version in pyproject.toml (single source of truth as of v0.4.0).
#    sulci.__version__ derives from this via importlib.metadata.

# 2. Refresh editable-install metadata so importlib.metadata.version()
#    sees the new version locally. Without this, your dev environment
#    keeps reporting the previous version even though pyproject.toml
#    was bumped.
pip install -e . --no-deps

# 3. Add a [X.Y.Z] entry to CHANGELOG.md following the Keep a Changelog
#    format (sections: Added, Changed, Fixed, Deprecated, Removed,
#    Security, Notes).

# 4. Run the full pre-PR check before tagging.
make checkin

# 5. Open a PR. After review and CI green, merge to main using a merge
#    commit (NOT squash) so individual sub-phase commits are preserved
#    in the main branch history.

# 6. After merge, tag main and push.
git checkout main
git pull
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z

# 7. The publish.yml workflow triggers on the tag push and publishes
#    to PyPI automatically (requires PYPI_TOKEN secret).

# 8. After publish completes, create a GitHub Release linked to the tag
#    using the matching CHANGELOG entry as the release notes:
awk '/^## \[X\.Y\.Z\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md > /tmp/release_notes.md
gh release create vX.Y.Z \
    --title "vX.Y.Z: <one-line summary>" \
    --notes-file /tmp/release_notes.md \
    --verify-tag

# 9. Verify install from PyPI in a fresh venv.
python3 -m venv /tmp/verify-vX.Y.Z
source /tmp/verify-vX.Y.Z/bin/activate
pip install --upgrade "sulci[sqlite]"
python -c "import sulci; print(sulci.__version__)"
```

For longer commit messages or release notes, write them to a file and
use `git commit -F` or `gh release create --notes-file` to avoid shell
quoting issues.

## Code style

- Black formatting: `pip install black && black sulci/`
- Type hints encouraged but not required
- Docstrings on all public classes and methods
