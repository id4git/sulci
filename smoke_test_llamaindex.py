#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
smoke_test_llamaindex.py
─────────────────────────
Manual smoke test for SulciCacheLLM — no API keys needed.

Run from repo root:
    python smoke_test_llamaindex.py
"""
from typing import Any, Sequence

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseAsyncGen,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseAsyncGen,
    CompletionResponseGen,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.bridge.pydantic import Field
from llama_index.core.llms.llm import LLM

from sulci.integrations.llamaindex import SulciCacheLLM


# ── Call log — external mutable list, survives Pydantic's internal copy ───────

_call_log: list = []


def reset_calls() -> None:
    _call_log.clear()


def call_count() -> int:
    return len(_call_log)


# ── Minimal mock LLM ──────────────────────────────────────────────────────────

class EchoLLM(LLM):
    """LLM that echoes the prompt and logs calls to the external call log."""

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="echo-llm")

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        _call_log.append("complete")
        return CompletionResponse(text=f"[LLM] {prompt}")

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        _call_log.append("chat")
        last = messages[-1].content if messages else ""
        return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content=f"[LLM] {last}"))

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponseGen:
        _call_log.append("stream_complete")
        def gen():
            yield CompletionResponse(text=f"[LLM stream] {prompt}", delta=f"[LLM stream] {prompt}")
        return gen()

    def stream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseGen:
        _call_log.append("stream_chat")
        def gen():
            yield ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content="[LLM stream]"),
                delta="[LLM stream]",
            )
        return gen()

    async def acomplete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        return self.complete(prompt, formatted, **kwargs)

    async def achat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        return self.chat(messages, **kwargs)

    async def astream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponseAsyncGen:
        async def gen():
            yield CompletionResponse(text=f"[LLM astream] {prompt}", delta=f"[LLM astream] {prompt}")
        return gen()

    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseAsyncGen:
        async def gen():
            yield ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content="[LLM astream]"),
                delta="[LLM astream]",
            )
        return gen()


# ── Smoke test ────────────────────────────────────────────────────────────────

import tempfile, os

def main():
    print("=" * 60)
    print("SulciCacheLLM smoke test")
    print("=" * 60)

    tmp_dir = tempfile.mkdtemp(prefix="sulci_smoke_")   # ← fresh every run
    cache = SulciCacheLLM(
        llm       = EchoLLM(),
        backend   = "sqlite",
        db_path   = os.path.join(tmp_dir, "cache"),
        threshold = 0.85,
    )
    
    print(f"\n{cache!r}")

    # ── Demo 1: complete() ────────────────────────────────────────────────────
    print("\n── Demo 1: complete() ──────────────────────────────")
    reset_calls()
    q  = "What is semantic caching?"
    r1 = cache.complete(q)
    print(f"  Miss → {r1.text!r}  (LLM calls: {call_count()})")
    assert call_count() == 1, f"Expected 1 LLM call on miss, got {call_count()}"

    r2 = cache.complete(q)
    print(f"  Hit  → {r2.text!r}  (LLM calls: {call_count()})")
    assert call_count() == 1, f"Expected no extra LLM call on hit, got {call_count()}"
    assert r1.text == r2.text
    print("  ✅  complete() hit/miss correct")

    # ── Demo 2: chat() ────────────────────────────────────────────────────────
    print("\n── Demo 2: chat() ──────────────────────────────────")
    reset_calls()
    msg = ChatMessage(role=MessageRole.USER, content="How does context-aware caching work?")
    c1  = cache.chat([msg])
    print(f"  Miss → {c1.message.content!r}  (LLM calls: {call_count()})")
    assert call_count() == 1

    c2 = cache.chat([msg])
    print(f"  Hit  → {c2.message.content!r}  (LLM calls: {call_count()})")
    assert call_count() == 1
    assert c1.message.content == c2.message.content
    print("  ✅  chat() hit/miss correct")

    # ── Demo 3: stream_complete() passes through ──────────────────────────────
    print("\n── Demo 3: stream_complete() pass-through ──────────")
    reset_calls()
    tokens = list(cache.stream_complete("What is Sulci?"))
    print(f"  Streamed {len(tokens)} token(s): {tokens[0].text!r}")
    assert call_count() == 1
    print("  ✅  stream_complete() pass-through correct")

    # ── Demo 4: stream does NOT populate cache ────────────────────────────────
    print("\n── Demo 4: stream does not populate cache ──────────")
    reset_calls()
    cache.complete("What is Sulci?")   # same prompt as Demo 3 — should be a miss
    print(f"  complete() after stream_complete — LLM calls: {call_count()}")
    assert call_count() == 1, "Stream must not write to cache"
    print("  ✅  stream isolation correct")

    # ── Demo 5: stats ─────────────────────────────────────────────────────────
    print("\n── Demo 5: stats ───────────────────────────────────")
    s = cache.stats()
    print(f"  hits={s['hits']}  misses={s['misses']}  hit_rate={s['hit_rate']:.1%}")
    print(f"\n{cache!r}")

    print("\n✅  All smoke tests passed")


if __name__ == "__main__":
    main()
