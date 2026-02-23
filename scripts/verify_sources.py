#!/usr/bin/env python3
"""
Verify sources.yaml (structure and optional path checks). Use after manual edit.
Exit 0 if valid, 1 if errors. Warnings do not change exit code.
"""
import sys
from pathlib import Path

import click

# Allow running from repo root or as script
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib.paths import get_sources_yaml_path
from lib.verify_sources import verify_sources_yaml


@click.command()
@click.option(
    "-r",
    "draft_root",
    type=click.Path(file_okay=False, path_type=Path),
    default=_REPO_ROOT,
    help="Draft repo root (for resolving relative paths when using --check-paths).",
)
@click.option(
    "--check-paths",
    is_flag=True,
    default=False,
    help="Warn when resolved paths (vault, .doc_sources/<name>, local) do not exist yet.",
)
@click.option(
    "-q",
    "quiet",
    is_flag=True,
    default=False,
    help="Only exit code; no output unless errors/warnings.",
)
def main(draft_root: Path, check_paths: bool, quiet: bool) -> None:
    draft_root = draft_root.resolve()
    path = get_sources_yaml_path()

    ok, errors, warnings = verify_sources_yaml(
        path,
        draft_root=draft_root if check_paths else None,
        check_paths=check_paths,
    )

    if not quiet:
        for e in errors:
            click.echo(f"Error: {e}", err=True)
        for w in warnings:
            click.echo(f"Warning: {w}", err=True)
        if ok and (errors or warnings):
            click.echo("Verify finished with messages above.")
        elif ok:
            click.echo("sources.yaml is valid.")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
