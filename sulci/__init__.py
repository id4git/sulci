# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Kathiravan Sengodan

"""
sulci/__init__.py
================
Public API surface for the sulci semantic caching library.

Exports
-------
Cache           — main cache engine (context-aware, v0.2+)
AsyncCache      — non-blocking async wrapper around Cache (v0.3.7+)
ContextWindow   — per-session conversation window
SessionStore    — multi-session manager
connect()       — opt-in telemetry + cloud key registration (v0.3+)

Telemetry
---------
Nothing phones home by default.  Telemetry is strictly opt-in:

    import sulci
    sulci.connect(api_key="sk-sulci-...")   # enables telemetry

Or per-instance:

    cache = Cache(backend="sulci", api_key="sk-sulci-...")

What is sent (aggregate counts only — no query content, no user data):
    {event, backend, hits, misses, avg_latency_ms, sdk_version,
     python_version, fingerprint}

The 9-field shape is locked by the gateway's TelemetryEvent schema
(``extra='forbid'`` — anything else is rejected with HTTP 422 and the
batch is silently dropped). See ``sulci.telemetry.WIRE_FIELDS``.

Data never sent:
    query text, response text, embeddings, user_id, session_id, IP address

The ``fingerprint`` field is a stable 24-char per-deployment hash —
``blake2b(machine_id || backend || embedding_model || threshold ||
context_window, digest_size=12)``. The ``machine_id`` is a
locally-generated ``uuid4`` persisted at ``~/.sulci/config``; it never
leaves the local machine. See :func:`sulci.telemetry.build_fingerprint`.

AsyncCache
----------
Drop-in non-blocking wrapper for FastAPI, LangChain async chains,
LlamaIndex async agents, and any asyncio-based application:

    from sulci import AsyncCache

    cache = AsyncCache(backend="sqlite", threshold=0.85, context_window=4)

    @app.post("/chat")
    async def chat(query: str, session_id: str):
        response, sim, depth = await cache.aget(query, session_id=session_id)
        if response:
            return {"response": response, "source": "cache"}
        response = await call_llm(query)
        await cache.aset(query, response, session_id=session_id)
        return {"response": response, "source": "llm"}

All constructor parameters are identical to Cache.
"""

import os
import threading
import time
from typing import Optional
from importlib.metadata import version as _pkg_version, PackageNotFoundError

# ── Package version ──────────────────────────────────────────────────────────
# Single source of truth: pyproject.toml. We read it via importlib.metadata
# at import time. Editable installs and uninstalled trees fall back to a
# placeholder so the import doesn't crash in dev/test environments.
try:
    __version__ = _pkg_version("sulci")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

# ── Module-level telemetry state ─────────────────────────────────────────────
# Both are False/None by default — connect() is the only way to change them.

_api_key:           Optional[str] = None
_telemetry_enabled: bool          = False

_TELEMETRY_URL = "https://api.sulci.io/v1/telemetry"
_SDK_VERSION   = __version__   # deprecated alias; new code should use sulci.__version__
_FLUSH_INTERVAL_SECONDS = 30

_event_buffer: list  = []
_buffer_lock          = threading.Lock()
_flush_thread_started = False


# ── Public API ────────────────────────────────────────────────────────────────

def connect(
    api_key:   Optional[str] = None,
    telemetry: bool          = True,
) -> None:
    """
    Opt-in gate for Sulci Cloud telemetry and key registration.

    Parameters
    ----------
    api_key : str, optional
        Your Sulci Cloud API key (sk-sulci-...).
        Falls back to SULCI_API_KEY environment variable if not provided.
        Required for telemetry to be enabled.
    telemetry : bool, default True
        Set to False to register your key without enabling telemetry.
        Useful for the sulci backend driver without usage reporting.

    Examples
    --------
    # Typical usage — enables telemetry
    import sulci
    sulci.connect(api_key="sk-sulci-...")

    # Key from environment variable
    # export SULCI_API_KEY="sk-sulci-..."
    sulci.connect()

    # Register key but disable telemetry
    sulci.connect(api_key="sk-sulci-...", telemetry=False)

    # No-op — nothing sent, no key set
    # (just don't call connect() at all)
    """
    global _api_key, _telemetry_enabled

    _api_key = api_key or os.environ.get("SULCI_API_KEY")

    # Telemetry is only active when BOTH conditions are true:
    #   1. the caller explicitly passed telemetry=True (the default)
    #   2. an api_key was resolved
    _telemetry_enabled = telemetry and (_api_key is not None)

    if _telemetry_enabled:
        _start_flush_thread()
        _emit("startup", {})


# ── Internal telemetry helpers ────────────────────────────────────────────────
# All functions below are no-ops when _telemetry_enabled is False.
# All exceptions are swallowed — telemetry must never affect the user's app.

def _emit(event: str, data: dict) -> None:
    """
    Buffer a telemetry event.  O(1) — safe to call from the Cache hot path.

    No-op when telemetry is disabled (the default).
    """
    if not _telemetry_enabled or not _api_key:
        return
    with _buffer_lock:
        _event_buffer.append({
            "event": event,
            "ts":    time.time(),
            **data,
        })


def _flush() -> None:
    """
    Drain the event buffer and POST aggregated batches to api.sulci.io.

    v0.5.2: aggregates cache.get and cache.set events separately, sending
    one HTTP call per event type that has events. cache.get carries
    hit/miss/latency aggregates; cache.set carries write count and
    average write latency (hits = count, misses = 0 by convention — see
    "cache.set semantics" note below).

    Each payload now includes a ``fingerprint`` field — a stable,
    anonymous, config-aware deployment identifier (see
    :func:`sulci.telemetry.build_fingerprint`). This lets the
    ``/v1/analytics/deployments`` dashboard tile group events by
    deployment.

    Startup events (emitted by :func:`connect`) are currently drained
    but not sent — the legacy emit pipe does not include a ``startup``
    POST path. Tracked as a follow-up; the gateway TelemetryEvent model
    accepts ``event='startup'`` so the gap is purely SDK-side.

    Never raises — all exceptions are swallowed silently.

    cache.set semantics
    -------------------
    The gateway's TelemetryEvent schema reuses ``hits`` / ``misses`` /
    ``avg_latency_ms`` for all event types. For ``event='cache.set'``
    the SDK convention is::

        hits           = number of set() calls aggregated
        misses         = 0
        avg_latency_ms = average set() latency

    This is documented here and on the gateway side; a future schema
    revision may rename these fields per-event-type.
    """
    global _event_buffer

    with _buffer_lock:
        if not _event_buffer:
            return
        batch          = _event_buffer[:]
        _event_buffer  = []

    # Build the fingerprint once per flush. We use the most recent
    # event's backend (events from one process should all share one
    # backend; if they don't, the dashboard will show them as separate
    # deployments which is the desired behavior).
    fingerprint = _build_fingerprint_for_batch(batch)

    # Aggregate cache.get events
    get_events  = [e for e in batch if e.get("event") == "cache.get"]
    if get_events:
        hits        = sum(e.get("hits",   0) for e in get_events)
        misses      = sum(e.get("misses", 0) for e in get_events)
        latencies   = [e.get("latency_ms", 0) for e in get_events if e.get("latency_ms")]
        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        backend     = get_events[0].get("backend", "")

        _post({
            "event":          "cache.get",
            "backend":        backend,
            "hits":           hits,
            "misses":         misses,
            "avg_latency_ms": avg_latency,
            "sdk_version":    _SDK_VERSION,
            "python_version": _python_version(),
            "fingerprint":    fingerprint,
        })

    # Aggregate cache.set events (additive, v0.5.2)
    set_events = [e for e in batch if e.get("event") == "cache.set"]
    if set_events:
        latencies   = [e.get("latency_ms", 0) for e in set_events if e.get("latency_ms")]
        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        backend     = set_events[0].get("backend", "")

        _post({
            "event":          "cache.set",
            "backend":        backend,
            "hits":           len(set_events),   # see "cache.set semantics" above
            "misses":         0,
            "avg_latency_ms": avg_latency,
            "sdk_version":    _SDK_VERSION,
            "python_version": _python_version(),
            "fingerprint":    fingerprint,
        })


def _build_fingerprint_for_batch(batch: list) -> Optional[str]:
    """Compute the per-deployment fingerprint for a batch of events.

    Returns ``None`` if the SDK's telemetry helpers can't be imported
    (e.g. test env with only ``__init__.py`` present) — the gateway
    schema accepts ``fingerprint=None``.
    """
    try:
        from sulci.config import get_machine_id
        from sulci.telemetry import build_fingerprint
        machine_id = get_machine_id()
        # Pull config bits off any event in the batch — they're all from
        # the same Cache instance in normal usage. We sniff backend from
        # the first event that carries one.
        backend = ""
        for e in batch:
            if e.get("backend"):
                backend = e["backend"]
                break
        return build_fingerprint(
            machine_id      = machine_id,
            backend         = backend,
            embedding_model = batch[0].get("embedding_model") if batch else None,
            threshold       = batch[0].get("threshold")       if batch else None,
            context_window  = batch[0].get("context_window")  if batch else None,
        )
    except Exception:
        return None


def _post(payload: dict) -> None:
    """POST one aggregated payload to ``/v1/telemetry``. Never raises.

    Strips any non-wire field via :func:`sulci.telemetry.coerce_to_wire`
    as a final guarantee against future flush() regressions accidentally
    leaking SDK-internal fields. The gateway uses ``extra='forbid'``;
    one stray field would HTTP-422 the entire batch.
    """
    try:
        try:
            from sulci.telemetry import coerce_to_wire
            payload = coerce_to_wire(payload)
        except Exception:
            # Helper unavailable (bare-init test env) — payload already
            # constructed with allowlisted keys upstream. Send as-is.
            pass
        import httpx
        httpx.post(
            _TELEMETRY_URL,
            json    = payload,
            headers = {"X-Sulci-Key": _api_key},
            timeout = 3.0,
        )
    except Exception:
        # Never let a telemetry failure surface to the user's app.
        pass


def _flush_loop() -> None:
    """Background thread target: flush every FLUSH_INTERVAL_SECONDS."""
    while True:
        time.sleep(_FLUSH_INTERVAL_SECONDS)
        if not _telemetry_enabled:
            # Telemetry was disabled after the thread started — stop quietly.
            return
        _flush()


def _start_flush_thread() -> None:
    """
    Start the background flush thread exactly once.

    Uses a module-level flag rather than checking thread.is_alive() to
    avoid the overhead of thread object lookup on every connect() call.
    """
    global _flush_thread_started
    if _flush_thread_started:
        return
    _flush_thread_started = True
    t = threading.Thread(target=_flush_loop, daemon=True, name="sulci-telemetry-flush")
    t.start()


# ── Core library imports (lazy) ───────────────────────────────────────────────
# Imported here rather than at the top so:
#   1. The telemetry module is independently testable without the full
#      sulci package installed (test_connect.py has no dependency on Cache).
#   2. Circular import risk between __init__ -> core -> __init__ is avoided.
#
# In normal usage (pip install sulci) these always resolve.
# In test-only environments (just __init__.py present) they gracefully
# return None and the telemetry tests still pass.

try:
    from sulci.core import Cache
    from sulci.context import ContextWindow, SessionStore
    from sulci.async_cache import AsyncCache
    # v0.5.0 — new protocols and implementations (additive; ADR 0004 + ADR 0007)
    # Note: top-level `sulci.SessionStore` continues to be the legacy class
    # from sulci.context (backward compat). The new sulci.sessions.SessionStore
    # protocol is namespaced and accessed via `from sulci.sessions import SessionStore`.
    from sulci.sessions import InMemorySessionStore, RedisSessionStore
    from sulci.sinks    import EventSink, NullSink, RedisStreamSink, TelemetrySink, CacheEvent
    SyncCache = Cache   # naming symmetry with AsyncCache
except ImportError:
    Cache                = None  # type: ignore[assignment]
    ContextWindow        = None  # type: ignore[assignment]
    SessionStore         = None  # type: ignore[assignment]
    AsyncCache           = None  # type: ignore[assignment]
    SyncCache            = None  # type: ignore[assignment]
    InMemorySessionStore = None  # type: ignore[assignment]
    RedisSessionStore    = None  # type: ignore[assignment]
    EventSink            = None  # type: ignore[assignment]
    NullSink             = None  # type: ignore[assignment]
    RedisStreamSink      = None  # type: ignore[assignment]
    TelemetrySink        = None  # type: ignore[assignment]
    CacheEvent           = None  # type: ignore[assignment]


def _python_version() -> str:
    import sys
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


# ── Public exports ────────────────────────────────────────────────────────────

__all__ = [
    "Cache",
    "SyncCache",
    "AsyncCache",
    "ContextWindow",
    "SessionStore",            # legacy class (sulci.context)
    "InMemorySessionStore",    # new protocol impl (sulci.sessions)
    "RedisSessionStore",       # new protocol impl (sulci.sessions)
    "EventSink",               # new protocol (sulci.sinks)
    "NullSink",                # new protocol impl
    "RedisStreamSink",         # new protocol impl
    "TelemetrySink",           # new protocol impl
    "CacheEvent",              # event dataclass
    "connect",
]
