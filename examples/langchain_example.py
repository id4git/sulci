"""
examples/langchain_example.py
==============================
Sulci Cache + LangChain — semantic and context-aware caching demo.

Works with OpenAI or Anthropic API keys, or falls back to a mock LLM.

Requirements:
    pip install "sulci[sqlite,langchain]"
    pip install langchain-openai      # for OpenAI
    pip install langchain-anthropic   # for Anthropic

    export OPENAI_API_KEY=sk-...        # OpenAI (checked first)
    export ANTHROPIC_API_KEY=sk-ant-... # Anthropic (checked second)
    # No key set → mock LLM used automatically

Run:
    python examples/langchain_example.py

Two patterns demonstrated:

  1. Stateless semantic cache — set_llm_cache(SulciCache(...)) + llm.invoke()
     Every LangChain call goes through the cache with zero code changes.

  2. Context-aware semantic cache — SulciCache subclass uses llm_string as
     session_id so prior conversation turns influence the lookup vector,
     dramatically improving hit rates on ambiguous follow-up questions.
"""
import os, sys, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.globals import set_llm_cache
from langchain_core.outputs import Generation
from sulci.integrations.langchain import SulciCache

# ── Shared cache db path ──────────────────────────────────────────────────────
_DB_PATH = os.path.join(tempfile.mkdtemp(prefix="sulci_lc_"), "cache")


# ── SulciCache subclass: uses llm_string as session_id ───────────────────────
class ContextAwareSulciCache(SulciCache):
    """
    Extends SulciCache with context-aware lookup.

    By using llm_string as session_id, each unique conversation gets its own
    context window. Sulci Cache blends prior turns into the lookup vector so
    ambiguous follow-up questions resolve correctly within the session.

    Usage:
        cache = ContextAwareSulciCache(backend="sqlite", context_window=4)
        set_llm_cache(cache)

        session = "user-alice-conv-1"   # unique per conversation
        cache.lookup("Can you give me an example?", session)   # context-aware
        cache.update("...", session, [Generation(text="...")])
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._hits   = 0
        self._misses = 0

    def lookup(self, prompt: str, llm_string: str):
        """llm_string doubles as session_id for context-aware lookup."""
        try:
            resp, sim, depth = self._default_cache.get(
                prompt, session_id=llm_string
            )
            if resp is not None:
                self._hits += 1
                return [Generation(text=resp)]
            self._misses += 1
            return None
        except Exception:
            self._misses += 1
            return None

    def update(self, prompt: str, llm_string: str, return_val) -> None:
        """Store response and advance context window for this session."""
        if not return_val:
            return
        try:
            self._default_cache.set(
                prompt, return_val[0].text, session_id=llm_string
            )
        except Exception:
            pass

    @property
    def total(self):
        return self._hits + self._misses

    @property
    def hit_rate(self):
        return self._hits / self.total if self.total else 0.0


# ── LLM setup: OpenAI → Anthropic → mock ─────────────────────────────────────
_has_openai    = bool(os.environ.get("OPENAI_API_KEY"))
_has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

print("── API key detection ──────────────────────────────")
print(f"  OPENAI_API_KEY    : {'✓ found' if _has_openai    else '✗ not set'}")
print(f"  ANTHROPIC_API_KEY : {'✓ found' if _has_anthropic else '✗ not set'}")

_llm        = None
_using_mock = False

if _has_openai:
    try:
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        print("  → Using: OpenAI gpt-4o-mini\n")
    except ImportError:
        print("  ✗ langchain-openai not installed — run: pip install langchain-openai")

if _llm is None and _has_anthropic:
    try:
        from langchain_anthropic import ChatAnthropic
        _llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
        print("  → Using: Anthropic claude-haiku-4-5-20251001\n")
    except ImportError:
        print("  ✗ langchain-anthropic not installed — run: pip install langchain-anthropic")

if _llm is None:
    _using_mock = True
    print("  → Using: mock LLM (no API key found — set OPENAI_API_KEY or ANTHROPIC_API_KEY)\n")

    from langchain_core.language_models.llms import BaseLLM
    from langchain_core.outputs import LLMResult
    from typing import Any, List, Optional

    class _MockLLM(BaseLLM):
        @property
        def _llm_type(self) -> str:
            return "mock"

        def _generate(
            self,
            prompts:     List[str],
            stop:        Optional[List[str]] = None,
            run_manager: Any = None,
            **kwargs:    Any,
        ) -> LLMResult:
            responses = []
            for prompt in prompts:
                p = prompt.lower()
                if "semantic" in p or "cache" in p:
                    text = "Semantic caching stores LLM responses indexed by meaning, not exact text."
                elif "langchain" in p:
                    text = "LangChain is a framework for building LLM-powered applications."
                elif "cap" in p or "distributed" in p:
                    text = "The CAP theorem: a distributed system can guarantee only two of Consistency, Availability, Partition tolerance."
                elif "rest" in p or "api" in p:
                    text = "A REST API uses HTTP methods (GET, POST, PUT, DELETE) to expose resources via URLs."
                elif "decorator" in p:
                    text = "A Python decorator wraps a function to extend its behaviour without modifying it."
                elif "example" in p or "show" in p:
                    text = "Example: cache = Cache(backend='sqlite'); cache.set('q', 'a')."
                elif "different" in p or "standard" in p or "traditional" in p:
                    text = "Unlike exact-match caches, semantic caching matches by meaning — paraphrases hit."
                elif "benefit" in p or "advantage" in p:
                    text = "Benefits: lower LLM costs, faster responses, higher hit rates in multi-turn conversations."
                else:
                    text = f"[Mock] Answer to: {prompt[:60]}"
                responses.append([Generation(text=text)])
            return LLMResult(generations=responses)

    _llm = _MockLLM()


# ── Helper: call LLM and route through cache ──────────────────────────────────
def _invoke(question: str, session: str, cache: ContextAwareSulciCache) -> dict:
    """
    Check cache first (using session as session_id), call LLM on miss.

    For real LLMs, llm.invoke() triggers LangChain's internal cache lookup.
    We use session as the llm_string so ContextAwareSulciCache routes it
    to the right context window.
    """
    t0  = time.perf_counter()
    hit = cache.lookup(question, session)

    if hit is not None:
        ms = (time.perf_counter() - t0) * 1000
        return {"response": hit[0].text, "source": "cache",
                "latency_ms": round(ms, 1), "cache_hit": True}

    # Cache miss — call LLM
    if _using_mock:
        response_text = _llm._generate([question]).generations[0][0].text
    else:
        response_text = _llm.invoke(question).content

    ms = (time.perf_counter() - t0) * 1000
    cache.update(question, session, [Generation(text=response_text)])
    return {"response": response_text, "source": "llm",
            "latency_ms": round(ms, 1), "cache_hit": False}


def print_result(label: str, r: dict) -> None:
    icon = "⚡" if r["cache_hit"] else "🌐"
    print(f"  {icon} [{r['source'].upper()}] {r['latency_ms']:.0f}ms — {label}")
    if r["cache_hit"]:
        print(f"       ↳ {r['response'][:80]}")


# ── DEMO 1: Stateless semantic cache — set_llm_cache + llm.invoke() ───────────
def demo_stateless():
    """
    Registers SulciCache globally. Every llm.invoke() call — chains, agents,
    retrievers — checks the cache first with no other code changes.
    """
    print("━" * 58)
    print("Demo 1 — Stateless semantic cache (set_llm_cache)")
    print("━" * 58)

    stateless_cache = ContextAwareSulciCache(
        backend          = "sqlite",
        db_path          = _DB_PATH,
        threshold        = 0.85,
        namespace_by_llm = False,
    )
    set_llm_cache(stateless_cache)

    SESSION = "stateless"

    print("\nRound 1: Fresh questions — all misses")
    print("-" * 50)
    for q in [
        "What is semantic caching?",
        "How does LangChain work?",
        "What is the CAP theorem?",
        "What is a REST API?",
    ]:
        r = _invoke(q, SESSION, stateless_cache)
        print_result(q, r)

    print("\nRound 2: Paraphrased questions — semantic hits")
    print("-" * 50)
    for q in [
        "How does semantic cache work?",       # ≈ q1
        "What is LangChain used for?",         # ≈ q2
        "Explain the CAP theorem",             # ≈ q3
        "What are REST APIs?",                 # ≈ q4
    ]:
        r = _invoke(q, SESSION, stateless_cache)
        print_result(q, r)

    print("\nRound 3: Clearly unrelated — cache miss")
    print("-" * 50)
    r = _invoke("What is the capital of Australia?", SESSION, stateless_cache)
    print_result("What is the capital of Australia?", r)

    print()
    print(f"  hits={stateless_cache._hits}  misses={stateless_cache._misses}"
          f"  hit_rate={stateless_cache.hit_rate:.0%}"
          f"  saved=${stateless_cache._hits * 0.005:.3f}")

    set_llm_cache(None)


# ── DEMO 2: Context-aware cache — session per conversation ────────────────────
def demo_context_aware():
    """
    Uses llm_string as session_id so each conversation gets its own context
    window. Ambiguous follow-up questions resolve correctly within the session.

    Customer support result: 32% → 88% hit rate (+56pp) with context_window=4.
    """
    print()
    print("━" * 58)
    print("Demo 2 — Context-aware cache (context_window=4)")
    print("━" * 58)

    ctx_cache = ContextAwareSulciCache(
        backend          = "sqlite",
        db_path          = _DB_PATH,
        threshold        = 0.85,
        context_window   = 4,
        query_weight     = 0.70,
        namespace_by_llm = False,
    )
    set_llm_cache(ctx_cache)

    history = []

    def ask_ctx(question: str, session: str) -> dict:
        r = _invoke(question, session, ctx_cache)
        history.append((session, question, r))
        return r

    # ── Session A: seed a topic, then ask paraphrases ──────────────────────
    print("\nSession A — seed + paraphrases in same session")
    print("-" * 50)
    SESSION_A = "session-alice-conv-1"

    r = ask_ctx("What is semantic caching?", SESSION_A)
    print_result("[seed] What is semantic caching?", r)

    for q in [
        "How does semantic cache work?",       # paraphrase — should hit
        "What is the decorator pattern in Python?",  # unrelated — miss
    ]:
        r = ask_ctx(q, SESSION_A)
        print_result(q, r)

    # ── Session B: fresh session for a different user ──────────────────────
    print("\nSession B — different user, fresh context")
    print("-" * 50)
    SESSION_B = "session-bob-conv-1"

    r = ask_ctx("What is the CAP theorem?", SESSION_B)
    print_result("[seed] What is the CAP theorem?", r)

    for q in [
        "Explain the CAP theorem",             # paraphrase — should hit
        "Can you give me a simple example?",   # context → CAP theorem
    ]:
        r = ask_ctx(q, SESSION_B)
        print_result(q, r)

    # ── Session A revisited: context still alive ───────────────────────────
    print(f"\nSession A revisited — context window still active")
    print("-" * 50)
    for q in [
        "How is this different from standard caching?",
        "What are the main benefits?",
    ]:
        r = ask_ctx(q, SESSION_A)
        print_result(q, r)

    print()
    print(f"  hits={ctx_cache._hits}  misses={ctx_cache._misses}"
          f"  hit_rate={ctx_cache.hit_rate:.0%}"
          f"  saved=${ctx_cache._hits * 0.005:.3f}")

    print("\n── Conversation history ──────────────────────────────")
    for i, (sid, q, r) in enumerate(history, 1):
        icon = "⚡" if r["cache_hit"] else "🌐"
        tag  = f"[{sid.split('-')[1]}]"
        print(f"{i:2}. {icon} {tag} {r['latency_ms']:.0f}ms — {q}")

    set_llm_cache(None)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("◈ Sulci Cache + LangChain — semantic & context-aware cache demo\n")
    demo_stateless()
    demo_context_aware()


if __name__ == "__main__":
    main()
