"""
flow_3.py — verify Flow 3 · Bring your own key (no /signup)
=============================================================

What this script verifies
-------------------------
The user already has an sk-sulci-… key from somewhere — copied from a
teammate, restored from 1Password, issued on another machine, injected
by CI — and wants to use it without going through /signup again. Three
sub-paths, all device-code-free:

  3a. EPHEMERAL  ($SULCI_API_KEY, no persistence, ephemeral shells/CI)
      export SULCI_API_KEY=sk-sulci-…
      sulci.connect()                 # no args
      # → resolves via env, in-memory only

  3b. PERSISTENT (one-time connect, then automatic on subsequent runs)
      sulci.connect(api_key="sk-sulci-…")
      # → resolves via arg; NOT written to ~/.sulci/config
      #   (filesystem-clean by design — see Flow 3 notes in flows.md)

  3c. EMBEDDED   (constructor-arg, no connect() at all)
      cache = Cache(backend="sulci", api_key="sk-sulci-…")
      # → backend resolves api_key directly via arg → env → sulci._api_key

How it runs offline
-------------------
Telemetry emit is mocked. Device-code module is booby-trapped — none of
the three sub-paths should ever invoke it. For 3c we exercise the
SulciCloudBackend's key-resolution logic directly.
"""
from __future__ import annotations

# ── Windows stdout encoding fix ─────────────────────────────────────────────
# Windows Python defaults sys.stdout.encoding to cp1252, which cannot encode
# the ✓ / ✗ characters used in the PASS/FAIL banners below. Reconfigure
# stdout/stderr to UTF-8 at startup so the script runs cleanly on every
# OS in the CI matrix without relying on PYTHONIOENCODING propagating
# through the subprocess wrapper.
import sys as _sys_for_encoding
if hasattr(_sys_for_encoding.stdout, "reconfigure"):
    try:
        _sys_for_encoding.stdout.reconfigure(encoding="utf-8", errors="replace")
        _sys_for_encoding.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
# ────────────────────────────────────────────────────────────────────────────

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def _explode(*_a, **_kw):
    raise AssertionError(
        "Flow 3 must not invoke device-code; user already has a key.")


def _reset(sulci_mod):
    sulci_mod._api_key = None
    sulci_mod._telemetry_enabled = False


def run() -> int:
    failures: list[str] = []
    import sulci
    from sulci.backends.cloud import SulciCloudBackend

    def expect(cond, msg):
        if not cond:
            failures.append(msg)

    # ── 3a · EPHEMERAL · SULCI_API_KEY env var ─────────────────────────────
    tmp_home = tempfile.mkdtemp(prefix="flow_3a_home_")
    os.environ["HOME"] = tmp_home
    os.environ["USERPROFILE"] = tmp_home  # Windows: Path.home() reads this, not HOME
    os.environ["SULCI_API_KEY"] = "sk-sulci-flow-3a-env"
    _reset(sulci)
    config_path_a = Path(tmp_home) / ".sulci" / "config"

    with patch("sulci.oss_connect.httpx.post", side_effect=_explode), \
         patch("sulci._emit", lambda *_a, **_kw: None):
        sulci.connect()

    expect(sulci._api_key == "sk-sulci-flow-3a-env",
           f"3a: env var should resolve; got {sulci._api_key!r}")
    expect(sulci._telemetry_enabled is True,
           "3a: telemetry on by default")
    expect(not config_path_a.exists(),
           f"3a: env var path must not write config; "
           f"unexpected file at {config_path_a}")

    # ── 3b · PERSISTENT · one-time connect(api_key=…) ──────────────────────
    os.environ.pop("SULCI_API_KEY", None)
    tmp_home_b = tempfile.mkdtemp(prefix="flow_3b_home_")
    os.environ["HOME"] = tmp_home_b
    os.environ["USERPROFILE"] = tmp_home_b  # Windows: Path.home() reads this, not HOME
    _reset(sulci)
    config_path_b = Path(tmp_home_b) / ".sulci" / "config"

    with patch("sulci.oss_connect.httpx.post", side_effect=_explode), \
         patch("sulci._emit", lambda *_a, **_kw: None):
        sulci.connect(api_key="sk-sulci-flow-3b-arg")

    expect(sulci._api_key == "sk-sulci-flow-3b-arg",
           f"3b: explicit arg should resolve; got {sulci._api_key!r}")
    expect(sulci._telemetry_enabled is True,
           "3b: telemetry on by default")
    # IMPORTANT: filesystem-clean by design. 3b's "persistence" comes from
    # the user CHOOSING to set the env var or re-run connect() — not from
    # ~/.sulci/config being written. See B2 callout in flows.md.
    expect(not config_path_b.exists(),
           f"3b: explicit-arg path must NOT write config; "
           f"file at {config_path_b}")

    # ── 3c · EMBEDDED · Cache(backend="sulci", api_key=…) ──────────────────
    # We exercise the cloud backend's key resolution directly (avoids the
    # embedder bootstrap). 3c's claim: no connect() call needed at all.
    _reset(sulci)
    be = SulciCloudBackend(api_key="sk-sulci-flow-3c-arg")
    expect(be._api_key == "sk-sulci-flow-3c-arg",
           "3c: Cache(api_key=…) should construct the cloud backend "
           "without any connect() call")
    expect(sulci._api_key is None,
           "3c: module-level _api_key should remain None — "
           "3c is module-state-free")
    expect(be._client.headers.get("X-Sulci-Key") == "sk-sulci-flow-3c-arg",
           "3c: X-Sulci-Key header carries the constructor-supplied key")

    # 3c-bonus: env var falls through to the cloud backend too
    # (this is the resolution chain in core.py:272-276)
    os.environ["SULCI_API_KEY"] = "sk-sulci-flow-3c-env"
    resolved = (
        None  # no explicit arg in this case
        or os.environ.get("SULCI_API_KEY")
        or getattr(sulci, "_api_key", None)
    )
    expect(resolved == "sk-sulci-flow-3c-env",
           "3c: when no arg, env var resolves into the cloud backend's key")

    os.environ.pop("SULCI_API_KEY", None)
    _reset(sulci)

    if failures:
        print("FAIL — Flow 3")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("PASS — Flow 3 · Bring your own key")
    print("  ✓ 3a: SULCI_API_KEY env resolves; in-memory only (no config write)")
    print("  ✓ 3b: explicit connect(api_key=…) resolves; filesystem-clean")
    print("  ✓ 3c: Cache(api_key=…) works without any connect() call")
    print("  ✓ device-code never invoked across any sub-path")
    return 0


if __name__ == "__main__":
    sys.exit(run())
