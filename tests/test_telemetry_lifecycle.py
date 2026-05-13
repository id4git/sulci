"""
Lifecycle tests for the telemetry pipe (v0.6.4+).

Pre-v0.6.4, the flush thread was a daemon with NO atexit hook, so
short-lived processes (demo scripts, CLI invocations, serverless,
test runs) silently lost every event buffered since the last 30s
flush tick. v0.6.4 added `atexit.register(_flush_on_exit)` inside
`_start_flush_thread()` to drain the buffer on process exit.

These tests pin that invariant. If a future PR removes the atexit
hook, changes the flush thread to non-daemon (which would block
process exit), or breaks the "never raise" contract on exit, these
tests fail loudly.
"""
from __future__ import annotations

import atexit
from unittest import mock

import pytest

import sulci


@pytest.fixture(autouse=True)
def reset_telemetry_state():
    """Reset module-level state so tests don\'t pollute each other."""
    yield
    sulci._api_key = None
    sulci._telemetry_enabled = False
    sulci._event_buffer.clear()
    sulci._flush_thread_started = False


class TestAtexitFlush:
    """v0.6.4 regression: short-lived processes must drain buffer on exit."""

    def test_flush_on_exit_drains_buffer(self, monkeypatch):
        """The headline guarantee — a script that exits before the 30s
        flush tick still gets its events to the gateway."""
        posts = []

        def fake_post(url, json=None, **kwargs):
            posts.append({"url": url, "body": json})
            response = mock.MagicMock()
            response.status_code = 200
            response.raise_for_status = mock.MagicMock()
            return response

        monkeypatch.setattr("httpx.post", fake_post)

        sulci.connect(api_key="sk-sulci-test-key", telemetry=True)
        sulci._emit(
            event="cache.get",
            data={"backend": "sqlite", "hit": True, "latency_ms": 0.5},
        )

        # Buffer has the event (plus the \'startup\' event from connect()),
        # no POST yet (would have happened on the 30s tick).
        assert len(sulci._event_buffer) >= 1
        assert posts == [], "no POST should have happened before exit"

        # Simulate process exit
        atexit._run_exitfuncs()

        assert len(posts) >= 1, (
            "v0.6.4 regression: telemetry buffer not drained at process exit. "
            "Was atexit.register(_flush_on_exit) removed from _start_flush_thread()? "
            "Was the daemon flush thread changed to non-daemon (which would "
            "block process exit instead)?"
        )
        assert "/v1/telemetry" in posts[0]["url"]

    def test_flush_on_exit_never_raises(self, monkeypatch):
        """The flush-on-exit hook must preserve the "telemetry never
        raises" contract even when the gateway returns an error."""
        def explosive_post(*args, **kwargs):
            raise RuntimeError("simulated gateway failure")

        monkeypatch.setattr("httpx.post", explosive_post)

        sulci.connect(api_key="sk-sulci-test-key", telemetry=True)
        sulci._emit(
            event="cache.get",
            data={"backend": "sqlite", "hit": True, "latency_ms": 0.5},
        )

        try:
            atexit._run_exitfuncs()
        except RuntimeError:
            pytest.fail(
                "flush-on-exit must not propagate exceptions — the "
                "\'telemetry never raises\' contract was violated."
            )

    def test_flush_on_exit_no_op_when_telemetry_disabled(self, monkeypatch):
        """If telemetry was disabled (or never enabled), the hook
        should make no HTTP calls."""
        posts = []

        def fake_post(url, json=None, **kwargs):
            posts.append({"url": url})
            return mock.MagicMock(status_code=200, raise_for_status=mock.MagicMock())

        monkeypatch.setattr("httpx.post", fake_post)

        sulci._flush_on_exit()  # without connect()

        assert posts == [], (
            "flush-on-exit must be a no-op when telemetry is disabled "
            "(prevents stray POSTs from libraries that don\'t opt in)"
        )

    def test_flush_thread_is_daemon(self):
        """The flush thread must stay daemon — non-daemon threads
        block process exit, which would create a different bug:
        scripts hanging for 30s on exit instead of losing telemetry."""
        import threading
        sulci.connect(api_key="sk-sulci-test-key", telemetry=True)

        flush_threads = [t for t in threading.enumerate()
                         if t.name == "sulci-telemetry-flush"]
        assert flush_threads, "flush thread should be running after connect()"
        assert all(t.daemon for t in flush_threads), (
            "flush thread must be daemon — non-daemon would block process "
            "exit indefinitely, replacing the v0.6.4 \'lost events\' bug "
            "with a \'hung process\' bug."
        )
