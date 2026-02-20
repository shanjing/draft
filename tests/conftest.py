"""Pytest fixtures for Draft tests."""
import sys
from pathlib import Path

import pytest

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def draft_root():
    """Draft repo root (has vault/, sources.yaml, etc.)."""
    return REPO_ROOT


@pytest.fixture
def client(draft_root):
    """FastAPI TestClient for the Draft app. Runs in-process; uses draft_root from app."""
    from fastapi.testclient import TestClient
    from ui.app import app
    return TestClient(app)


@pytest.fixture
def temp_draft_root(tmp_path):
    """Temporary draft root with a minimal repo under .doc_sources (for ingest/chunk tests)."""
    (tmp_path / ".doc_sources" / "vault").mkdir(parents=True)
    (tmp_path / ".doc_sources" / "vault" / "DRAFT.md").write_text("# Draft\n\nDraft is a document mirror and RAG assistant.\n")
    return tmp_path
