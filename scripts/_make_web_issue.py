#!/usr/bin/env python3
"""
scripts/_make_web_issue.py
===========================
Generate per-issue files for the sulci-web Quickstart.jsx alignment
follow-up (FU-5 from v0.4.0 release work).
"""
from pathlib import Path

PREFIX = "sulci_web_issue"
TARGET_REPO = "sulci-io/sulci-web"

ISSUES = [
    {
        "title": "docs: align Quickstart.jsx install command with v0.4.0 OSS ([chroma] -> [sqlite])",
        "labels": ["documentation"],
        "body": """\
## Problem

The sulci-oss v0.4.0 release (shipped 2026-04-27) changed the recommended
install command for the Anthropic example from:

    pip install "sulci[chroma]" anthropic

to:

    pip install "sulci[sqlite]" anthropic

Background: previously the Anthropic example hardcoded `backend="chroma"`,
but anyone following the README's recommended `pip install "sulci[sqlite]"`
quickstart hit ImportError on first run. v0.4.0 fixed this by switching
the example to `backend="sqlite"` (functionally equivalent for the demo)
and updating both the example's docstring and the README install
instructions.

## Where this is stale on the website

`sulci-web/src/components/docs/sections/Quickstart.jsx` line 13 still
references `pip install "sulci[chroma]" anthropic`. This is now
inconsistent with:

- The OSS README at https://github.com/sulci-io/sulci-oss
- The OSS example at examples/anthropic_example.py
- The other component on the same site:
  `sulci-web/src/components/tabs/SulciTab.jsx` line 414, which already
  says `pip install "sulci[sqlite]" anthropic`

So the website is currently inconsistent with itself plus the published
OSS package.

## Fix

In `sulci-web/src/components/docs/sections/Quickstart.jsx`:

    - <CodeBlock>{`pip install "sulci[chroma]" anthropic`}</CodeBlock>
    + <CodeBlock>{`pip install "sulci[sqlite]" anthropic`}</CodeBlock>

One-line change. Verify the rendered Quickstart docs page on the dev
build before merging.

## Cross-reference

Tracked as FU-5 from the sulci-oss v0.4.0 release work
(https://github.com/sulci-io/sulci-oss/releases/tag/v0.4.0). The
matching OSS-side fix landed in commit fe770c8 (phase 1.6.5a).

## Priority

Medium. Not release-blocking, but worth fixing soon — anyone visiting
the site between now and a fix sees a contradiction with the published
OSS package on PyPI.
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
            f'--repo {TARGET_REPO} '
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
