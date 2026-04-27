# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Kathiravan Sengodan
"""
sulci/sinks/protocol.py — EventSink protocol + CacheEvent (v0.5.0)

STABLE API — modifications require superseding ADR per ADR 0005.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Optional, Dict, Any


@dataclass
class CacheEvent:
    """
    Emitted by Cache on every hit/miss/set/clear.

    Privacy discipline: sinks shipped with sulci MUST NOT emit query text,
    response text, or embedding vectors externally. Only the metadata
    envelope shown below leaves the process. TelemetrySink enforces this
    via an explicit field allowlist.
    """
    event_type: str                             # 'hit' | 'miss' | 'set' | 'clear'
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    backend_id: Optional[str] = None            # e.g. 'qdrant', 'chroma', 'sulci'
    embedding_model: Optional[str] = None       # e.g. 'minilm', 'openai'
    similarity: Optional[float] = None          # for 'hit' events
    latency_ms: Optional[int] = None            # for 'hit' and 'miss'
    context_depth: int = 0                      # number of session turns consulted
    timestamp: Optional[float] = None           # unix timestamp
    metadata: Dict[str, Any] = field(default_factory=dict)   # extension point


@runtime_checkable
class EventSink(Protocol):
    """
    Receives CacheEvent on every cache operation.

    Implementations shipped in v0.5.0:
      - NullSink         — no-op, default
      - TelemetrySink    — HTTPS POST to endpoint with field allowlist
      - RedisStreamSink  — writes to Redis Stream for billing/observability

    Custom implementations: any class matching this surface.
    """

    def emit(self, event: CacheEvent) -> None:
        """
        Handle a cache event. Called on every hit/miss/set/clear.

        MUST NOT raise on delivery failure — degrade gracefully
        (log and continue). A failing sink must never break the
        caller's cache operation.
        """
        ...

    def flush(self) -> None:
        """
        Force-flush any buffered events.

        Called at Cache.__del__ and on explicit user flush.
        May be a no-op for sinks that don't buffer.
        """
        ...
