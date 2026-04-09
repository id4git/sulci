# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Kathiravan Sengodan
"""
sulci.integrations.langchain
─────────────────────────────
Context-aware semantic cache adapter for LangChain, backed by Sulci.

This module is the canonical home of SulciCache inside the sulci package.
The same class is also submitted as a PR to langchain_community/cache.py
so it appears in the official LangChain cache integrations listing.

Usage:
    from langchain.globals import set_llm_cache
    from sulci.integrations.langchain import SulciCache

    set_llm_cache(SulciCache(backend="sqlite"))

Or, once merged into langchain-community:
    from langchain_community.cache import SulciCache
    from langchain.globals import set_llm_cache

    set_llm_cache(SulciCache(backend="sqlite"))

Install:
    pip install "sulci[langchain]"
    # which installs: sulci + langchain-core
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Any, Optional, Sequence

logger = logging.getLogger(__name__)

# langchain-core is optional — guard the import clearly.
try:
    from langchain_core.caches import BaseCache
    from langchain_core.outputs import Generation
except ImportError as _lc_err:  # pragma: no cover
    raise ImportError(
        "langchain-core is required for sulci.integrations.langchain.\n"
        "Install: pip install \"sulci[langchain]\"\n"
        "or:      pip install langchain-core"
    ) from _lc_err


class SulciCache(BaseCache):
    """
    Context-aware semantic cache for LangChain, backed by Sulci.

    Unlike exact-match caches (``InMemoryCache``, ``SQLiteCache``) and
    stateless semantic caches (``GPTCache``, ``RedisSemanticCache``),
    SulciCache blends prior conversation turns into the similarity lookup
    vector — giving dramatically higher hit rates in multi-turn workloads:

    .. list-table::
       :header-rows: 1

       * - Workload
         - Stateless semantic
         - SulciCache (context-aware)
       * - Customer support
         - 32%
         - **88%** (+56 pp)
       * - Developer Q&A
         - 80%
         - **96%** (+16 pp)

    ``context_window=0`` (default) is fully stateless and backward-
    compatible.  Raise it to 4 to unlock context-aware mode:

    - Customer support:  32% → 88% hit rate  (+56 pp)
    - Developer Q&A:     80% → 96% hit rate  (+16 pp)

    Args:
        namespace_by_llm (bool):
            When ``True`` (default) each unique LLM configuration (model
            name, temperature, …) is stored in a separate cache partition
            so a GPT-4o response is never returned for a Claude query.
            Set to ``False`` to share one cache across all models.
        **kwargs:
            All remaining arguments are forwarded to ``sulci.Cache``::

                backend         "sqlite"|"chroma"|"qdrant"|"faiss"|
                                "redis"|"milvus"|"sulci"  (default "sqlite")
                threshold       Cosine similarity cutoff 0–1  (default 0.85)
                embedding_model "minilm"|"mpnet"|"bge"|"openai"
                ttl_seconds     Entry lifetime in seconds (None = no expiry)
                context_window  Turns to remember; 0 = stateless (default)
                query_weight    α in blending formula  (default 0.70)
                context_decay   Per-turn decay         (default 0.50)
                api_key         Sulci Cloud key (backend="sulci")
                gateway_url     Custom gateway for Enterprise VPC deployments
                                (default: https://api.sulci.io)
                personalized    Partition per user_id  (default False)
                db_path         On-disk path for SQLite/FAISS backends

    Examples:
        # Self-hosted SQLite — zero infrastructure
        set_llm_cache(SulciCache(backend="sqlite"))

        # Context-aware — chatbot / agent
        set_llm_cache(SulciCache(
            backend="sqlite",
            context_window=4,
            threshold=0.75,
        ))

        # Qdrant — production deployment
        set_llm_cache(SulciCache(backend="qdrant", ttl_seconds=86400))

        # Managed Sulci Cloud
        set_llm_cache(SulciCache(backend="sulci", api_key="sk-sulci-..."))
        # or via env var: SULCI_API_KEY=sk-sulci-...
        set_llm_cache(SulciCache(backend="sulci"))
    """

    def __init__(
        self,
        *,
        namespace_by_llm: bool = True,
        **kwargs: Any,
    ) -> None:
        # Lazy import: sulci is only required at instantiation time,
        # not when langchain_community.cache is imported.
        try:
            from sulci import Cache as _Cache
        except ImportError as exc:
            raise ImportError(
                "sulci is required for SulciCache.\n"
                "Install: pip install \"sulci[sqlite]\"  # or another backend"
            ) from exc

        # namespace_by_llm has no effect with the managed cloud backend —
        # Sulci Cloud handles tenant isolation server-side via API key.
        # Creating per-LLM db_path partitions spins up phantom
        # SulciCloudBackend instances that all hit the same cloud namespace.
        if namespace_by_llm and kwargs.get("backend") == "sulci":
            logger.warning(
                "SulciCache: namespace_by_llm=True has no effect when "
                "backend='sulci'. Sulci Cloud handles isolation server-side. "
                "Set namespace_by_llm=False to suppress this warning."
            )
            namespace_by_llm = False

        self._namespace_by_llm = namespace_by_llm
        self._kwargs            = kwargs
        self._default_cache     = _Cache(**kwargs)
        self._ns_caches: dict[str, Any] = {}
        self._Cache = _Cache  # keep reference for namespace clone construction

    # ── Namespace helpers ──────────────────────────────────────────────────────

    def _cache_for(self, llm_string: str) -> Any:
        """
        Return the sulci.Cache instance for this llm_string.

        When namespace_by_llm=True each unique LLM config gets its own
        on-disk partition (db_path suffixed with an 8-char MD5 hash) so
        models never share cached responses.
        """
        if not self._namespace_by_llm:
            return self._default_cache

        if llm_string not in self._ns_caches:
            ns     = hashlib.md5(llm_string.encode()).hexdigest()[:8]
            kwargs = dict(self._kwargs)
            base   = kwargs.pop("db_path", "./sulci_lc")
            kwargs["db_path"] = f"{base}_{ns}"
            self._ns_caches[llm_string] = self._Cache(**kwargs)

        return self._ns_caches[llm_string]

    # ── BaseCache interface ────────────────────────────────────────────────────

    def lookup(
        self,
        prompt: str,
        llm_string: str,
    ) -> Optional[list[Generation]]:
        """
        Called by LangChain before every LLM API call.

        Returns a list containing one Generation on a semantic cache hit,
        or None on a miss.  All errors are swallowed — a cache failure
        must never raise an exception in the caller's application.
        """
        try:
            # sulci.Cache.get() always returns a 3-tuple:
            # (response: str|None, similarity: float, context_depth: int)
            response, similarity, depth = self._cache_for(llm_string).get(prompt)
            if response is None:
                return None
            logger.debug(
                "sulci HIT  sim=%.3f  depth=%d  prompt=%r",
                similarity, depth, prompt[:60],
            )
            return [Generation(text=response)]
        except Exception:
            logger.warning(
                "sulci lookup error — treating as cache miss", exc_info=True
            )
            return None

    def update(
        self,
        prompt: str,
        llm_string: str,
        return_val: Sequence[Generation],
    ) -> None:
        """
        Called by LangChain after every successful LLM API call.

        Stores the first Generation text in the Sulci cache.  Errors
        are swallowed — a failed cache write must never crash the app.
        """
        if not return_val:
            return
        try:
            self._cache_for(llm_string).set(prompt, return_val[0].text)
            logger.debug("sulci SET  prompt=%r", prompt[:60])
        except Exception:
            logger.warning("sulci update error — skipping store", exc_info=True)

    def clear(self, **kwargs: Any) -> None:
        """Evict all entries across the default cache and all NS partitions."""
        # Snapshot values first — avoids any dict-changed-during-iteration issues.
        caches_to_clear = [self._default_cache] + list(self._ns_caches.values())
        try:
            for c in caches_to_clear:
                c.clear()
        except Exception:
            logger.warning("sulci clear error", exc_info=True)
        finally:
            # Always reset the namespace dict — even if data clearing partly failed.
            # This guarantees _ns_caches is empty after clear() is called.
            self._ns_caches.clear()

    # ── Async overrides ────────────────────────────────────────────────────────
    # LangChain recommends overriding these to avoid spawning excess threads.
    # We delegate to the synchronous implementations via run_in_executor so
    # the event loop is never blocked.

    async def alookup(
        self,
        prompt: str,
        llm_string: str,
    ) -> Optional[list[Generation]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.lookup, prompt, llm_string)

    async def aupdate(
        self,
        prompt: str,
        llm_string: str,
        return_val: Sequence[Generation],
    ) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.update, prompt, llm_string, return_val)

    async def aclear(self, **kwargs: Any) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.clear)

    # ── Extras ────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """
        Return Sulci cache statistics from the default cache partition.

        Keys: hits, misses, hit_rate, saved_cost, total_queries,
              active_sessions.
        """
        return self._default_cache.stats()

    def __repr__(self) -> str:
        s = self._default_cache.stats()
        return (
            f"SulciCache("
            f"hit_rate={s.get('hit_rate', 0):.1%}, "
            f"hits={s.get('hits', 0)}, "
            f"misses={s.get('misses', 0)}, "
            f"saved=${s.get('saved_cost', 0):.2f})"
        )
