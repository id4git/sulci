#!/usr/bin/env python3
"""
scripts/_make_more_issues.py
=============================
Generate per-issue files for 3 sulci-oss follow-ups discovered after the
v0.4.0 release shipped to PyPI. Same shape as scripts/_make_issues.py.
"""
from pathlib import Path

# Each issue starts at slot 8 (the original 7 used slots 1-7 in /tmp/sulci_oss_issue_*)
# Rename the per-issue file slots so they don't collide with /tmp/sulci_oss_issue_*
# from the earlier script. Use a different prefix.

PREFIX = "sulci_oss_issue_post_release"

ISSUES = [
    {
        "title": "deps: sentence-transformers renamed get_sentence_embedding_dimension upstream",
        "labels": ["bug", "low-priority"],
        "body": """\
## Problem

When loading the MiniLM embedder on a fresh PyPI install of v0.4.0, the
following FutureWarning is emitted:

    /sulci/embeddings/minilm.py:36: FutureWarning: The
    `get_sentence_embedding_dimension` method has been renamed to
    `get_embedding_dimension`.
      self._dim = self._model.get_sentence_embedding_dimension()

This is from a newer sentence-transformers version that renamed the
method. Our code still uses the old name. The warning is non-fatal
today (still works), but a future major sentence-transformers release
could remove the old name and break us.

## Proposed fix

In `sulci/embeddings/minilm.py`, swap to the new method name with a
fallback for older sentence-transformers versions:

    try:
        self._dim = self._model.get_embedding_dimension()
    except AttributeError:
        # Older sentence-transformers (pre-rename) — keep working
        self._dim = self._model.get_sentence_embedding_dimension()

This silences the FutureWarning on new installs while staying
compatible with older sentence-transformers releases.

## Effort

~5 lines in one file. Could be a one-commit PR.

## Context

Surfaced during v0.4.0 PyPI install verification.
""",
    },
    {
        "title": "packaging: add [project.urls] and authors block to pyproject.toml",
        "labels": ["documentation", "low-priority"],
        "body": """\
## Problem

Running `pip show sulci` after installing v0.4.0 shows empty fields for
Home-page and Author:

    Name: sulci
    Version: 0.4.0
    Summary: ...
    Home-page:
    Author:

The PyPI listing page also lacks rich project metadata (no Homepage or
Repository links surfaced in the sidebar — only because the README
inlines them as Markdown, which renders fine but isn't picked up by
`pip show` or programmatic introspection).

## Proposed fix

Add a `[project.urls]` table and `authors` field to `pyproject.toml`:

    [project]
    name = "sulci"
    authors = [
        { name = "Kathiravan Sengodan" },
    ]
    ...

    [project.urls]
    Homepage      = "https://sulci.io"
    Repository    = "https://github.com/sulci-io/sulci-oss"
    Documentation = "https://sulci.io/docs"
    Changelog     = "https://github.com/sulci-io/sulci-oss/blob/main/CHANGELOG.md"
    Issues        = "https://github.com/sulci-io/sulci-oss/issues"

After the next release with this metadata, `pip show` shows the
Homepage and Author, and PyPI's project page sidebar shows the URL
links. Better discoverability for users finding the package.

## Effort

~10 lines added to pyproject.toml. Lands in next minor release (v0.4.1
or v0.5.0).

## Context

Surfaced during v0.4.0 PyPI install verification.
""",
    },
    {
        "title": "docs: README badge `pypi v0.3.7` is stale (shields.io cache)",
        "labels": ["documentation", "low-priority"],
        "body": """\
## Problem

The PyPI project page (https://pypi.org/project/sulci/) renders the
README at the time of the v0.4.0 release and shows a stale shields.io
PyPI badge reading `pypi v0.3.7`. The actual published package is
v0.4.0; only the badge image is stale.

This is a shields.io CDN caching artifact, not a real issue with the
package. shields.io typically refreshes within 24 hours.

## Proposed fix (only if it doesn't auto-resolve)

If the badge is still stale 24-48 hours after release:

1. Force a cache purge by appending a cache-buster to the badge URL,
   e.g., `?cacheSeconds=300` or `?_=v040`
2. Or, verify the underlying badge URL by visiting
   `https://img.shields.io/pypi/v/sulci` directly — it should show
   the current version

## Status

Wait-and-see. Most likely resolves itself by 2026-04-28 without
intervention.

## Context

Surfaced during v0.4.0 PyPI install verification (badge visible in
PyPI screenshot).
""",
    },
]


def write_per_issue():
    for i, issue in enumerate(ISSUES, 1):
        body_path = Path(f"/tmp/{PREFIX}_{i}_body.md")
        body_path.write_text(issue["body"])
        title_path = Path(f"/tmp/{PREFIX}_{i}_title.txt")
        title_path.write_text(issue["title"])
        labels_path = Path(f"/tmp/{PREFIX}_{i}_labels.txt")
        labels_path.write_text(",".join(issue["labels"]))
    print(f"wrote {len(ISSUES)} per-issue files to /tmp/{PREFIX}_*")


def emit_gh_script():
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    for i in range(1, len(ISSUES) + 1):
        lines.append(
            f'gh issue create '
            f'--title "$(cat /tmp/{PREFIX}_{i}_title.txt)" '
            f'--body-file /tmp/{PREFIX}_{i}_body.md '
            f'--label "$(cat /tmp/{PREFIX}_{i}_labels.txt)"'
        )
    out = Path(f"/tmp/create_{PREFIX}_issues.sh")
    out.write_text("\n".join(lines) + "\n")
    out.chmod(0o755)
    print(f"wrote {out}")


if __name__ == "__main__":
    write_per_issue()
    emit_gh_script()
