"""
tests/test_connect.py
=====================
Unit tests for sulci.connect() — Step 4 (Week 2).

Coverage
--------
- _telemetry_enabled is False by default (most important invariant)
- connect() enables telemetry only when api_key is present
- connect(telemetry=False) registers key without enabling telemetry
- connect() resolves key from SULCI_API_KEY env var
- connect() with no key and no env var does not enable telemetry
- connect() does not start flush thread without a key
- connect() called twice does not start a second flush thread
- connect() emits startup event on successful connect
- connect() does not emit startup when telemetry=False
- _emit() is a no-op when telemetry is disabled
- _emit() is a no-op when api_key is None even if flag is True
- _emit() buffers events when telemetry is enabled
- _emit() never raises — telemetry must never crash the caller
- _flush() drains the buffer and sends one aggregated HTTP call
- _flush() sends correct X-Sulci-Key auth header
- _flush() uses 3s timeout
- _flush() swallows httpx.TimeoutException — never raises
- _flush() swallows generic exceptions — never raises
- _flush() is a no-op on empty buffer
- 50 concurrent threads emitting — no events lost (thread safety)
- Cache(telemetry=False) stores the flag correctly
- Cache telemetry=True by default
- Cache.get() does not emit when telemetry=False
- Cache.get() emits when telemetry=True and connect() called
"""

import os
import threading
import time
import pytest
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_module():
    """Reset all module-level telemetry state between tests."""
    import sulci
    sulci._api_key             = None
    sulci._telemetry_enabled   = False
    sulci._event_buffer        = []
    sulci._flush_thread_started = False

# ══════════════════════════════════════════════════════════════════════════════
# Default state
# ══════════════════════════════════════════════════════════════════════════════

class TestDefaultState:
    def setup_method(self):
        _reset_module()

    def test_telemetry_disabled_by_default(self):
        """Most critical invariant — nothing phones home without connect()."""
        import sulci
        assert sulci._telemetry_enabled is False

    def test_api_key_none_by_default(self):
        import sulci
        assert sulci._api_key is None

    def test_event_buffer_empty_by_default(self):
        import sulci
        assert sulci._event_buffer == []

    def test_emit_is_noop_by_default(self):
        """_emit() must not modify buffer when telemetry is off."""
        import sulci
        sulci._emit("cache.get", {"hits": 1, "misses": 0})
        assert sulci._event_buffer == []


# ══════════════════════════════════════════════════════════════════════════════
# connect()
# ══════════════════════════════════════════════════════════════════════════════

class TestConnect:
    def setup_method(self):
        _reset_module()

    def test_connect_enables_telemetry_with_key(self):
        """connect() with a valid key sets api_key and enables telemetry."""
        import sulci
        with patch("sulci._start_flush_thread"), patch("sulci._emit"):
            sulci.connect(api_key="sk-sulci-test123")
        assert sulci._telemetry_enabled is True
        assert sulci._api_key == "sk-sulci-test123"

    def test_connect_without_key_does_not_enable_telemetry(self):
        """connect(prompt=False) with no key, no env var, no config file
        leaves telemetry disabled — the explicit opt-out path for
        CI/headless environments. As of v0.6.0, the default behavior of
        ``sulci.connect()`` with no inputs is to invoke the browser-based
        device-code flow, so this test passes prompt=False to assert the
        no-flow path. See sulci.oss_connect for the device-code path and
        the TestDeviceCodeFlow class below for its tests.

        We also patch ``_read_key_from_config`` to return None so a real
        ``~/.sulci/config`` on the developer's machine doesn't leak into
        the test and silently provide a key from step 3 of the resolution
        chain."""
        import sulci
        with patch.dict(os.environ, {}, clear=True), \
             patch("sulci._read_key_from_config", return_value=None):
            os.environ.pop("SULCI_API_KEY", None)
            sulci.connect(prompt=False)
        assert sulci._telemetry_enabled is False
        assert sulci._api_key is None

    def test_connect_telemetry_false_sets_key_but_not_telemetry(self):
        """
        connect(telemetry=False) stores the key but leaves telemetry disabled.
        Thread must not be started.
        """
        import sulci
        with patch("sulci._start_flush_thread") as mock_thread, \
             patch("sulci._emit"):
            sulci.connect(api_key="sk-sulci-test123", telemetry=False)
        assert sulci._api_key           == "sk-sulci-test123"
        assert sulci._telemetry_enabled is False
        mock_thread.assert_not_called()

    def test_connect_reads_key_from_env(self):
        """connect() with no explicit key falls back to SULCI_API_KEY env var."""
        import sulci
        with patch.dict(os.environ, {"SULCI_API_KEY": "sk-sulci-fromenv"}), \
             patch("sulci._start_flush_thread"), patch("sulci._emit"):
            sulci.connect()
        assert sulci._api_key           == "sk-sulci-fromenv"
        assert sulci._telemetry_enabled is True

    def test_connect_explicit_key_takes_precedence_over_env(self):
        """Explicit api_key argument overrides SULCI_API_KEY env var."""
        import sulci
        with patch.dict(os.environ, {"SULCI_API_KEY": "sk-sulci-fromenv"}), \
             patch("sulci._start_flush_thread"), patch("sulci._emit"):
            sulci.connect(api_key="sk-sulci-explicit")
        assert sulci._api_key == "sk-sulci-explicit"

    def test_connect_starts_flush_thread(self):
        """connect() with a valid key starts the background flush thread."""
        import sulci
        with patch("sulci._start_flush_thread") as mock_thread, \
             patch("sulci._emit"):
            sulci.connect(api_key="sk-sulci-test123")
        mock_thread.assert_called_once()

    def test_connect_does_not_start_thread_without_key(self):
        """connect(prompt=False) without a key must NOT start the flush
        thread. As of v0.6.0 the default behavior is to invoke the
        device-code flow when no key is found; prompt=False is the
        explicit opt-out for tests / CI / headless callers that want
        connect() to be a no-op when there's no key. Also patch
        ``_read_key_from_config`` so a stale ~/.sulci/config doesn't
        leak in (same defense as
        test_connect_without_key_does_not_enable_telemetry above)."""
        import sulci
        with patch("sulci._start_flush_thread") as mock_thread, \
             patch("sulci._read_key_from_config", return_value=None), \
             patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SULCI_API_KEY", None)
            sulci.connect(api_key=None, prompt=False)
        mock_thread.assert_not_called()

    def test_connect_emits_startup_event(self):
        """connect() emits a startup telemetry event when key is present."""
        import sulci
        with patch("sulci._start_flush_thread"), \
             patch("sulci._emit") as mock_emit:
            sulci.connect(api_key="sk-sulci-test123")
        mock_emit.assert_called_once_with("startup", {})

    def test_connect_does_not_emit_startup_when_telemetry_false(self):
        """connect(telemetry=False) must not emit any events."""
        import sulci
        with patch("sulci._emit") as mock_emit:
            sulci.connect(api_key="sk-sulci-test123", telemetry=False)
        mock_emit.assert_not_called()

    def test_connect_twice_starts_flush_thread_only_once(self):
        """
        Calling connect() twice must not create two flush threads.
        _flush_thread_started flag prevents duplicates.
        """
        import sulci
        with patch("sulci._emit"), \
             patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            sulci.connect(api_key="sk-sulci-test123")
            sulci.connect(api_key="sk-sulci-test123")
        assert mock_thread_cls.call_count == 1


# ══════════════════════════════════════════════════════════════════════════════
# _emit()
# ══════════════════════════════════════════════════════════════════════════════

class TestEmit:
    def setup_method(self):
        _reset_module()

    def test_emit_buffers_event_when_enabled(self):
        """_emit() appends an event to _event_buffer when telemetry is on."""
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._emit("cache.get", {"hits": 1, "misses": 0, "backend": "sqlite"})
        assert len(sulci._event_buffer) == 1
        assert sulci._event_buffer[0]["event"] == "cache.get"
        assert sulci._event_buffer[0]["hits"]  == 1

    def test_emit_noop_when_disabled(self):
        """_emit() is a no-op when _telemetry_enabled is False."""
        import sulci
        sulci._telemetry_enabled = False
        sulci._emit("cache.get", {"hits": 1})
        assert sulci._event_buffer == []

    def test_emit_noop_when_no_key(self):
        """
        _emit() is a no-op when _api_key is None even if flag is True.
        Guards against state where flag was set but key was later cleared.
        """
        import sulci
        sulci._telemetry_enabled = True
        sulci._api_key           = None
        sulci._emit("cache.get", {"hits": 1})
        assert sulci._event_buffer == []

    def test_emit_multiple_events_appends(self):
        """Multiple _emit() calls all land in the buffer."""
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        for i in range(5):
            sulci._emit("cache.get", {"hits": 1, "misses": 0})
        assert len(sulci._event_buffer) == 5

    def test_emit_includes_timestamp(self):
        """Every buffered event includes a ts unix timestamp."""
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        before = time.time()
        sulci._emit("cache.get", {"hits": 1})
        after  = time.time()
        ts = sulci._event_buffer[0]["ts"]
        assert before <= ts <= after

    def test_emit_never_raises_on_exception(self):
        """
        _emit() must silently swallow all exceptions.
        Telemetry must never crash the user's application.
        """
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        with patch.object(sulci, "_event_buffer", side_effect=Exception("buffer error")):
            try:
                sulci._emit("cache.get", {"hits": 1})
            except Exception:
                pytest.fail("_emit() raised — it must never raise")


# ══════════════════════════════════════════════════════════════════════════════
# _flush()
# ══════════════════════════════════════════════════════════════════════════════

class TestFlush:
    def setup_method(self):
        _reset_module()

    def test_flush_noop_on_empty_buffer(self):
        """_flush() on an empty buffer must not call httpx.post."""
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        with patch("httpx.post") as mock_post:
            sulci._flush()
        mock_post.assert_not_called()

    def test_flush_sends_aggregated_payload(self):
        """
        _flush() aggregates buffered events into a single HTTP POST.
        hits and misses are summed; latency is averaged.
        """
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 10.0, "backend": "sqlite", "ts": time.time()},
            {"event": "cache.get", "hits": 1, "misses": 0, "latency_ms": 20.0, "backend": "sqlite", "ts": time.time()},
            {"event": "cache.get", "hits": 0, "misses": 1, "latency_ms":  5.0, "backend": "sqlite", "ts": time.time()},
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["hits"]            == 2
        assert payload["misses"]          == 1
        assert payload["avg_latency_ms"]  == round((10 + 20 + 5) / 3, 2)
        assert payload["backend"]         == "sqlite"
        assert payload["sdk_version"]     == sulci._SDK_VERSION
        assert "python_version"           in payload

    def test_flush_sends_correct_auth_header(self):
        """_flush() sends X-Sulci-Key header with the module api_key."""
        import sulci
        sulci._api_key           = "sk-sulci-mykey"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0,
             "backend": "sqlite", "ts": time.time()}
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Sulci-Key"] == "sk-sulci-mykey"

    def test_flush_drains_buffer(self):
        """Buffer is empty after a successful flush."""
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0,
             "backend": "sqlite", "ts": time.time()}
        ]
        with patch("httpx.post"):
            sulci._flush()
        assert sulci._event_buffer == []

    def test_flush_swallows_http_exception(self):
        """httpx.TimeoutException during flush must not propagate."""
        import sulci, httpx
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0,
             "backend": "sqlite", "ts": time.time()}
        ]
        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            sulci._flush()   # must not raise

    def test_flush_swallows_generic_exception(self):
        """Any exception during flush must not propagate."""
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0,
             "backend": "sqlite", "ts": time.time()}
        ]
        with patch("httpx.post", side_effect=RuntimeError("network down")):
            sulci._flush()   # must not raise

    def test_flush_uses_3s_timeout(self):
        """_flush() passes timeout=3.0 to httpx.post — never blocks indefinitely."""
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True
        sulci._event_buffer = [
            {"event": "cache.get", "hits": 1, "misses": 0,
             "backend": "sqlite", "ts": time.time()}
        ]
        with patch("httpx.post") as mock_post:
            sulci._flush()
        assert mock_post.call_args.kwargs["timeout"] == 3.0


# ══════════════════════════════════════════════════════════════════════════════
# Cache integration - TBD uncomment after week 2 step 6 completed
# ══════════════════════════════════════════════════════════════════════════════

class TestCacheIntegration:
    def setup_method(self):
        _reset_module()

    def test_cache_constructor_accepts_telemetry_false(self):
        """Cache(telemetry=False) stores the flag without error."""
        import sulci
        cache = sulci.Cache(backend="sqlite", telemetry=False)
        assert cache._telemetry is False

    def test_cache_constructor_telemetry_true_by_default(self):
        """Cache telemetry defaults to True at the instance level."""
        import sulci
        cache = sulci.Cache(backend="sqlite")
        assert cache._telemetry is True

    def test_cache_get_does_not_emit_when_telemetry_false(self):
        """
        Cache(telemetry=False).get() must not call _emit()
        even if sulci.connect() has been called.
        """
        import sulci
        with patch("sulci._start_flush_thread"):
            sulci.connect(api_key="sk-sulci-test123")
        cache = sulci.Cache(backend="sqlite", telemetry=False)
        with patch.object(sulci, "_emit") as mock_emit:
            cache.get("test query")
        mock_emit.assert_not_called()

    def test_cache_get_emits_when_telemetry_enabled(self):
        """
        Cache.get() calls _emit() with cache.get event when
        telemetry is True and sulci.connect() has been called.
        """
        import sulci
        with patch("sulci._start_flush_thread"):
            sulci.connect(api_key="sk-sulci-test123")
        cache = sulci.Cache(backend="sqlite", telemetry=True)
        cache.set("what is semantic caching", "it caches by meaning")
        with patch.object(sulci, "_emit") as mock_emit:
            cache.get("what is semantic caching")
        mock_emit.assert_called_once()
        event, data = mock_emit.call_args[0]
        assert event       == "cache.get"
        assert "hits"      in data
        assert "misses"    in data
        assert "latency_ms" in data


# ══════════════════════════════════════════════════════════════════════════════
# Thread safety
# ══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def setup_method(self):
        _reset_module()

    def test_concurrent_emits_do_not_lose_events(self):
        """
        50 threads each emit 10 events = 500 total.
        All must be in the buffer — no lost writes under contention.
        """
        import sulci
        sulci._api_key           = "sk-sulci-test"
        sulci._telemetry_enabled = True

        def emit_batch():
            for _ in range(10):
                sulci._emit("cache.get", {"hits": 1, "misses": 0, "backend": "sqlite"})

        threads = [threading.Thread(target=emit_batch) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert len(sulci._event_buffer) == 500


# ══════════════════════════════════════════════════════════════════════════════
# Device-code flow integration with connect() — D12 / v0.6.0
# ══════════════════════════════════════════════════════════════════════════════

class TestDeviceCodeFlow:
    """Tests for connect()'s wiring to the OSS-Connect device-code flow.
    Internals of the flow itself are covered in test_oss_connect.py;
    these tests verify the resolution chain and persistence integration
    inside connect()."""

    def setup_method(self):
        _reset_module()

    def test_no_key_anywhere_invokes_device_code_flow(self):
        """connect(prompt=True) with no api_key, no SULCI_API_KEY, no config →
        invokes run_device_code_flow and uses its result.

        Note: prompt=True must be explicit in v0.5.3 (the default is False
        for safety while OSS-Connect's gateway+dashboard chain ships).
        v0.6.0 will flip the default to True.
        """
        import sulci
        with patch.dict(os.environ, {}, clear=True), \
             patch("sulci._read_key_from_config", return_value=None), \
             patch("sulci.oss_connect.run_device_code_flow",
                   return_value="sk-sulci-from-flow") as mock_flow, \
             patch("sulci._persist_key_to_config") as mock_persist, \
             patch("sulci._start_flush_thread"), \
             patch("sulci._emit"):
            os.environ.pop("SULCI_API_KEY", None)
            sulci.connect(prompt=True)

        mock_flow.assert_called_once()
        # The key from the flow becomes the active api_key.
        assert sulci._api_key == "sk-sulci-from-flow"
        # And telemetry is enabled (key was resolved + telemetry=True).
        assert sulci._telemetry_enabled is True
        # And the key got persisted for next-time short-circuit.
        mock_persist.assert_called_once_with("sk-sulci-from-flow")

    def test_config_short_circuits_before_flow(self):
        """connect() with no api_key, no env var, BUT a key in config →
        uses the config key and does NOT invoke the device-code flow."""
        import sulci
        with patch.dict(os.environ, {}, clear=True), \
             patch("sulci._read_key_from_config",
                   return_value="sk-sulci-from-config"), \
             patch("sulci.oss_connect.run_device_code_flow") as mock_flow, \
             patch("sulci._start_flush_thread"), \
             patch("sulci._emit"):
            os.environ.pop("SULCI_API_KEY", None)
            sulci.connect()

        # Flow was NOT called — config short-circuit hit first.
        mock_flow.assert_not_called()
        assert sulci._api_key == "sk-sulci-from-config"

    def test_env_var_short_circuits_before_config_and_flow(self):
        """SULCI_API_KEY beats config beats device-code flow. Verify the
        full resolution order by setting BOTH env and config — env wins."""
        import sulci
        with patch.dict(os.environ, {"SULCI_API_KEY": "sk-sulci-env-wins"}), \
             patch("sulci._read_key_from_config",
                   return_value="sk-sulci-from-config") as mock_config, \
             patch("sulci.oss_connect.run_device_code_flow") as mock_flow, \
             patch("sulci._start_flush_thread"), \
             patch("sulci._emit"):
            sulci.connect()

        # Env var wins — config never read, flow never invoked.
        mock_config.assert_not_called()
        mock_flow.assert_not_called()
        assert sulci._api_key == "sk-sulci-env-wins"

    def test_explicit_arg_beats_everything(self):
        """An explicit api_key= argument takes priority even over env vars
        and config — the existing v0.5.x contract."""
        import sulci
        with patch.dict(os.environ, {"SULCI_API_KEY": "sk-sulci-env"}), \
             patch("sulci._read_key_from_config",
                   return_value="sk-sulci-config") as mock_config, \
             patch("sulci.oss_connect.run_device_code_flow") as mock_flow, \
             patch("sulci._start_flush_thread"), \
             patch("sulci._emit"):
            sulci.connect(api_key="sk-sulci-explicit")

        mock_config.assert_not_called()
        mock_flow.assert_not_called()
        assert sulci._api_key == "sk-sulci-explicit"

    def test_prompt_false_skips_flow_when_no_key(self):
        """The CI/headless escape hatch: prompt=False and no key
        anywhere → connect() is a no-op, no network call attempted."""
        import sulci
        with patch.dict(os.environ, {}, clear=True), \
             patch("sulci._read_key_from_config", return_value=None), \
             patch("sulci.oss_connect.run_device_code_flow") as mock_flow:
            os.environ.pop("SULCI_API_KEY", None)
            sulci.connect(prompt=False)

        mock_flow.assert_not_called()
        assert sulci._api_key is None
        assert sulci._telemetry_enabled is False

    def test_prompt_false_still_uses_config_if_present(self):
        """prompt=False is about the *device-code flow*, not config.
        If a config-persisted key exists, it should still be used."""
        import sulci
        with patch.dict(os.environ, {}, clear=True), \
             patch("sulci._read_key_from_config",
                   return_value="sk-sulci-cached"), \
             patch("sulci.oss_connect.run_device_code_flow") as mock_flow, \
             patch("sulci._start_flush_thread"), \
             patch("sulci._emit"):
            os.environ.pop("SULCI_API_KEY", None)
            sulci.connect(prompt=False)

        mock_flow.assert_not_called()
        assert sulci._api_key == "sk-sulci-cached"
        assert sulci._telemetry_enabled is True

    def test_flow_failure_propagates_runtimerror(self):
        """When the user denies / the code expires / network fails,
        run_device_code_flow raises RuntimeError. That exception
        propagates to the caller — passing prompt=False is the only
        way to suppress."""
        import sulci
        with patch.dict(os.environ, {}, clear=True), \
             patch("sulci._read_key_from_config", return_value=None), \
             patch("sulci.oss_connect.run_device_code_flow",
                   side_effect=RuntimeError("sulci.connect() failed: access_denied")):
            os.environ.pop("SULCI_API_KEY", None)
            with pytest.raises(RuntimeError, match="access_denied"):
                sulci.connect(prompt=True)
        # State stays clean — no half-configured connection.
        assert sulci._api_key is None
        assert sulci._telemetry_enabled is False

    def test_persist_failure_does_not_break_connect(self):
        """If config.update fails for any reason (disk full, permission
        denied), connect() should still complete successfully — the
        only consequence is that the next invocation prompts again."""
        import sulci
        with patch.dict(os.environ, {}, clear=True), \
             patch("sulci._read_key_from_config", return_value=None), \
             patch("sulci.oss_connect.run_device_code_flow",
                   return_value="sk-sulci-from-flow"), \
             patch("sulci.config.update",
                   side_effect=OSError("disk full")), \
             patch("sulci._start_flush_thread"), \
             patch("sulci._emit"):
            os.environ.pop("SULCI_API_KEY", None)
            # Should NOT raise.
            sulci.connect(prompt=True)

        assert sulci._api_key == "sk-sulci-from-flow"
        assert sulci._telemetry_enabled is True
