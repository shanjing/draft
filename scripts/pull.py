#!/usr/bin/env python3
"""
Pull .md files from tracked source repos into draft (only when source is newer).

This is a pull only: it adds and updates files from source into draft. It does
NOT delete files in draft when they are removed from the source repo. Draft
keeps whatever was last pulled; files deleted in source remain in draft until
you remove them manually.
Reads repos.yaml; applies same exclusions as CLAUDE.md.
"""
from pathlib import Path
import re
import shutil
import subprocess

import click

EXCLUDE_TOPLEVEL = {"README.md"}
EXCLUDE_BASENAME = {"CLAUDE.md"}
EXCLUDE_DIRS = (
    ".claude",
    ".cursor",
    ".pytest_cache",
    ".venv",
    ".git",
    "__pycache__",
    ".tmp",
    ".adk",
)


def parse_repos_yaml(path: Path) -> dict[str, dict]:
    """Parse repos.yaml: { name: {"source": str, "url": str | None} }."""
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


def _add_repo_to_yaml(repos_yaml: Path, name: str, source_path: str, url: str | None = None) -> None:
    """Append one repo to repos.yaml (preserves existing content and comment header)."""
    text = repos_yaml.read_text()
    lines = text.splitlines(keepends=True)
    insert_at = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*repos\s*:\s*$", line):
            insert_at = i + 1
            break
    if insert_at is None:
        raise click.ClickException("repos.yaml: could not find 'repos:' line")

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
    repos_yaml.write_text("".join(new_lines))


def should_include(rel_path: str) -> bool:
    if rel_path in EXCLUDE_TOPLEVEL:
        return False
    if Path(rel_path).name in EXCLUDE_BASENAME:
        return False
    parts = Path(rel_path).parts
    if parts and parts[0] in EXCLUDE_DIRS:
        return False
    return True


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


def _ensure_repo_url_in_yaml(repos_yaml: Path, name: str, url: str) -> None:
    """Insert or update 'url:' for the given repo in repos.yaml."""
    text = repos_yaml.read_text()
    lines = text.splitlines(keepends=True)
    in_block = False
    source_line_idx = None
    url_line_idx = None
    for i, line in enumerate(lines):
        m = re.match(r"^\s{2,}([A-Za-z0-9_.-]+):\s*$", line)
        if m and "source" not in line and "url" not in line:
            in_block = m.group(1) == name
            if in_block:
                source_line_idx = None
                url_line_idx = None
        elif in_block and re.match(r"^\s+source\s*:", line):
            source_line_idx = i
        elif in_block and re.match(r"^\s+url\s*:", line):
            url_line_idx = i
            break
    if source_line_idx is None:
        return
    new_url_line = f"    url: {url}\n"
    if url_line_idx is not None:
        lines[url_line_idx] = new_url_line
    else:
        lines.insert(source_line_idx + 1, new_url_line)
    repos_yaml.write_text("".join(lines))


def do_pull(draft_root: Path, verbose: bool) -> None:
    """Run pull from repos.yaml."""
    repos_yaml = draft_root / "repos.yaml"
    if not repos_yaml.is_file():
        raise click.ClickException(f"repos.yaml not found at {repos_yaml}")

    repos = parse_repos_yaml(repos_yaml)
    if not repos:
        click.echo("No repos listed in repos.yaml")
        return

    for name, repo in repos.items():
        source_path = repo["source"]
        if not Path(source_path).is_absolute():
            source_root = (draft_root / source_path).resolve()
        else:
            source_root = Path(source_path)

        if not source_root.is_dir():
            click.echo(f"Skip {name}: source not found: {source_root}", err=True)
            continue

        # If git repo and url missing in yaml, fetch and write
        if not repo.get("url"):
            git_url = get_git_remote_url(source_root)
            if git_url:
                _ensure_repo_url_in_yaml(repos_yaml, name, git_url)
                repo["url"] = git_url

        # Collect included paths (for verbose tree and for copy)
        paths: list[str] = []
        for f in source_root.rglob("*.md"):
            try:
                rel = f.relative_to(source_root)
            except ValueError:
                continue
            rel_str = rel.as_posix()
            if not should_include(rel_str):
                continue
            paths.append(rel_str)

        if verbose:
            click.echo(f"{name}")
            if paths:
                tree = _paths_to_tree(paths)
                _print_tree(tree)
            click.echo()

        # Pull only: copy from source into draft; never delete files in draft.
        updated = 0
        for rel_str in paths:
            f = source_root / rel_str
            dest = draft_root / name / rel_str
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or f.stat().st_mtime > dest.stat().st_mtime:
                shutil.copy2(f, dest)
                if not verbose:
                    click.echo(f"  {rel_str}")
                updated += 1

        if updated > 0:
            click.echo(f"{name}: {updated} file(s) updated")
        else:
            click.echo(f"{name}: up to date")


def do_add_repo(draft_root: Path, add_arg: str, verbose: bool) -> None:
    """Add a repo to repos.yaml and run pull (including the new repo)."""
    repos_yaml = draft_root / "repos.yaml"
    if not repos_yaml.is_file():
        raise click.ClickException(f"repos.yaml not found at {repos_yaml}")

    existing = parse_repos_yaml(repos_yaml)
    add_arg = add_arg.strip()

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

    if not resolved.is_dir():
        raise click.ClickException(f"Not a directory (cannot add): {resolved}")

    if name in existing:
        raise click.ClickException(f"Repo '{name}' is already in repos.yaml")

    git_url = get_git_remote_url(resolved)
    _add_repo_to_yaml(repos_yaml, name, source_path, url=git_url)
    click.echo(f"Added {name} -> {source_path}" + (f" ({git_url})" if git_url else ""))
    click.echo()
    do_pull(draft_root, verbose)


@click.command()
@click.option(
    "-r",
    "repo_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="List all .md files from this repo (path); repo does not need to be in repos.yaml.",
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
    help="Add a repo to management: pass repo name (e.g. OtherRepo) or relative path (e.g. ../OtherRepo). Updates repos.yaml and runs pull.",
)
def main(
    repo_path: Path | None,
    snippet: bool,
    verbose: bool,
    add_repo: str | None,
) -> None:
    script_dir = Path(__file__).resolve().parent
    draft_root = script_dir.parent

    if add_repo is not None:
        do_add_repo(draft_root, add_repo, verbose)
    elif repo_path is not None:
        list_md_in_repo(repo_path, snippet)
    else:
        do_pull(draft_root, verbose)


if __name__ == "__main__":
    main()
