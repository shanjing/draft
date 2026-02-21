"""
Verify sources.yaml after manual edit: structure, required fields, optional path checks.
Use from CLI (scripts/verify_sources.py) or in tests.
Vault and .doc_sources paths are under DRAFT_HOME (~/.draft).
"""
import re
from pathlib import Path

from lib.manifest import build_manifest
from lib.manifest import _parse_sources_yaml  # same parser used by manifest/pull/app
from lib.paths import get_doc_sources_root, get_vault_root


REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def verify_sources_yaml(
    path: Path,
    *,
    draft_root: Path | None = None,
    check_paths: bool = False,
) -> tuple[bool, list[str], list[str]]:
    """
    Verify sources.yaml at path.

    Returns (ok, errors, warnings).
    - errors: block pull/use (missing file, no repos:, missing source, invalid name).
    - warnings: optional (empty repos, path not yet present).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        errors.append(f"File not found: {path}")
        return False, errors, warnings

    if not path.is_file():
        errors.append(f"Not a file: {path}")
        return False, errors, warnings

    text = path.read_text()
    if "repos:" not in text or not re.search(r"^\s*repos\s*:\s*$", text, re.MULTILINE):
        errors.append("Missing or malformed top-level 'repos:' line")
        return False, errors, warnings

    repos = _parse_sources_yaml(path)

    if not repos:
        warnings.append("No repos defined (add repo blocks under 'repos:')")
        return True, errors, warnings

    for name, repo in repos.items():
        if not REPO_NAME_RE.match(name):
            errors.append(f"Repo name '{name}' contains invalid characters (use only A-Za-z0-9_.-)")
        src = repo.get("source")
        if src is None:
            errors.append(f"Repo '{name}': missing 'source:'")
        elif not str(src).strip():
            errors.append(f"Repo '{name}': 'source:' is empty")

    if check_paths and draft_root is not None and not errors:
        manifest = build_manifest(draft_root)
        for name, entry in manifest.get("sources", {}).items():
            if "resolved_path" not in entry:
                st = entry.get("source_type", "")
                if st == "vault":
                    warnings.append(f"'{name}': vault path not found (create {get_vault_root()})")
                elif st == "github":
                    warnings.append(
                        f"'{name}': not pulled yet (run Pull to create {get_doc_sources_root() / name})"
                    )
                else:
                    src = entry.get("source", "")
                    warnings.append(f"'{name}': local path not found ({src})")

    ok = len(errors) == 0
    return ok, errors, warnings
