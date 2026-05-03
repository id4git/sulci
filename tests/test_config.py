"""
tests/test_config.py
====================
Unit tests for sulci.config — D14 (v0.5.2).

Coverage
--------
- load() returns {} on missing file
- load() returns {} on malformed JSON (silent fallback)
- load() returns {} on non-object JSON (e.g. [1,2,3])
- load() returns parsed dict on valid JSON
- save() creates ~/.sulci/ with 0700 permissions
- save() writes file with 0600 permissions
- save() is atomic (tempfile + rename)
- save() round-trips through load()
- update() merges into existing config
- update() works as first-write (no existing file)
- get_machine_id() generates a uuid on first call, persists it, returns same on second call
- get_machine_id() degrades gracefully when home is unwritable (returns a UUID anyway)
"""
from __future__ import annotations

import json
import os
import stat
import pytest

import sulci.config as cfg


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """Redirect ~ to a tempdir so we never touch the real ~/.sulci."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # On some systems os.path.expanduser also consults USERPROFILE.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path


# ── load() ────────────────────────────────────────────────────────────────────

class TestLoad:
    def test_missing_file_returns_empty_dict(self, tmp_home):
        assert cfg.load() == {}

    def test_malformed_json_returns_empty_dict(self, tmp_home):
        cfg_dir = tmp_home / ".sulci"
        cfg_dir.mkdir()
        (cfg_dir / "config").write_text("{not json")
        assert cfg.load() == {}

    def test_non_object_json_returns_empty_dict(self, tmp_home):
        """A JSON list/string/number should not crash — silent fallback."""
        cfg_dir = tmp_home / ".sulci"
        cfg_dir.mkdir()
        (cfg_dir / "config").write_text("[1, 2, 3]")
        assert cfg.load() == {}

    def test_valid_object_returns_parsed_dict(self, tmp_home):
        cfg_dir = tmp_home / ".sulci"
        cfg_dir.mkdir()
        (cfg_dir / "config").write_text(json.dumps({"api_key": "sk-x", "machine_id": "abc"}))
        loaded = cfg.load()
        assert loaded == {"api_key": "sk-x", "machine_id": "abc"}

    def test_unreadable_file_returns_empty_dict(self, tmp_home):
        """Permission errors must not propagate."""
        cfg_dir = tmp_home / ".sulci"
        cfg_dir.mkdir()
        f = cfg_dir / "config"
        f.write_text(json.dumps({"x": 1}))
        os.chmod(f, 0)
        try:
            # Root in CI containers can read regardless of mode.
            # Skip the assertion in that case rather than fake a result.
            if os.geteuid() == 0:
                pytest.skip("Cannot test unreadable file as root")
            assert cfg.load() == {}
        finally:
            os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)


# ── save() ────────────────────────────────────────────────────────────────────

class TestSave:
    def test_creates_directory(self, tmp_home):
        assert cfg.save({"api_key": "sk-test"}) is True
        assert (tmp_home / ".sulci").is_dir()

    def test_directory_mode_is_0700(self, tmp_home):
        cfg.save({"api_key": "sk-test"})
        mode = stat.S_IMODE((tmp_home / ".sulci").stat().st_mode)
        assert mode == 0o700, f"expected 0o700, got {oct(mode)}"

    def test_file_mode_is_0600(self, tmp_home):
        cfg.save({"api_key": "sk-test"})
        mode = stat.S_IMODE((tmp_home / ".sulci" / "config").stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    def test_round_trips_through_load(self, tmp_home):
        original = {"api_key": "sk-roundtrip", "machine_id": "x" * 32}
        cfg.save(original)
        assert cfg.load() == original

    def test_overwrites_existing_file(self, tmp_home):
        cfg.save({"a": 1})
        cfg.save({"b": 2})
        assert cfg.load() == {"b": 2}

    def test_no_tempfile_left_behind(self, tmp_home):
        cfg.save({"x": 1})
        tmps = list((tmp_home / ".sulci").glob("*.tmp"))
        assert tmps == []


# ── update() ──────────────────────────────────────────────────────────────────

class TestUpdate:
    def test_merges_into_existing_config(self, tmp_home):
        cfg.save({"api_key": "sk-x"})
        cfg.update(machine_id="abc123")
        loaded = cfg.load()
        assert loaded == {"api_key": "sk-x", "machine_id": "abc123"}

    def test_update_overwrites_existing_field(self, tmp_home):
        cfg.save({"api_key": "old"})
        cfg.update(api_key="new")
        assert cfg.load()["api_key"] == "new"

    def test_update_works_as_first_write(self, tmp_home):
        # No existing file
        cfg.update(machine_id="firstwrite")
        assert cfg.load() == {"machine_id": "firstwrite"}

    def test_update_treats_corrupt_file_as_empty(self, tmp_home):
        """A corrupt file should not block an update — treated as {}."""
        cfg_dir = tmp_home / ".sulci"
        cfg_dir.mkdir()
        (cfg_dir / "config").write_text("garbage")
        cfg.update(machine_id="recovery")
        assert cfg.load() == {"machine_id": "recovery"}


# ── get_machine_id() ──────────────────────────────────────────────────────────

class TestGetMachineId:
    def test_generates_on_first_call(self, tmp_home):
        mid = cfg.get_machine_id()
        assert isinstance(mid, str)
        assert len(mid) == 32   # uuid4().hex
        assert int(mid, 16) >= 0   # must be valid hex

    def test_persists_across_calls(self, tmp_home):
        mid1 = cfg.get_machine_id()
        mid2 = cfg.get_machine_id()
        assert mid1 == mid2

    def test_persists_across_module_reloads(self, tmp_home):
        """Re-importing the module must not regenerate the id."""
        import importlib, sulci.config as c
        mid1 = c.get_machine_id()
        importlib.reload(c)
        mid2 = c.get_machine_id()
        assert mid1 == mid2

    def test_returns_uuid_even_on_unwritable_home(self, tmp_home, monkeypatch):
        """If save fails, we still return a (process-local) UUID — degraded but functional."""
        monkeypatch.setattr(cfg, "save", lambda *a, **kw: False)
        mid = cfg.get_machine_id()
        assert isinstance(mid, str)
        assert len(mid) == 32

    def test_existing_machine_id_is_preserved(self, tmp_home):
        """If config already has a machine_id, return it verbatim."""
        cfg.save({"machine_id": "preexisting"})
        assert cfg.get_machine_id() == "preexisting"
