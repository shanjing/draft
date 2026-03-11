"""Pytest fixtures for Draft tests."""
import os
import sys
from pathlib import Path

import pytest

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def draft_root(draft_home):
    """Draft repo root. Ensures sources.yaml exists in DRAFT_HOME (draft_home) from example if missing."""
    from lib.paths import ensure_sources_yaml
    ensure_sources_yaml(REPO_ROOT)
    return REPO_ROOT


@pytest.fixture
def draft_home(tmp_path):
    """DRAFT_HOME for tests: tmp path with vault/ and optional .doc_sources."""
    (tmp_path / "vault").mkdir(parents=True)
    (tmp_path / "vault" / "DRAFT.md").write_text("# Draft\n\nDraft is a document mirror and RAG assistant.\n")
    prev = os.environ.get("DRAFT_HOME")
    os.environ["DRAFT_HOME"] = str(tmp_path)
    yield tmp_path
    if prev is None:
        os.environ.pop("DRAFT_HOME", None)
    else:
        os.environ["DRAFT_HOME"] = prev


@pytest.fixture
def client(draft_root, draft_home):
    """FastAPI TestClient for the Draft app. Uses draft_home for vault/.doc_sources."""
    from fastapi.testclient import TestClient
    from ui.app import app
    return TestClient(app)


@pytest.fixture
def temp_draft_root(tmp_path):
    """Temporary DRAFT_HOME with vault/ (for ingest/chunk tests). Sets DRAFT_EMBED_MODEL so build_index works."""
    (tmp_path / "vault").mkdir(parents=True)
    (tmp_path / "vault" / "DRAFT.md").write_text("# Draft\n\nDraft is a document mirror and RAG assistant.\n")
    prev_home = os.environ.get("DRAFT_HOME")
    prev_embed = os.environ.get("DRAFT_EMBED_MODEL")
    os.environ["DRAFT_HOME"] = str(tmp_path)
    os.environ["DRAFT_EMBED_MODEL"] = "sentence-transformers/all-MiniLM-L6-v2"
    yield tmp_path
    if prev_home is None:
        os.environ.pop("DRAFT_HOME", None)
    else:
        os.environ["DRAFT_HOME"] = prev_home
    if prev_embed is None:
        os.environ.pop("DRAFT_EMBED_MODEL", None)
    else:
        os.environ["DRAFT_EMBED_MODEL"] = prev_embed
