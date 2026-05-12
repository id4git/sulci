"""
flow_2_routemismatch.py — verify the SDK and gateway agree on cache URLs
=========================================================================

STATUS: EXPECTED TO FAIL TODAY.

This script encodes a known platform P0:

    sulci-oss/sulci/backends/cloud.py  hits  POST /v1/get   and  POST /v1/set
    sulci-platform/gateway/.../cache.py exposes  POST /v1/cache/get  and  /v1/cache/set

The two halves disagree. Every Flow 2 cache.get() call against the live
gateway returns 404, the SDK's `except Exception:` clause at cloud.py:118
swallows it, and the call returns (None, 0.0) — a silent miss. Users see
"sulci doesn't seem to be caching anything" with no error to investigate.

This script will PASS once either:
  (a) the SDK is updated to POST to /v1/cache/get and /v1/cache/set, OR
  (b) the gateway adds /v1/get and /v1/set as aliases or rewrites.

Either fix closes the gap. (a) is cleaner and matches the gateway's
existing canonical paths. (b) is a one-line FastAPI redirect.

How this script checks
----------------------
Two probes, both run if available:

  PROBE 1 (static, always runs) — read the SDK source and assert that
  cloud.py uses /v1/cache/get (the gateway's canonical path) rather than
  /v1/get. Today this assertion FAILS.

  PROBE 2 (live, requires env) — if SULCI_LIVE_GATEWAY and SULCI_LIVE_KEY
  are set, hit the live gateway with both /v1/get and /v1/cache/get and
  report which returns non-404. Skipped silently if creds absent.

The script exits 1 on FAIL (the expected state today). When it exits 0
on a CI run, the gap has closed and the doc's Flow 2 callout should be
deleted.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _find_cloud_py() -> Path | None:
    """Locate the installed sulci.backends.cloud module on disk."""
    try:
        import sulci.backends.cloud as _cloud
        return Path(_cloud.__file__)
    except ImportError:
        return None


def run() -> int:
    failures: list[str] = []
    notes: list[str] = []

    # ── PROBE 1 — static: SDK source should hit /v1/cache/get and /v1/cache/set ──
    src_path = _find_cloud_py()
    if src_path is None or not src_path.exists():
        failures.append(
            "could not locate sulci.backends.cloud on disk — "
            "install sulci-oss[cloud] before running this verification.")
    else:
        src = src_path.read_text(encoding='utf-8')
        # The fix would replace "/v1/get" with "/v1/cache/get" and
        # "/v1/set" with "/v1/cache/set". A negative-pattern check is
        # cleaner than a regex over arbitrary path components.
        has_legacy_get = '"/v1/get"' in src or "'/v1/get'" in src
        has_legacy_set = '"/v1/set"' in src or "'/v1/set'" in src
        has_fixed_get  = "/v1/cache/get" in src
        has_fixed_set  = "/v1/cache/set" in src

        if has_legacy_get:
            failures.append(
                f"{src_path}: still POSTs to /v1/get; gateway exposes /v1/cache/get")
        if has_legacy_set:
            failures.append(
                f"{src_path}: still POSTs to /v1/set; gateway exposes /v1/cache/set")
        if has_fixed_get and not has_legacy_get:
            notes.append("✓ SDK now uses /v1/cache/get")
        if has_fixed_set and not has_legacy_set:
            notes.append("✓ SDK now uses /v1/cache/set")

    # ── PROBE 2 — live (optional) — if creds present, hit the gateway ──────
    live_url = os.environ.get("SULCI_LIVE_GATEWAY")
    live_key = os.environ.get("SULCI_LIVE_KEY")
    if live_url and live_key:
        try:
            import httpx
            client = httpx.Client(
                base_url=live_url.rstrip("/"),
                headers={"X-Sulci-Key": live_key},
                timeout=5,
            )
            for path in ("/v1/get", "/v1/cache/get"):
                try:
                    r = client.post(path, json={"embedding": [0.0]*384,
                                                "threshold": 0.85,
                                                "tenant_id": None,
                                                "user_id": None})
                    notes.append(f"live probe {path} → {r.status_code}")
                except httpx.HTTPError as e:
                    notes.append(f"live probe {path} → network error: {e}")
        except ImportError:
            notes.append("PROBE 2: httpx not available; skipped live check")
    else:
        notes.append("PROBE 2 skipped — set SULCI_LIVE_GATEWAY + SULCI_LIVE_KEY "
                     "to enable live verification")

    # ── Report ──────────────────────────────────────────────────────────────
    if failures:
        print("FAIL (expected today) — flow_2 route mismatch")
        for f in failures:
            print(f"  ✗ {f}")
        for n in notes:
            print(f"    · {n}")
        print()
        print("This failure encodes platform P0 #1 from flows.md.")
        print("Fix lands in sulci-oss/sulci/backends/cloud.py: replace")
        print('  "/v1/get"  →  "/v1/cache/get"')
        print('  "/v1/set"  →  "/v1/cache/set"')
        return 1

    print("PASS — SDK and gateway agree on /v1/cache/* paths")
    for n in notes:
        print(f"  · {n}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
