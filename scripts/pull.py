#!/usr/bin/env python3
"""
Pull .md files from tracked source repos into draft (only when source is newer).

This is a pull only: it adds and updates files from source into draft. It does
NOT delete files in draft when they are removed from the source repo. Draft
keeps whatever was last pulled; files deleted in source remain in draft until
you remove them manually.
Reads sources.yaml; applies same exclusions as CLAUDE.md.
"""
from pathlib import Path
import base64
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

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
DOC_SOURCES_DIR = ".doc_sources"
VAULT_DIR = "vault"

# Doc sources and vault live under DRAFT_HOME (~/.draft)
try:
    from lib.paths import get_doc_sources_root
except ImportError:
    def get_doc_sources_root() -> Path:
        return Path.home() / ".draft" / DOC_SOURCES_DIR


def parse_repos_yaml(path: Path) -> dict[str, dict]:
    """Parse sources.yaml: { name: {"source": str, "url": str | None} }."""
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
    if parts and parts[0] in EXCLUDE_DIRS:
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


def _github_api_request(path: str, method: str = "GET") -> dict | list:
    """GET (or method) GitHub API path; path should start with /. Uses GITHUB_TOKEN if set."""
    import os
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/vnd.github.v3+json")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise click.ClickException(f"GitHub API error: {e}") from e


def _fetch_md_from_github(owner: str, repo: str, verbose: bool) -> list[tuple[str, bytes]]:
    """Fetch all included .md file (path, content) from GitHub repo. Uses same exclusions as local."""
    repo_info = _github_api_request(f"/repos/{owner}/{repo}")
    default_branch = repo_info.get("default_branch") or "main"
    try:
        branch_info = _github_api_request(f"/repos/{owner}/{repo}/branches/{default_branch}")
    except click.ClickException:
        try:
            default_branch = "master"
            branch_info = _github_api_request(f"/repos/{owner}/{repo}/branches/{default_branch}")
        except click.ClickException:
            raise click.ClickException(f"Could not get branch for {owner}/{repo}")
    tree_sha = branch_info.get("commit", {}).get("commit", {}).get("tree", {}).get("sha")
    if not tree_sha:
        tree_sha = branch_info.get("commit", {}).get("tree", {}).get("sha")
    if not tree_sha:
        raise click.ClickException(f"Could not get tree SHA for {owner}/{repo}")
    tree = _github_api_request(f"/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1")
    if not isinstance(tree, dict) or "tree" not in tree:
        raise click.ClickException(f"Invalid tree response for {owner}/{repo}")
    md_paths = []
    for entry in tree["tree"]:
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        if not path.endswith(".md"):
            continue
        if not should_include(path):
            continue
        md_paths.append(path)
    result: list[tuple[str, bytes]] = []
    for path in sorted(md_paths):
        try:
            content = _github_api_request(f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}?ref={default_branch}")
            if isinstance(content, dict) and "content" in content:
                raw = content["content"]
                if content.get("encoding") == "base64":
                    result.append((path, base64.b64decode(raw)))
                else:
                    result.append((path, raw.encode("utf-8")))
                if verbose:
                    click.echo(f"  {path}")
        except click.ClickException:
            continue
    return result


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


def do_pull(draft_root: Path, verbose: bool, quiet: bool = False) -> None:
    """Run pull from sources.yaml. When quiet, only echo summary lines (for UI console)."""
    sources_yaml = draft_root / "sources.yaml"
    if not sources_yaml.is_file():
        raise click.ClickException(f"sources.yaml not found at {sources_yaml}")

    _normalize_sources_yaml(sources_yaml)
    repos = parse_repos_yaml(sources_yaml)
    if not repos:
        click.echo("No repos listed in sources.yaml")
        return

    click.echo("Pull started.")
    doc_sources_root = get_doc_sources_root()
    doc_sources_root.mkdir(parents=True, exist_ok=True)
    for name, repo in repos.items():
        if name == VAULT_DIR:
            continue  # Vault lives outside .doc_sources (e.g. ./vault); can later be S3/iCloud
        source_path = repo["source"].strip()

        # --- Remote GitHub: fetch .md via API, write to draft/name/ ---
        if _is_github_url(source_path):
            parsed = _parse_github_url(source_path)
            if not parsed:
                click.echo(f"Skip {name}: invalid GitHub URL", err=True)
                continue
            owner, repo_name = parsed
            if not quiet:
                click.echo(f"[GitHub] Fetching {owner}/{repo_name} via API")
            if verbose and not quiet:
                click.echo(f"{name}")
            try:
                files = _fetch_md_from_github(owner, repo_name, verbose and not quiet)
            except click.ClickException as e:
                click.echo(f"Skip {name}: {e}", err=True)
                continue
            if verbose and not quiet and files:
                tree = _paths_to_tree([p for p, _ in files])
                _print_tree(tree)
                click.echo()
            updated = 0
            for rel_str, content in files:
                dest = doc_sources_root / name / rel_str
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                if not quiet:
                    click.echo(f"  [API] {rel_str}")
                updated += 1
            if updated > 0:
                click.echo(f"[Done] {name}: {updated} file(s) updated")
            else:
                click.echo(f"[Done] {name}: up to date")
            continue

        # --- Local path ---
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
                _ensure_repo_url_in_yaml(sources_yaml, name, git_url)
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

        if verbose and not quiet:
            click.echo(f"{name}")
            if paths:
                tree = _paths_to_tree(paths)
                _print_tree(tree)
            click.echo()

        if not quiet:
            click.echo(f"[Local] {name} from {source_root}")
        updated = 0
        for rel_str in paths:
            f = source_root / rel_str
            dest = doc_sources_root / name / rel_str
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or f.stat().st_mtime > dest.stat().st_mtime:
                shutil.copy2(f, dest)
                if not quiet:
                    click.echo(f"  [Copy] {rel_str}")
                updated += 1

        if updated > 0:
                click.echo(f"[Done] {name}: {updated} file(s) updated")
        else:
                click.echo(f"[Done] {name}: up to date")

    try:
        from lib.manifest import update_manifest
        update_manifest(draft_root)
        click.echo("Manifest updated (draft_config.json).")
    except Exception:
        pass


def do_add_repo(draft_root: Path, add_arg: str, verbose: bool, quiet: bool = False) -> None:
    """Add a repo to sources.yaml and run pull (including the new repo).
    add_arg can be: local path, repo name (../name), or GitHub URL (no clone).
    """
    sources_yaml = draft_root / "sources.yaml"
    if not sources_yaml.is_file():
        sources_yaml.write_text("repos:\n")

    existing = parse_repos_yaml(sources_yaml)
    add_arg = add_arg.strip()

    # GitHub URL: add source as URL (no local clone); pull will fetch .md via API
    if _is_github_url(add_arg):
        parsed = _parse_github_url(add_arg)
        if not parsed:
            raise click.ClickException(f"Invalid GitHub URL: {add_arg}")
        owner, repo_name = parsed
        name = f"{owner}_{repo_name}"
        if name in existing:
            raise click.ClickException(f"Repo '{name}' is already in sources.yaml")
        # Normalize to https URL for API
        source_path = f"https://github.com/{owner}/{repo_name}"
        _add_repo_to_yaml(sources_yaml, name, source_path, url=source_path)
        click.echo(f"Added {name} -> {source_path} (pull fetches .md from GitHub)")
        click.echo()
        do_pull(draft_root, verbose, quiet=quiet)
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

    if not resolved.is_dir():
        raise click.ClickException(f"Not a directory (cannot add): {resolved}")

    if name in existing:
        raise click.ClickException(f"Repo '{name}' is already in sources.yaml")

    git_url = get_git_remote_url(resolved)
    _add_repo_to_yaml(sources_yaml, name, source_path, url=git_url)
    click.echo(f"Added {name} -> {source_path}" + (f" ({git_url})" if git_url else ""))
    click.echo()
    do_pull(draft_root, verbose, quiet=quiet)


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
