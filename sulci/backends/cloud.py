# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Kathiravan Sengodan

# sulci/backends/cloud.py
"""
SulciCloudBackend — routes cache operations to Sulci Cloud via HTTPS.

Zero infrastructure for the user. One parameter change from self-hosted:

    # Before
    cache = Cache(backend="sqlite", threshold=0.85)

    # After
    cache = Cache(backend="sulci", api_key="sk-sulci-...", threshold=0.85)

All public methods match the contract expected by Cache in core.py:
    search(embedding, threshold, user_id, now) -> (response|None, similarity)
    upsert(embedding, query, response, user_id, ttl_seconds)
    delete_user(user_id)
    clear()
"""

import httpx
from typing import Optional

from sulci import __version__


class SulciCloudBackend:
    """
    Thin HTTPS client wrapping the Sulci Cloud API.

    Preserves the exact same backend interface as all local backends
    so core.py needs zero changes to use it.

    Failure policy:
        - search() timeout or error  → returns (None, 0.0)  — treated as cache miss
        - upsert() failure           → silently ignored      — fire and forget
        - Never raises to the caller — the user's app must never crash due to cache
    """

    #: Tenant isolation is enforced server-side by the Sulci Cloud gateway,
    #: keyed off the api_key (1:1 with a tenant). Declared False here because
    #: the OSS conformance suite cannot reach the gateway to verify enforcement
    #: locally. A custom local-gateway test harness could flip this to True.
    ENFORCES_TENANT_ISOLATION: bool = False

    CLOUD_URL    = "https://api.sulci.io"
    USER_AGENT   = f"sulci/{__version__}"

    def __init__(
        self,
        api_key:     str,
        timeout:     float = 5.0,
        gateway_url: str   = "",
    ):
        if not api_key:
            raise ValueError(
                "api_key is required for backend='sulci'. "
                "Get your free key at https://sulci.io/signup"
            )

        self._api_key  = api_key
        self._timeout  = timeout
        self._base_url = gateway_url.rstrip("/") if gateway_url else self.CLOUD_URL
        self._client   = httpx.Client(
            base_url = self._base_url,
            headers  = {
                "X-Sulci-Key":   api_key,
                "Content-Type":  "application/json",
                "User-Agent":    self.USER_AGENT,
            },
            timeout  = httpx.Timeout(timeout),
        )

    # ── Public interface — matches local backend contract ─────────────────────

    def search(
        self,
        embedding:  list,
        threshold:  float,
        *,
        tenant_id:  Optional[str] = None,
        user_id:    Optional[str] = None,
        now:        Optional[float] = None,
    ) -> tuple:
        """
        Semantic lookup via cloud API.

        Tenant isolation is enforced server-side by the gateway based on
        the api_key (which maps 1:1 to a tenant). The `tenant_id` kwarg
        is forwarded to the gateway for logging and for the rare cases
        where one api_key is authorized across multiple tenants.

        Returns:
            (response, similarity) where response is None on miss.
            Falls back to (None, 0.0) on any network error — never raises.
        """
        try:
            resp = self._client.post(
                "/v1/get",
                json={
                    "embedding": embedding,
                    "threshold": threshold,
                    "tenant_id": tenant_id,
                    "user_id":   user_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return (
                data.get("response"),
                float(data.get("similarity", 0.0)),
            )
        except httpx.TimeoutException:
            # Timeout — treat as cache miss, never crash
            return None, 0.0
        except Exception:
            # Any other error — treat as cache miss, never crash
            return None, 0.0

    def store(
        self,
        key: str,
        query: str,
        response: str,
        embedding: list,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        expires: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Store a cache entry in the cloud (Backend protocol method).

        Translates the protocol's (key, expires) parameters to the cloud
        API's (ttl_seconds) shape and forwards to /v1/set. Fire-and-forget
        — silently ignores all errors per the Backend protocol contract.

        Note: `key` and `metadata` are sent to the gateway for record-
        keeping but the cloud API does not currently use them for lookup.
        """
        import time as _time
        ttl_seconds: Optional[int] = None
        if expires:
            ttl_seconds = max(0, int(expires - _time.time()))
        try:
            self._client.post(
                "/v1/set",
                json={
                    "key":         key,
                    "embedding":   embedding,
                    "query":       query,
                    "response":    response,
                    "tenant_id":   tenant_id,
                    "user_id":     user_id,
                    "ttl_seconds": ttl_seconds,
                    "metadata":    metadata,
                },
            )
        except Exception:
            pass

    def upsert(
        self,
        embedding:   list,
        query:       str,
        response:    str,
        user_id:     Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Store a cache entry in the cloud.
        Fire-and-forget — silently ignores all errors.
        """
        try:
            self._client.post(
                "/v1/set",
                json={
                    "embedding":   embedding,
                    "query":       query,
                    "response":    response,
                    "user_id":     user_id,
                    "ttl_seconds": ttl_seconds,
                },
            )
        except Exception:
            pass   # Never crash the user's app on a failed write

    def delete_user(self, user_id: str) -> None:
        """Delete all cache entries for a given user_id."""
        try:
            self._client.delete(f"/v1/user/{user_id}")
        except Exception:
            pass

    def clear(self) -> None:
        """Clear all cache entries for this tenant."""
        try:
            self._client.delete("/v1/cache")
        except Exception:
            pass

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying httpx client."""
        try:
            self._client.close()
        except Exception:
            pass

    def __del__(self):
        self.close()

    def __repr__(self) -> str:
        return (
            f"SulciCloudBackend("
            f"url={self._base_url!r}, "
            f"key_prefix={self._api_key[:16]!r}, "
            f"timeout={self._timeout})"
        )
