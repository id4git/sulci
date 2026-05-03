"""
tests/test_telemetry.py
=======================
Unit tests for sulci.telemetry helpers + the v0.5.2 _flush() wire shape.

D13 coverage:
  - build_fingerprint() is deterministic for fixed inputs
  - build_fingerprint() changes when any config bit changes
  - build_fingerprint() never includes raw machine_id in output
  - python_version_str() returns N.N.N
  - WIRE_FIELDS matches the gateway TelemetryEvent schema (9 fields)
  - coerce_to_wire() strips non-allowlisted fields
  - _flush() includes fingerprint in payload (cache.get)
  - _flush() emits a separate POST for cache.set events
  - _flush() emits BOTH posts when both event types are buffered
  - _flush() drops embedding_model/threshold/context_window from wire payload
    (they live in the buffer for fingerprint computation, not for the wire)
  - _flush() handles startup events without crashing (currently dropped)
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import patch

import sulci
import sulci.telemetry as tel
import sulci.config as cfg


def _reset_module():
    sulci._api_key             = None
    sulci._telemetry_enabled   = False
    sulci._event_buffer        = []
    sulci._flush_thread_started = False


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path


# ── build_fingerprint ─────────────────────────────────────────────────────────

class TestFingerprint:
    def test_deterministic_for_same_inputs(self):
        a = tel.build_fingerprint(
            machine_id="m1", backend="qdrant",
            embedding_model="minilm", threshold=0.85, context_window=4,
        )
        b = tel.build_fingerprint(
            machine_id="m1", backend="qdrant",
            embedding_model="minilm", threshold=0.85, context_window=4,
        )
        assert a == b

    def test_changes_with_machine_id(self):
        a = tel.build_fingerprint(machine_id="m1", backend="qdrant")
        b = tel.build_fingerprint(machine_id="m2", backend="qdrant")
        assert a != b

    def test_changes_with_backend(self):
        a = tel.build_fingerprint(machine_id="m1", backend="qdrant")
        b = tel.build_fingerprint(machine_id="m1", backend="chroma")
        assert a != b

    def test_changes_with_embedding_model(self):
        a = tel.build_fingerprint(machine_id="m1", backend="q", embedding_model="minilm")
        b = tel.build_fingerprint(machine_id="m1", backend="q", embedding_model="openai")
        assert a != b

    def test_changes_with_threshold(self):
        a = tel.build_fingerprint(machine_id="m1", backend="q", threshold=0.85)
        b = tel.build_fingerprint(machine_id="m1", backend="q", threshold=0.65)
        assert a != b

    def test_threshold_within_4dp_is_same(self):
        """Round-tripping floats shouldn't fragment the fingerprint."""
        a = tel.build_fingerprint(machine_id="m1", backend="q", threshold=0.85)
        b = tel.build_fingerprint(machine_id="m1", backend="q", threshold=0.85000001)
        assert a == b

    def test_changes_with_context_window(self):
        a = tel.build_fingerprint(machine_id="m1", backend="q", context_window=0)
        b = tel.build_fingerprint(machine_id="m1", backend="q", context_window=4)
        assert a != b

    def test_no_machine_id_in_output(self):
        """Privacy: the fingerprint must not contain the raw machine_id."""
        machine_id = "deadbeef" * 4
        fp = tel.build_fingerprint(machine_id=machine_id, backend="q")
        assert machine_id not in fp

    def test_returns_24_hex_chars(self):
        fp = tel.build_fingerprint(machine_id="m1", backend="q")
        assert len(fp) == 24
        assert int(fp, 16) >= 0   # must be valid hex

    def test_fits_gateway_64char_cap(self):
        """Defense against accidentally bumping digest_size past gateway max."""
        fp = tel.build_fingerprint(machine_id="m1", backend="qdrant")
        assert len(fp) <= 64   # gateway TelemetryEvent.fingerprint max_length


# ── WIRE_FIELDS / coerce_to_wire ──────────────────────────────────────────────

class TestWireContract:
    def test_wire_fields_matches_gateway_schema(self):
        """If this fails, the gateway schema and SDK have drifted.
        Update both sides in lockstep.
        """
        expected = {
            "event", "backend", "hits", "misses", "avg_latency_ms",
            "sdk_version", "python_version", "fingerprint",
        }
        assert tel.WIRE_FIELDS == expected

    def test_coerce_strips_non_allowlisted(self):
        payload = {
            "event": "cache.get", "backend": "q", "hits": 1, "misses": 0,
            "avg_latency_ms": 1.0, "sdk_version": "0.5.2",
            "python_version": "3.11.0", "fingerprint": "abc",
            "embedding_model": "minilm",   # not on the wire
            "threshold": 0.85,             # not on the wire
            "extra_garbage": "rejected",
        }
        coerced = tel.coerce_to_wire(payload)
        assert "embedding_model" not in coerced
        assert "threshold" not in coerced
        assert "extra_garbage" not in coerced
        assert coerced["event"] == "cache.get"
        assert coerced["fingerprint"] == "abc"

    def test_coerce_keeps_none_values(self):
        """Pydantic Optional[...] fields accept None — don't strip them."""
        payload = {
            "event": "cache.get", "backend": "q", "hits": 0, "misses": 0,
            "avg_latency_ms": 0.0, "sdk_version": "0.5.2",
            "python_version": None, "fingerprint": None,
        }
        coerced = tel.coerce_to_wire(payload)
        assert coerced["python_version"] is None
        assert coerced["fingerprint"] is None


# ── python_version_str ────────────────────────────────────────────────────────

def test_python_version_str_format():
    v = tel.python_version_str()
    parts = v.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


# ── _flush integration ────────────────────────────────────────────────────────

class TestFlushIntegration:
    def setup_method(self):
        _reset_module()

    def test_cache_get_payload_includes_fingerprint(self, tmp_home):
        """v0.5.2: fingerprint is now sent to the gateway."""
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
             "backend": "sqlite", "embedding_model": "minilm", "threshold": 0.85,
             "context_window": 0, "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        assert mock_post.call_count == 1
        payload = mock_post.call_args.kwargs["json"]
        assert "fingerprint" in payload
        assert isinstance(payload["fingerprint"], str)
        assert len(payload["fingerprint"]) == 24

    def test_cache_set_emits_separate_post(self, tmp_home):
        """cache.set events get their own aggregated POST to /v1/telemetry."""
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.set", "latency_ms": 5.0, "backend": "sqlite",
             "embedding_model": "minilm", "threshold": 0.85,
             "context_window": 0, "ts": time.time()},
            {"event": "cache.set", "latency_ms": 7.0, "backend": "sqlite",
             "embedding_model": "minilm", "threshold": 0.85,
             "context_window": 0, "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        assert mock_post.call_count == 1
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event"]          == "cache.set"
        assert payload["hits"]           == 2     # count of sets, per "cache.set semantics"
        assert payload["misses"]         == 0
        assert payload["avg_latency_ms"] == 6.0
        assert "fingerprint"             in payload

    def test_both_event_types_emit_two_posts(self, tmp_home):
        """Mixed buffer → one cache.get POST + one cache.set POST."""
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
             "backend": "sqlite", "embedding_model": "minilm",
             "threshold": 0.85, "context_window": 0, "ts": time.time()},
            {"event": "cache.set", "latency_ms": 5.0, "backend": "sqlite",
             "embedding_model": "minilm", "threshold": 0.85,
             "context_window": 0, "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        assert mock_post.call_count == 2
        events_posted = {call.kwargs["json"]["event"] for call in mock_post.call_args_list}
        assert events_posted == {"cache.get", "cache.set"}

    def test_payloads_only_contain_wire_fields(self, tmp_home):
        """Defense against accidentally leaking SDK-internal keys to the wire.

        The gateway uses extra='forbid' — any unknown key would HTTP-422
        the entire batch. This test fails loudly before that happens.
        """
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
             "backend": "sqlite", "embedding_model": "minilm",
             "threshold": 0.85, "context_window": 0, "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        payload = mock_post.call_args.kwargs["json"]
        assert set(payload.keys()).issubset(tel.WIRE_FIELDS), (
            f"payload contains non-wire keys: "
            f"{set(payload.keys()) - tel.WIRE_FIELDS}"
        )

    def test_same_config_same_fingerprint_across_flushes(self, tmp_home):
        """Two flushes from the same install produce the same fingerprint.

        This is the dashboard-dedup invariant — a deployment that runs
        all day shouldn't appear as N rows on /v1/analytics/deployments.
        """
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True

        def one_flush():
            sulci._event_buffer = [
                {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
                 "backend": "qdrant", "embedding_model": "minilm",
                 "threshold": 0.85, "context_window": 4, "ts": time.time()},
            ]
            with patch("httpx.post") as mock_post:
                sulci._flush()
            return mock_post.call_args.kwargs["json"]["fingerprint"]

        fp1 = one_flush()
        fp2 = one_flush()
        assert fp1 == fp2

    def test_different_backend_different_fingerprint(self, tmp_home):
        """Switching backend on the same machine → distinct deployment row."""
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True

        def flush_with_backend(backend):
            sulci._event_buffer = [
                {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
                 "backend": backend, "embedding_model": "minilm",
                 "threshold": 0.85, "context_window": 0, "ts": time.time()},
            ]
            with patch("httpx.post") as mock_post:
                sulci._flush()
            return mock_post.call_args.kwargs["json"]["fingerprint"]

        fp_q = flush_with_backend("qdrant")
        fp_c = flush_with_backend("chroma")
        assert fp_q != fp_c

    def test_startup_only_buffer_does_not_post(self, tmp_home):
        """Startup events alone don't trigger a POST (legacy gap, see _flush docstring).

        If this test starts failing because we now POST startup events,
        update the test rather than the production code only — verify
        the gateway accepts the new payload first.
        """
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "startup", "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        assert mock_post.call_count == 0


# ── Privacy guarantees ────────────────────────────────────────────────────────

class TestPrivacyInvariants:
    """Tests that codify the ADR 0010 server-side privacy firewall on the
    SDK side. These should never have to change unless the gateway schema
    changes — and then they change in lockstep.
    """

    def setup_method(self):
        _reset_module()

    def test_no_query_text_field_on_wire(self, tmp_home):
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
             "backend": "sqlite", "embedding_model": "minilm",
             "threshold": 0.85, "context_window": 0,
             "query": "secret query text",   # poisoned event
             "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        payload = mock_post.call_args.kwargs["json"]
        assert "query" not in payload

    def test_no_response_field_on_wire(self, tmp_home):
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
             "backend": "sqlite", "embedding_model": "minilm",
             "threshold": 0.85, "context_window": 0,
             "response": "secret response",
             "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        payload = mock_post.call_args.kwargs["json"]
        assert "response" not in payload

    def test_no_embedding_field_on_wire(self, tmp_home):
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0,
             "backend": "sqlite", "embedding_model": "minilm",
             "threshold": 0.85, "context_window": 0,
             "embedding": [0.1, 0.2, 0.3],
             "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        payload = mock_post.call_args.kwargs["json"]
        assert "embedding" not in payload
