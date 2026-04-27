#!/usr/bin/env python3
"""
scripts/_make_web_step_d_issues.py
====================================
Generate per-issue files for 3 sulci-web follow-ups from v0.4.0 release work:
  FU-2:        sulci.io/enterprise marketing page
  FU-3:        sulci.io/security trust portal
  FU-16-web:   marketing differentiation messaging

All target sulci-cache/sulci-web (under sulci-cache user, not sulci-io org,
because Vercel free-tier auto-deploy doesn't work for org-owned private repos).
"""
from pathlib import Path

PREFIX = "sulci_web_d"
TARGET_REPO = "sulci-cache/sulci-web"

ISSUES = [
    {
        "title": "feat: sulci.io/enterprise marketing page",
        "labels": ["enhancement"],
        "body": """\
## Goal

Create a public-facing marketing page at sulci.io/enterprise that
describes Sulci's enterprise tier offering. Audience: sales prospects,
security buyers, and RFP reviewers. The page should live separately
from the technical docs and feel like a sales asset, not a manual.

## Content (initial draft scope)

### Hero section
- Headline: "Sulci for Enterprise" or similar
- Subheading positioning Sulci as production-grade semantic caching
  with first-class multi-tenant isolation, hosted or self-managed

### Deployment matrix
A table showing the three deployment options:

| Tier         | Sharing      | Deployment      | Logical isolation | Physical isolation        |
|--------------|--------------|-----------------|-------------------|---------------------------|
| Free / Pro   | Multi-tenant | Managed Cloud   | tenant_id filter  | None — shared cluster     |
| Business     | Multi-tenant | Managed Cloud   | tenant_id filter  | None — shared cluster     |
| Enterprise   | Single-tenant| VPC             | tenant_id filter  | Dedicated cluster         |
| Enterprise   | Single-tenant| Air-gapped      | tenant_id filter  | Customer hardware         |

### "What you get at each tier" feature comparison
Compare what's in OSS vs Pro vs Business vs Enterprise. Avoid claiming
features that aren't yet shipped — be honest about the platform's
current state.

### Trust signals
- Customer logos / testimonials when available
- Compliance roadmap (SOC 2 target date, HIPAA BAA availability)
- Pen test summary when available
- Linked from sulci.io/security (FU-3)

### Call-to-action
Single primary CTA: "Talk to sales for Enterprise" linking to a
contact form, calendar booking, or sales@sulci.io email.

## Implementation

Create `sulci-web/src/pages/EnterprisePage.jsx` (or equivalent in the
existing routing structure). Add navigation entry in the main nav.

## Constraints — what NOT to put on this page

These belong in OSS docs or the GitHub repo, not the marketing page:

- Backend protocol implementation details
- tenant_id kwarg semantics
- Conformance test suite mechanics

The marketing page is for the why and what, not the how.

## Cross-reference

Tracked as FU-2 from sulci-oss v0.4.0 release work
(https://github.com/sulci-io/sulci-oss/releases/tag/v0.4.0). Companion
to the OSS-side multi-tenancy doc at
https://github.com/sulci-io/sulci-oss/blob/main/docs/multi_tenancy_and_isolation.md
(which deliberately omits pricing/tier content because that lives here).

## Effort

~1-2 days of design + content + JSX implementation. Most of the work
is wordsmithing and table construction; the React components themselves
are straightforward given the existing site styles.
""",
    },
    {
        "title": "feat: sulci.io/security trust portal",
        "labels": ["enhancement", "documentation"],
        "body": """\
## Goal

Create a public security/trust portal at sulci.io/security covering
compliance status, vulnerability disclosure process, security
architecture, and customer-facing security artifacts.

Audience: customer auditors, security buyers, compliance reviewers,
researchers reporting vulnerabilities.

## Content

### Compliance status
- Current attestations (none yet, target dates if any)
- SOC 2 Type II target date
- HIPAA BAA availability
- ISO 27001 status (likely "not pursuing yet" honestly stated)

### Vulnerability disclosure
- Email: security@sulci.io
- PGP key for sensitive reports
- Response SLA (e.g., acknowledge within 48 hours, triage within 5 days)
- Coordinated disclosure policy

### Security architecture
- Brief overview of how data flows in the managed cloud
- tenant_id isolation guarantees (link to OSS docs/multi_tenancy_and_isolation.md)
- Encryption at rest / in transit
- Subprocessor list (cloud providers, observability vendors, etc.)

### Data handling policy
- Where data lives (regions)
- Retention policy
- Deletion workflow
- GDPR / CCPA right-to-erasure procedures

### Customer audit support
- "Request our SOC 2 report under NDA" form (when available)
- Response time for security questionnaires
- Available compliance documentation

## Implementation notes

Most content blocks on the actual SOC 2 audit cycle, so the page can be
drafted now but populated as compliance milestones land. Initial version
should at minimum have:

- Vulnerability disclosure (security@sulci.io contact)
- Subprocessor list
- High-level architecture overview

The compliance status section can be honest about being pre-attestation.
"In progress, target Q3 2026" is more credible than empty cells.

## Implementation route

Two options:
1. Create `sulci-web/src/pages/SecurityPage.jsx` in the existing site
2. Use a dedicated trust portal subdomain (trust.sulci.io) — common
   pattern for SaaS, lets the portal evolve independently of marketing

Option 1 is faster; option 2 scales better.

## Cross-reference

Tracked as FU-3 from sulci-oss v0.4.0 release work
(https://github.com/sulci-io/sulci-oss/releases/tag/v0.4.0). Will be
linked from the FU-2 enterprise marketing page.

## Effort

Initial version: ~half a day of content + JSX. Ongoing maintenance as
compliance milestones land.
""",
    },
    {
        "title": "feat: marketing differentiation messaging — three OSS-free differentiators",
        "labels": ["enhancement", "documentation"],
        "body": """\
## Goal

Update sulci.io marketing content to lead with three differentiators
that are real today AND free in OSS — turning OSS into a genuine
"developer marketing" funnel rather than a stripped-down free tier.

## Background

During v0.4.0 planning, we observed that the major caching-layer
competitors (GPTCache, LangCache, Helicone, Portkey, LangSmith) all
keep tenant isolation features in OSS or free tier and monetize on
operational axes (hosting, observability volume, compliance, support
SLAs, team seats). None paywall logical isolation.

This means Sulci has actual technical differentiation in OSS itself —
if we keep it ungated AND market it clearly. v0.4.0 keeps it ungated;
this issue is about the marketing side.

## Three differentiators to lead with

1. **Context-aware blending (+20.8pp resolution accuracy on a
   built-in benchmark vs stateless competitors).** None of the
   competitors above do context-aware caching; they're all stateless.
   This is genuinely unique. Source: benchmark/README.md.

2. **Formally-verified multi-tenant isolation in the protocol contract.**
   Backend protocol declares tenant_id as a hard boundary; the
   conformance test suite (tests/compat/) plus
   tests/test_qdrant_tenant_isolation.py verify it end-to-end. No
   competitor offers this depth of testing infrastructure for tenant
   isolation in OSS.

3. **Seven-backend abstraction with conformance-tested protocol.**
   Customers pick the vector DB they already run; sulci adapts. Most
   competitors lock you to one (GPTCache/Milvus, LangCache/Redis,
   etc.).

## Where this content goes

Specific updates needed across:

- **Hero / landing copy** on sulci.io home — currently focuses on
  "your LLM already answered that"; should add a tagline or sub-line
  that highlights one of the three differentiators
- **"Why Sulci" section / comparison table** — likely an existing
  component on the home or about page; should reference the three
  differentiators with concrete numbers
- **Architecture / Sulci docs tabs** — already quote the +20.8pp
  number; should add a small "Note on engine" footnote (see also
  related FU-11 in sulci-oss issue tracker)

## Tone

Honest > breathless. The +20.8pp number is from a built-in TF-IDF
benchmark that demonstrates the technique; with real production
embeddings (MiniLM) the numbers shift. Footnoting that gracefully
preserves trust.

## Cross-reference

Tracked as FU-16 (web part) from sulci-oss v0.4.0 release work. Backed
by competitive analysis at FU-15 (internal sales/marketing wiki — not
public).

## Constraints

- No claims about features that don't exist yet
- No comparisons that risk legal trouble (don't trash competitors)
- No marketing-internal pricing details that haven't been finalized

## Effort

~1 day of copywriting + 2-3 hours of JSX integration.
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
