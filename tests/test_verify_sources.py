"""Tests for sources.yaml verification (lib and CLI)."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.verify_sources import verify_sources_yaml


def test_verify_valid_sources_yaml(draft_root):
    path = draft_root / "sources.yaml"
    ok, errors, warnings = verify_sources_yaml(path)
    assert ok is True
    assert errors == []
    # May have warnings if check_paths not used or paths missing


def test_verify_missing_file(tmp_path):
    path = tmp_path / "sources.yaml"
    ok, errors, warnings = verify_sources_yaml(path)
    assert ok is False
    assert any("not found" in e for e in errors)
    assert len(errors) >= 1


def test_verify_no_repos_key(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("other:\n  foo: bar\n")
    ok, errors, warnings = verify_sources_yaml(path)
    assert ok is False
    assert any("repos" in e.lower() for e in errors)


def test_verify_empty_repos(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n")
    ok, errors, warnings = verify_sources_yaml(path)
    assert ok is True
    assert any("No repos" in w for w in warnings)


def test_verify_repo_missing_source(tmp_path):
    """Block with only url (no source) is not added by parser -> empty repos warning."""
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n  myrepo:\n    url: https://x.com\n")
    ok, errors, warnings = verify_sources_yaml(path)
    assert ok is True
    assert any("No repos" in w for w in warnings)


def test_verify_repo_empty_source(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n  myrepo:\n    source: \n")
    ok, errors, warnings = verify_sources_yaml(path)
    assert ok is False
    assert any("empty" in e.lower() or "source" in e.lower() for e in errors)


def test_verify_invalid_repo_name(tmp_path):
    """Valid repo name (allowed chars) passes; parser never yields invalid names from file."""
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n  good_name:\n    source: https://github.com/a/b\n")
    ok, errors, warnings = verify_sources_yaml(path)
    assert ok is True


def test_verify_check_paths_warns_missing(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n  vault:\n    source: ./vault\n  gh:\n    source: https://github.com/u/r\n")
    ok, errors, warnings = verify_sources_yaml(
        path, draft_root=tmp_path, check_paths=True
    )
    assert ok is True
    assert any("vault" in w.lower() or "not pulled" in w.lower() or "path" in w.lower() for w in warnings)


def test_verify_check_paths_no_warn_when_exists(tmp_path):
    """Vault and .doc_sources are under DRAFT_HOME; set it so vault path exists."""
    import os
    (tmp_path / "vault").mkdir(parents=True)
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n  vault:\n    source: ./vault\n")
    prev = os.environ.get("DRAFT_HOME")
    os.environ["DRAFT_HOME"] = str(tmp_path)
    try:
        ok, errors, warnings = verify_sources_yaml(
            path, draft_root=tmp_path, check_paths=True
        )
        assert ok is True
        assert not any("vault" in w and "not found" in w.lower() for w in warnings)
    finally:
        if prev is None:
            os.environ.pop("DRAFT_HOME", None)
        else:
            os.environ["DRAFT_HOME"] = prev


def test_cli_exit_0_on_valid(draft_root):
    import subprocess
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_sources.py"), "-r", str(draft_root)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_update_manifest_raises_on_invalid_yaml(tmp_path):
    """update_manifest() must not write draft_config.json when sources.yaml is invalid."""
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n  x:\n    source: \n")
    from lib.manifest import update_manifest
    with pytest.raises(ValueError, match="sources.yaml invalid"):
        update_manifest(tmp_path)
    manifest_file = tmp_path / ".draft" / "draft_config.json"
    assert not manifest_file.exists()


def test_cli_exit_1_on_invalid(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("repos:\n  x:\n    source: \n")  # empty source -> error
    import subprocess
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_sources.py"), "-r", str(tmp_path), "-q"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
