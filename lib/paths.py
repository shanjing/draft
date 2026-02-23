"""
Draft data paths: user data lives under DRAFT_HOME (~/.draft by default).
sources.yaml lives at DRAFT_HOME/sources.yaml; repo ships sources.example.yaml.
"""
import os
import shutil
from pathlib import Path

DOC_SOURCES_DIR = ".doc_sources"
VAULT_DIR = "vault"
SOURCES_YAML = "sources.yaml"
SOURCES_EXAMPLE_YAML = "sources.example.yaml"


def get_draft_home() -> Path:
    """User data root: DRAFT_HOME env or ~/.draft by default. Always returns a resolved path."""
    raw = os.environ.get("DRAFT_HOME", "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = (Path.home() / ".draft").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_sources_yaml_path() -> Path:
    """Path to sources.yaml in DRAFT_HOME (~/.draft/sources.yaml by default)."""
    return get_draft_home() / SOURCES_YAML


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


def ensure_sources_yaml(draft_root: Path) -> Path:
    """If DRAFT_HOME/sources.yaml is missing, create it from repo sources.example.yaml. Return its path."""
    path = get_sources_yaml_path()
    if path.is_file():
        return path
    get_draft_home().mkdir(parents=True, exist_ok=True)
    example = draft_root / SOURCES_EXAMPLE_YAML
    if example.is_file():
        shutil.copy2(example, path)
    else:
        path.write_text("repos:\n")
    return path
