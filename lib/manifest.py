"""
Generate draft_config.json from sources.yaml (single source of truth).
The manifest is always derived; never hand-edited. Used for re-link and tooling.
"""
import json
import re
from pathlib import Path

DOC_SOURCES_DIR = ".doc_sources"
VAULT_DIR = "vault"
MANIFEST_DIR = ".draft"
MANIFEST_FILENAME = "draft_config.json"


def _parse_sources_yaml(path: Path) -> dict[str, dict]:
    """Parse sources.yaml: { name: {"source": str, "url": str | None} }."""
    if not path.is_file():
        return {}
    lines = path.read_text().splitlines()
    repos: dict[str, dict] = {}
    name = None
    source = None
    url = None
    for line in lines:
        m_name = re.match(r"^\s{2,}([A-Za-z0-9_.-]+):\s*$", line)
        m_source = re.match(r"^\s+source:\s*(.+)$", line)
        m_url = re.match(r"^\s+url:\s*(.+)$", line)
        if m_name and "source" not in line and "url" not in line:
            if name and source is not None:
                repos[name] = {"source": source.strip(), "url": (url.strip() or None) if url else None}
            name = m_name.group(1)
            source = None
            url = None
            if name in ("repos", "source"):
                name = None
        elif m_source and name:
            source = m_source.group(1)
        elif m_url and name:
            url = m_url.group(1)
    if name and source is not None:
        repos[name] = {"source": source.strip(), "url": (url.strip() or None) if url else None}
    return repos


def _source_type(name: str, source: str, url: str | None) -> str:
    if name == VAULT_DIR:
        return "vault"
    if source and "github.com" in source:
        return "github"
    return "local"


def _resolved_path(draft_root: Path, name: str, source: str, source_type: str) -> str | None:
    if source_type == "vault":
        p = (draft_root / VAULT_DIR).resolve()
        return str(p) if p.exists() else None
    if source_type == "github":
        p = (draft_root / DOC_SOURCES_DIR / name).resolve()
        return str(p) if p.exists() else None
    # local
    if not source:
        return None
    if Path(source).is_absolute():
        p = Path(source).resolve()
    else:
        p = (draft_root / source).resolve()
    return str(p) if p.exists() else None


def build_manifest(draft_root: Path) -> dict:
    """Build manifest dict from sources.yaml and resolved paths. No I/O except read yaml."""
    sources_yaml = draft_root / "sources.yaml"
    repos = _parse_sources_yaml(sources_yaml)
    sources: dict[str, dict] = {}
    for name, repo in repos.items():
        src = repo.get("source") or ""
        url = repo.get("url")
        st = _source_type(name, src, url)
        entry: dict = {
            "source_type": st,
            "source": src,
        }
        if url is not None:
            entry["url"] = url
        resolved = _resolved_path(draft_root, name, src, st)
        if resolved is not None:
            entry["resolved_path"] = resolved
        sources[name] = entry
    return {
        "version": 1,
        "sources": sources,
        "file_registry_path": ".draft/file_registry.json",
    }


def update_manifest(draft_root: Path) -> None:
    """Regenerate draft_config.json from sources.yaml. Fails if sources.yaml is invalid (verify is mandatory)."""
    from lib.verify_sources import verify_sources_yaml

    sources_yaml = draft_root / "sources.yaml"
    ok, errors, _warnings = verify_sources_yaml(sources_yaml)
    if not ok:
        raise ValueError("sources.yaml invalid: " + "; ".join(errors))

    manifest_dir = draft_root / MANIFEST_DIR
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / MANIFEST_FILENAME
    manifest = build_manifest(draft_root)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
