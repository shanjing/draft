#!/usr/bin/env python3
"""
Pull .md files from tracked source repos into draft (only when source is newer).

This is a pull only: it adds and updates files from source into draft. It does
NOT delete files in draft when they are removed from the source repo. Draft
keeps whatever was last pulled; files deleted in source remain in draft until
you remove them manually.
Reads sources.yaml; applies same exclusions as CLAUDE.md.
"""
import sys
from pathlib import Path

# Ensure repo root is on path so "lib" is importable when run as scripts/pull.py
_SCRIPT_DIR = Path(__file__).resolve().parent
_DRAFT_ROOT = _SCRIPT_DIR.parent
if str(_DRAFT_ROOT) not in sys.path:
    sys.path.insert(0, str(_DRAFT_ROOT))

import os
import re
import shutil
import subprocess

import click

EXCLUDE_TOPLEVEL: set[str] = set()
EXCLUDE_BASENAME = {"CLAUDE.md"}
EXCLUDE_DIRS = (
    ".claude",
    ".cursor",
    ".vscode",
    ".pytest_cache",
    ".venv",
    ".git",
    "__pycache__",
    ".tmp",
    ".adk",
    ".cache",
)
DOC_SOURCES_DIR = ".doc_sources"
VAULT_DIR = "vault"

# Doc sources and vault live under DRAFT_HOME (~/.draft)
try:
    from lib.paths import get_clones_root
    from lib.manifest import parse_sources_yaml
except ImportError:
    def get_clones_root() -> Path:
        return Path.home() / ".draft" / ".clones"


def get_git_remote_url(repo_path: Path) -> str | None:
    """Return origin remote URL if repo_path is a git repo, else None."""
    if not (repo_path / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _is_path_like(s: str) -> bool:
    """True if input looks like a path (relative or absolute) rather than a bare repo name."""
    s = s.strip()
    if not s:
        return False
    if s.startswith("/") or s.startswith(".") or "/" in s or "\\" in s:
        return True
    return False


def _add_repo_to_yaml(sources_yaml: Path, name: str, source_path: str, url: str | None = None) -> None:
    """Append one repo to sources.yaml (preserves existing content and comment header)."""
    text = sources_yaml.read_text()
    lines = text.splitlines(keepends=True)
    insert_at = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*repos\s*:\s*$", line):
            insert_at = i + 1
            break
    if insert_at is None:
        raise click.ClickException("sources.yaml: could not find 'repos:' line")

    end = insert_at
    for i in range(insert_at, len(lines)):
        if re.match(r"^\s{2,}[A-Za-z0-9_.-]+\s*:\s*$", lines[i]) and "source" not in lines[i]:
            end = i
        elif re.match(r"^\s+source\s*:", lines[i]):
            end = i + 1

    new_block = f"  {name}:\n    source: {source_path}\n"
    if url:
        new_block += f"    url: {url}\n"
    new_lines = lines[:end] + [new_block] + lines[end:]
    sources_yaml.write_text("".join(new_lines))


def should_include(rel_path: str) -> bool:
    if rel_path in EXCLUDE_TOPLEVEL:
        return False
    if Path(rel_path).name in EXCLUDE_BASENAME:
        return False
    parts = Path(rel_path).parts
    if any(p in EXCLUDE_DIRS for p in parts):
        return False
    return True


def _is_github_url(source: str) -> bool:
    """True if source is a GitHub repo URL (https or git@)."""
    s = (source or "").strip()
    return s.startswith("https://github.com/") or s.startswith("http://github.com/") or s.startswith("git@github.com:")


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Return (owner, repo) or None. Strips .git from repo."""
    url = (url or "").strip()
    # https://github.com/owner/repo or .../repo.git
    if "github.com/" in url:
        try:
            parts = url.split("github.com/", 1)[1].replace(".git", "").strip("/").split("/")
            if len(parts) >= 2:
                return (parts[0], parts[1])
            if len(parts) == 1:
                return (parts[0], parts[0])
        except IndexError:
            pass
    # git@github.com:owner/repo.git
    if url.startswith("git@github.com:"):
        try:
            owner_repo = url.split("git@github.com:", 1)[1].replace(".git", "").strip("/")
            parts = owner_repo.split("/", 1)
            if len(parts) == 2:
                return (parts[0], parts[1])
            if len(parts) == 1:
                return (parts[0], parts[0])
        except IndexError:
            pass
    return None


def _require_git() -> None:
    """Ensure git is available; raise ClickException if not."""
    try:
        out = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode != 0:
            raise click.ClickException("Git is required for GitHub sources. Install git (https://git-scm.com) and try again.")
    except FileNotFoundError:
        raise click.ClickException("Git is required for GitHub sources. Install git (https://git-scm.com) and try again.")


def _ensure_clone(git_url: str, clone_dir: Path) -> None:
    """Clone repo into clone_dir if it does not already exist. git_url can be https or git@."""
    if (clone_dir / ".git").is_dir():
        return
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--", git_url, str(clone_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip()
        raise click.ClickException(f"git clone failed: {err}") from e
    except subprocess.TimeoutExpired:
        raise click.ClickException("git clone timed out") from None


def _git_pull(clone_dir: Path) -> None:
    """Run git pull in clone_dir."""
    try:
        subprocess.run(
            ["git", "-C", str(clone_dir), "pull"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip()
        raise click.ClickException(f"git pull failed: {err}") from e
    except subprocess.TimeoutExpired:
        raise click.ClickException("git pull timed out") from None


def _paths_to_tree(paths: list[str]) -> dict:
    """Build a nested dict from relative paths: dirs are dicts, files are None."""
    root: dict = {}
    for path in sorted(paths):
        parts = path.split("/")
        current = root
        for i, p in enumerate(parts):
            if i == len(parts) - 1:
                current[p] = None
            else:
                current.setdefault(p, {})
                current = current[p]
    return root


def _print_tree(d: dict, prefix: str = "") -> None:
    """Print tree dict in Linux tree style (├── └── │   ). Dirs first, then files, then by name."""
    items = sorted(d.items(), key=lambda x: (x[1] is None, x[0]))
    for i, (name, child) in enumerate(items):
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "
        click.echo(prefix + connector + name)
        if child is not None and isinstance(child, dict):
            ext = "    " if is_last else "│   "
            _print_tree(child, prefix + ext)


def list_md_in_repo(repo_root: Path, show_snippet: bool) -> None:
    """List all included .md files under repo_root in tree format; optionally show first 3 lines of each."""
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise click.ClickException(f"Not a directory: {repo_root}")

    files: list[tuple[Path, str]] = []
    for f in sorted(repo_root.rglob("*.md")):
        try:
            rel = f.relative_to(repo_root)
        except ValueError:
            continue
        rel_str = rel.as_posix()
        if not should_include(rel_str):
            continue
        files.append((f, rel_str))

    paths = [rel_str for _, rel_str in files]
    if paths:
        tree = _paths_to_tree(paths)
        click.echo(repo_root.name)
        _print_tree(tree)
    if show_snippet:
        click.echo()
        for f, rel_str in files:
            click.echo(rel_str)
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in lines[:3]:
                    click.echo(f"  | {line}")
                if len(lines) > 3:
                    click.echo("  | ...")
            except OSError as e:
                click.echo(f"  (error reading: {e})")
            click.echo()


def _ensure_repo_url_in_yaml(sources_yaml: Path, name: str, url: str) -> None:
    """Insert or update 'url:' for the given repo in sources.yaml. Keeps only one url line per repo."""
    text = sources_yaml.read_text()
    lines = text.splitlines(keepends=True)
    in_block = False
    source_line_idx = None
    url_line_idxs: list[int] = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s{2,}([A-Za-z0-9_.-]+):\s*$", line)
        if m and "source" not in line and "url" not in line:
            if in_block and m.group(1) != name:
                break  # left our block; do not use any later repo's source line
            in_block = m.group(1) == name
            if in_block:
                source_line_idx = None
                url_line_idxs = []
        elif in_block and re.match(r"^\s+source\s*:", line):
            source_line_idx = i
        elif in_block and re.match(r"^\s+url\s*:", line):
            url_line_idxs.append(i)
    if source_line_idx is None:
        return
    new_url_line = f"    url: {url}\n"
    if url_line_idxs:
        # Replace first url line with new value; remove any duplicate url lines in this block
        lines[url_line_idxs[0]] = new_url_line
        for idx in reversed(url_line_idxs[1:]):
            del lines[idx]
    else:
        lines.insert(source_line_idx + 1, new_url_line)
    sources_yaml.write_text("".join(lines))


def _normalize_sources_yaml(sources_yaml: Path) -> None:
    """Remove duplicate 'url:' lines within each repo block (keep first only)."""
    lines = sources_yaml.read_text().splitlines(keepends=True)
    to_drop: set[int] = set()
    in_block = False
    url_line_idxs: list[int] = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s{2,}([A-Za-z0-9_.-]+):\s*$", line)
        if m and "source" not in line and "url" not in line:
            # New repo block: mark duplicate url lines from previous block for removal
            for idx in url_line_idxs[1:]:
                to_drop.add(idx)
            in_block = True
            url_line_idxs = []
        elif in_block and re.match(r"^\s+url\s*:", line):
            url_line_idxs.append(i)
    for idx in url_line_idxs[1:]:
        to_drop.add(idx)
    if to_drop:
        new_lines = [ln for j, ln in enumerate(lines) if j not in to_drop]
        sources_yaml.write_text("".join(new_lines))


def _run_index_for_ai_if_ready(draft_root: Path, quiet: bool) -> None:
    """If a valid LLM is configured, run index_for_ai and echo progress (for CLI). Skip when DRAFT_SETUP=1 (setup.sh does one build at the end)."""
    if os.environ.get("DRAFT_SETUP"):
        return
    try:
        from lib.ai_engine import llm_ready
        if not llm_ready(draft_root):
            return
    except Exception:
        return
    index_script = draft_root / "scripts" / "index_for_ai.py"
    if not index_script.is_file():
        return
    if not quiet:
        click.echo("Building RAG index...")
    result = subprocess.run(
        [sys.executable, str(index_script)],
        cwd=str(draft_root),
        capture_output=True,
        text=True,
        timeout=600,
        env=os.environ.copy(),
    )
    if not quiet:
        if result.returncode == 0:
            click.echo(result.stdout or "Done.")
        else:
            click.echo((result.stderr or result.stdout or "RAG index build failed.").strip(), err=True)


def do_pull(draft_root: Path, verbose: bool, quiet: bool = False) -> None:
    """Run pull from sources.yaml (in DRAFT_HOME). When quiet, only echo summary lines (for UI console)."""
    from lib.paths import ensure_sources_yaml
    sources_yaml = ensure_sources_yaml(draft_root)
    _normalize_sources_yaml(sources_yaml)
    repos = parse_sources_yaml(sources_yaml)
    if not repos:
        click.echo("No repos listed in sources.yaml")
        return

    click.echo("Pull started.")
    for name, repo in repos.items():
        if name == VAULT_DIR:
            continue  # Vault is not pulled from git
        source_path = repo["source"].strip()

        # --- Remote GitHub: clone/pull via git (no copy; index and UI read from .clones) ---
        if _is_github_url(source_path):
            parsed = _parse_github_url(source_path)
            if not parsed:
                click.echo(f"Skip {name}: invalid GitHub URL", err=True)
                continue
            _require_git()
            clone_dir = get_clones_root() / name
            try:
                _ensure_clone(source_path, clone_dir)
                if not quiet:
                    click.echo(f"[GitHub] {name} from {clone_dir}")
                _git_pull(clone_dir)
            except click.ClickException as e:
                click.echo(f"Skip {name}: {e}", err=True)
                continue
            if not quiet:
                click.echo(f"[Done] {name}: up to date (index/UI read from clone)")
            continue

        # --- Local path: no copy; index and UI read from source path ---
        if not Path(source_path).is_absolute():
            source_root = (draft_root / source_path).resolve()
        else:
            source_root = Path(source_path)

        if not source_root.is_dir() and not source_root.is_file():
            click.echo(f"Skip {name}: source not found: {source_root}", err=True)
            continue

        if not repo.get("url"):
            git_url = get_git_remote_url(source_root)
            if git_url:
                _ensure_repo_url_in_yaml(sources_yaml, name, git_url)
                repo["url"] = git_url

        if not quiet:
            click.echo(f"[Local] {name} from {source_root} (no copy; index/UI read from source)")
            click.echo(f"[Done] {name}: up to date")

    try:
        from lib.manifest import update_manifest
        update_manifest(draft_root)
        click.echo("Manifest updated (draft_config.json).")
    except Exception:
        pass


def do_add_repo(draft_root: Path, add_arg: str, verbose: bool, quiet: bool = False) -> None:
    """Add a repo to sources.yaml (in DRAFT_HOME) and run pull (including the new repo).
    add_arg can be: local path, repo name (../name), or GitHub URL (clone/pull via git).
    """
    from lib.paths import ensure_sources_yaml
    sources_yaml = ensure_sources_yaml(draft_root)
    existing = parse_sources_yaml(sources_yaml)
    add_arg = add_arg.strip()

    # GitHub URL: add source as URL; pull will clone/pull via git and sync .md
    if _is_github_url(add_arg):
        parsed = _parse_github_url(add_arg)
        if not parsed:
            raise click.ClickException(f"Invalid GitHub URL: {add_arg}")
        owner, repo_name = parsed
        name = f"{owner}_{repo_name}"
        if name in existing:
            raise click.ClickException(f"Repo '{name}' is already in sources.yaml")
        source_path = f"https://github.com/{owner}/{repo_name}"
        _add_repo_to_yaml(sources_yaml, name, source_path, url=source_path)
        click.echo(f"Added {name} -> {source_path} (pull uses git clone/pull)")
        click.echo()
        do_pull(draft_root, verbose, quiet=quiet)
        _run_index_for_ai_if_ready(draft_root, quiet)
        return

    if _is_path_like(add_arg):
        # Treat as path: resolve and derive name from last component
        source_path = add_arg
        resolved = (draft_root / add_arg).resolve() if not Path(add_arg).is_absolute() else Path(add_arg).resolve()
        name = resolved.name
    else:
        # Treat as repo name: default source is ../<name> (sibling of draft)
        name = add_arg
        source_path = f"../{name}"
        resolved = (draft_root / source_path).resolve()

    if not resolved.is_dir() and not resolved.is_file():
        raise click.ClickException(f"Not a directory or file (cannot add): {resolved}")

    if name in existing:
        raise click.ClickException(f"Repo '{name}' is already in sources.yaml")

    git_url = get_git_remote_url(resolved)
    _add_repo_to_yaml(sources_yaml, name, source_path, url=git_url)
    click.echo(f"Added {name} -> {source_path}" + (f" ({git_url})" if git_url else ""))
    click.echo()
    do_pull(draft_root, verbose, quiet=quiet)
    _run_index_for_ai_if_ready(draft_root, quiet)


@click.command()
@click.option(
    "-r",
    "repo_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="List all .md files from this repo (path); repo does not need to be in sources.yaml.",
)
@click.option(
    "-s",
    "snippet",
    is_flag=True,
    default=False,
    help="With -r, show the first 3 lines of each file.",
)
@click.option(
    "-v",
    "verbose",
    is_flag=True,
    default=False,
    help="Show repos being scanned and each tracked file in tree format (like Linux tree).",
)
@click.option(
    "-a",
    "add_repo",
    type=str,
    default=None,
    help="Add a repo to management: pass repo name (e.g. OtherRepo) or relative path (e.g. ../OtherRepo). Updates sources.yaml and runs pull.",
)
@click.option(
    "-q",
    "quiet",
    is_flag=True,
    default=False,
    help="Summary only: one line per repo (for UI system console).",
)
def main(
    repo_path: Path | None,
    snippet: bool,
    verbose: bool,
    add_repo: str | None,
    quiet: bool,
) -> None:
    script_dir = Path(__file__).resolve().parent
    draft_root = script_dir.parent

    if add_repo is not None:
        do_add_repo(draft_root, add_repo, verbose, quiet=quiet)
    elif repo_path is not None:
        list_md_in_repo(repo_path, snippet)
    else:
        do_pull(draft_root, verbose, quiet=quiet)


if __name__ == "__main__":
    main()
