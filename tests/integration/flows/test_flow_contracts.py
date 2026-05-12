"""Pytest discovery wrapper for the flow contract scripts.

Each flow_*.py is a standalone runnable that exits 0 on PASS and 1 on
FAIL. This wrapper runs each as a subprocess and asserts exit 0 so the
existing pytest+CI infrastructure picks them up without rewriting the
scripts as pytest test functions. Full doc + post-fix context lives in
sulci-platform/docs/architecture/flows/flows.md (private).
"""
import subprocess, sys, pathlib
import pytest

HERE = pathlib.Path(__file__).parent
SCRIPTS = [
    "flow_1.py",
    "flow_2.py",
    "flow_2_e2e.py",
    "flow_3.py",
    "flow_cli_devicecode.py",
    "flow_2_routemismatch.py",   # regression guard for sulci-oss #62
]

@pytest.mark.parametrize("script", SCRIPTS)
def test_flow_contract(script):
    result = subprocess.run(
        [sys.executable, str(HERE / script)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"{script} failed:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
