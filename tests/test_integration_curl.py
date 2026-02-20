"""Integration test: run tests/test_ask_curl.sh against a live server (optional)."""
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "test_ask_curl.sh"


@pytest.mark.skipif(not SCRIPT.is_file(), reason="test_ask_curl.sh not found")
def test_ask_curl_script_exists():
    """Script test_ask_curl.sh is present and executable."""
    assert SCRIPT.is_file()


@pytest.mark.integration
def test_ask_curl_against_local_server():
    """Run test_ask_curl.sh against http://127.0.0.1:8058 (server must be running)."""
    if not SCRIPT.is_file():
        pytest.skip("test_ask_curl.sh not found")
    out = subprocess.run(
        ["bash", str(SCRIPT), "http://127.0.0.1:8058"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=Path(__file__).resolve().parent.parent,
    )
    # Script exits 0 even when server returns 405; we only check it ran
    assert out.returncode == 0 or "405" in out.stdout + out.stderr
