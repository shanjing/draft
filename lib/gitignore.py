"""
Filter paths by .gitignore. Uses `git check-ignore` when repo_root is a git repo.
Used so vector index, search index, and UI tree exclude ignored files/dirs.
"""
import subprocess
from pathlib import Path


def get_git_ignored_set(repo_root: Path, rel_paths: list[str]) -> set[str]:
    """
    Return the set of rel_paths that git would ignore (per .gitignore).
    If repo_root is not a git repo or git check-ignore fails, returns empty set (no paths excluded).
    rel_paths must be relative to repo_root, using forward slashes.
    """
    if not rel_paths:
        return set()
    if not (repo_root / ".git").exists():
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "--no-index", "--stdin"],
            input="\n".join(rel_paths),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode not in (0, 1):
            return set()
        # Exit 0: some paths ignored (listed on stdout). 1: none ignored (empty stdout).
        out = (proc.stdout or "").strip()
        if not out:
            return set()
        return set(line.strip() for line in out.splitlines() if line.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return set()
