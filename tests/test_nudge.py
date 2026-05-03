"""
tests/test_nudge.py
===================
Unit tests for the v0.5.2 passive nudge (D15).

The nudge is a one-line stderr message printed once per process when:
  - This Cache instance has observed >= 100 raw .get() calls
  - The user has not called sulci.connect() (telemetry is disabled)
  - SULCI_QUIET=1 is not in the environment
  - The nudge has not already been shown in this process

Coverage
--------
- Below threshold: no output
- At threshold: output once
- Already-shown: subsequent stats() calls are silent
- SULCI_QUIET=1: suppression
- telemetry_enabled=True: suppression (already connected)
- Output is a single newline-terminated stderr line
- stats() return value is unaffected by nudge
"""
from __future__ import annotations

import sys
import pytest
from unittest.mock import patch, MagicMock

import sulci
import sulci.core as core


def _reset():
    core._NUDGE_SHOWN = False
    sulci._telemetry_enabled = False


def _fake_cache(query_count=0):
    """Construct a minimal object that mimics a Cache for nudge testing.

    We don't instantiate real Cache because it would load embedders.
    The nudge logic only touches: self._query_count, self._stats,
    self._sessions. Everything else is irrelevant.
    """
    c = MagicMock(spec=core.Cache)
    c._query_count = query_count
    c._stats       = {"hits": 0, "misses": 0, "saved_cost": 0.0}
    c._sessions    = None
    # Bind the real methods to our fake so they actually execute
    c.stats        = core.Cache.stats.__get__(c, core.Cache)
    c._maybe_nudge = core.Cache._maybe_nudge.__get__(c, core.Cache)
    return c


# ── Threshold behaviour ───────────────────────────────────────────────────────

class TestThreshold:
    def setup_method(self):
        _reset()

    def test_below_threshold_no_output(self, capsys, monkeypatch):
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c = _fake_cache(query_count=99)
        c.stats()
        captured = capsys.readouterr()
        assert "[sulci]" not in captured.err

    def test_at_threshold_emits_nudge(self, capsys, monkeypatch):
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c = _fake_cache(query_count=100)
        c.stats()
        captured = capsys.readouterr()
        assert "[sulci]" in captured.err
        assert "sulci.io" in captured.err

    def test_above_threshold_emits_nudge(self, capsys, monkeypatch):
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c = _fake_cache(query_count=500)
        c.stats()
        captured = capsys.readouterr()
        assert "[sulci]" in captured.err

    def test_nudge_is_one_line(self, capsys, monkeypatch):
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c = _fake_cache(query_count=100)
        c.stats()
        captured = capsys.readouterr()
        # One newline-terminated line
        assert captured.err.count("\n") == 1


# ── One-shot semantics ────────────────────────────────────────────────────────

class TestOneShot:
    def setup_method(self):
        _reset()

    def test_only_emits_once_per_process(self, capsys, monkeypatch):
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c = _fake_cache(query_count=150)
        c.stats()
        c.stats()
        c.stats()
        captured = capsys.readouterr()
        assert captured.err.count("[sulci]") == 1

    def test_module_flag_blocks_other_instances(self, capsys, monkeypatch):
        """A second Cache instance should not re-trigger the nudge."""
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c1 = _fake_cache(query_count=100)
        c2 = _fake_cache(query_count=100)
        c1.stats()
        c2.stats()
        captured = capsys.readouterr()
        assert captured.err.count("[sulci]") == 1


# ── Suppression ───────────────────────────────────────────────────────────────

class TestSuppression:
    def setup_method(self):
        _reset()

    def test_sulci_quiet_suppresses(self, capsys, monkeypatch):
        monkeypatch.setenv("SULCI_QUIET", "1")
        c = _fake_cache(query_count=200)
        c.stats()
        captured = capsys.readouterr()
        assert "[sulci]" not in captured.err

    def test_quiet_suppresses_but_does_not_burn_one_shot(self, capsys, monkeypatch):
        """If SULCI_QUIET=1 is later unset, the nudge can still fire.

        i.e. quiet is a runtime gate, not a permanent decision. Important
        because users might toggle it after seeing it once accidentally.
        """
        monkeypatch.setenv("SULCI_QUIET", "1")
        c = _fake_cache(query_count=200)
        c.stats()
        # Now unset and try again
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c2 = _fake_cache(query_count=200)
        c2.stats()
        captured = capsys.readouterr()
        assert captured.err.count("[sulci]") == 1

    def test_telemetry_enabled_suppresses(self, capsys, monkeypatch):
        """Already connected? No nudge — they took the action."""
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        sulci._telemetry_enabled = True
        c = _fake_cache(query_count=200)
        c.stats()
        captured = capsys.readouterr()
        assert "[sulci]" not in captured.err

    def test_telemetry_check_burns_one_shot(self, capsys, monkeypatch):
        """If telemetry is enabled when threshold first hit, we burn the
        one-shot flag — disconnecting telemetry later should NOT cause
        the nudge to suddenly appear.
        """
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        sulci._telemetry_enabled = True
        c = _fake_cache(query_count=200)
        c.stats()   # connected — silently suppressed
        sulci._telemetry_enabled = False
        c2 = _fake_cache(query_count=200)
        c2.stats()  # now disconnected — but one-shot was burned
        captured = capsys.readouterr()
        assert "[sulci]" not in captured.err


# ── stats() return value untouched ────────────────────────────────────────────

class TestStatsReturnValue:
    def setup_method(self):
        _reset()

    def test_stats_returns_normal_dict_when_nudge_fires(self, monkeypatch):
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c = _fake_cache(query_count=100)
        result = c.stats()
        assert isinstance(result, dict)
        assert "hits"   in result
        assert "misses" in result
        assert "total_queries" in result
        assert "hit_rate"      in result

    def test_stats_returns_normal_dict_when_nudge_suppressed(self, monkeypatch):
        monkeypatch.setenv("SULCI_QUIET", "1")
        c = _fake_cache(query_count=100)
        result = c.stats()
        assert isinstance(result, dict)
        assert "hits"   in result
        assert "misses" in result

    def test_nudge_failure_does_not_break_stats(self, capsys, monkeypatch):
        """If _maybe_nudge raises (it shouldn't, but defense in depth),
        stats() still returns a valid dict."""
        monkeypatch.delenv("SULCI_QUIET", raising=False)
        c = _fake_cache(query_count=100)
        with patch.object(c, "_maybe_nudge", side_effect=RuntimeError("boom")):
            result = c.stats()
        assert isinstance(result, dict)
        assert "total_queries" in result
