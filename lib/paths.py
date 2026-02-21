"""
Draft data paths: user data lives under DRAFT_HOME (~/.draft by default).
Repo root (DRAFT_ROOT) holds code and sources.yaml; vault and .doc_sources live under DRAFT_HOME.
"""
import os
from pathlib import Path

DOC_SOURCES_DIR = ".doc_sources"
VAULT_DIR = "vault"


def get_draft_home() -> Path:
    """User data root: DRAFT_HOME env or ~/.draft. Always returns a resolved path."""
    raw = os.environ.get("DRAFT_HOME", "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = (Path.home() / ".draft").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_doc_sources_root() -> Path:
    """Root for pulled doc sources: ~/.draft/.doc_sources (or DRAFT_HOME/.doc_sources)."""
    return get_draft_home() / DOC_SOURCES_DIR


def get_vault_root() -> Path:
    """Vault directory: ~/.draft/vault (or DRAFT_HOME/vault)."""
    return get_draft_home() / VAULT_DIR


def ensure_vault_ready() -> Path:
    """Ensure DRAFT_HOME and vault directory exist; create if missing. Call at startup."""
    home = get_draft_home()
    vault = home / VAULT_DIR
    vault.mkdir(parents=True, exist_ok=True)
    return vault
