#!/usr/bin/env python3
"""
scripts/_update_contributing_v2.py
====================================
Add a Retroactive cleanup subsection to CONTRIBUTING.md Pre-publish review.
Idempotent: refuses to re-apply if the new subsection is already present.
"""
from pathlib import Path
import sys

CONTRIBUTING = Path("CONTRIBUTING.md")
NEW_SUBSECTION_HEADER = "### Retroactive cleanup"
ANCHOR = "## Releasing"

# Build content from a list of lines to avoid any multi-line string parsing.
# Backticks are inserted via chr(96) where they appear inside what would
# otherwise be a markdown code fence.

TICK = chr(96)
TICK3 = TICK * 3

LINES = [
    "### Retroactive cleanup",
    "",
    "If you discover that something already published to a public surface",
    "needs to be removed or sanitized, the fix is rarely a single place:",
    "",
    "1. Sanitize the original artifact first (issue body, comment, commit",
    "   message, or release notes - whatever the source is).",
    "2. Run a repo-wide search for the same terms. Content has shadow copies",
    "   in helper scripts, tooling files, drafts that got committed with the",
    "   rest of a change, comments referencing the original, or generated",
    "   files. A short grep catches most of them:",
    "",
    TICK3,
    "git grep -nE \"<term1>|<term2>|<term3>\" -- ':!CONTRIBUTING.md'",
    TICK3,
    "",
    "   Exclude " + TICK + "CONTRIBUTING.md" + TICK + " because the terms-to-avoid list legitimately",
    "   contains the words.",
    "3. Sanitize each shadow copy and commit the cleanup as a focused",
    "   " + TICK + "chore:" + TICK + " change. The commit message should explain why the specific",
    "   edits exist; future contributors who find them via " + TICK + "git log" + TICK + " should",
    "   understand the reasoning.",
    "4. Accept that the original (un-sanitized) content remains in git history",
    "   at the commits where it landed. Force-pushing to rewrite published",
    "   history is generally not worth the operational disruption for moderate",
    "   leaks - see the note in the parent section.",
    "",
    "The \"sanitize once, grep the rest, accept history\" pattern lets you fix",
    "forward cleanly without tripping over force-push fallout.",
    "",
    "",
]

NEW_CONTENT = "\n".join(LINES)


def main() -> int:
    if not CONTRIBUTING.exists():
        print("ERROR: CONTRIBUTING.md not found", file=sys.stderr)
        return 1

    src = CONTRIBUTING.read_text()

    if NEW_SUBSECTION_HEADER in src:
        print("SKIP: '{}' already present".format(NEW_SUBSECTION_HEADER))
        return 0

    n = src.count(ANCHOR)
    if n != 1:
        print("ERROR: anchor '{}' matched {} times (expected 1)".format(ANCHOR, n),
              file=sys.stderr)
        return 2

    new_src = src.replace(ANCHOR, NEW_CONTENT + ANCHOR, 1)
    CONTRIBUTING.write_text(new_src)
    print("UPDATED: CONTRIBUTING.md - added 'Retroactive cleanup' subsection "
          "before '{}'".format(ANCHOR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
