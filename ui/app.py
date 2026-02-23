"""
Draft UI: serve document tree and markdown content. Launch with uvicorn.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Disable Chroma telemetry before any chromadb import (avoids "capture() takes 1 positional argument" error)
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DRAFT_ROOT = Path(__file__).resolve().parent.parent
DOC_SOURCES_DIR = ".doc_sources"
VAULT_DIR = "vault"

# Global allowed document types (tree + doc viewer). Capped at 5.
ALLOWED_DOC_EXTENSIONS = (".md", ".txt", ".pdf", ".doc", ".docx")
DOC_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
if str(DRAFT_ROOT) not in sys.path:
    sys.path.insert(0, str(DRAFT_ROOT))

# Load .env so DRAFT_LLM_* and OLLAMA_MODEL work regardless of how server is started
try:
    from dotenv import load_dotenv
    load_dotenv(DRAFT_ROOT / ".env")
except ImportError:
    pass

from lib.log import logger, configure as configure_log
from lib.paths import get_doc_sources_root, get_vault_root, ensure_vault_ready, ensure_sources_yaml, get_sources_yaml_path

configure_log()


def _parse_repos_yaml(path: Path) -> dict:
    import re
    lines = path.read_text().splitlines()
    repos = {}
    name = None
    source = None
    url = None
    for line in lines:
        m = re.match(r"^\s{2,}([A-Za-z0-9_.-]+):\s*$", line)
        m_s = re.match(r"^\s+source:\s*(.+)$", line)
        m_u = re.match(r"^\s+url:\s*(.+)$", line)
        if m and "source" not in line and "url" not in line:
            if name and source is not None:
                repos[name] = {"source": source.strip(), "url": (url.strip() or None) if url else None}
            name = m.group(1)
            source = None
            url = None
            if name in ("repos", "source"):
                name = None
        elif m_s and name:
            source = m_s.group(1)
        elif m_u and name:
            url = m_u.group(1)
    if name and source is not None:
        repos[name] = {"source": source.strip(), "url": (url.strip() or None) if url else None}
    return repos


def _remove_repo_from_sources_yaml(path: Path, repo_name: str) -> bool:
    """Remove one repo block from sources.yaml. Returns True if removed, False if not found."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    removed = False

    while i < len(lines):
        line = lines[i]
        import re
        m_repo = re.match(r"^(\s{2,})([A-Za-z0-9_.-]+):\s*$", line)
        if m_repo and "source" not in line and "url" not in line and m_repo.group(2) == repo_name:
            removed = True
            i += 1
            while i < len(lines):
                nxt = lines[i]
                m_next_repo = re.match(r"^(\s{2,})([A-Za-z0-9_.-]+):\s*$", nxt)
                if m_next_repo and "source" not in nxt and "url" not in nxt:
                    break
                if nxt.strip() and not nxt.startswith(" "):
                    break
                i += 1
            continue
        out.append(line)
        i += 1

    if removed:
        path.write_text("".join(out), encoding="utf-8")
    return removed


VAULT_SOURCES_FILENAME = ".draft_sources.json"


def _read_vault_sources(vault_root: Path) -> dict[str, str]:
    """Read vault file -> source name map (from sources.yaml entry names). Returns {} if missing/invalid."""
    path = vault_root / VAULT_SOURCES_FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_vault_source(vault_root: Path, rel_path: str, source: str) -> None:
    """Record that a vault file came from the given source (sources.yaml entry name)."""
    path = vault_root / VAULT_SOURCES_FILENAME
    data = _read_vault_sources(vault_root)
    data[rel_path] = source
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _remove_vault_source_refs(vault_root: Path, source_name: str) -> int:
    """Remove any vault source-map entries that reference source_name. Returns number removed."""
    path = vault_root / VAULT_SOURCES_FILENAME
    if not path.is_file():
        return 0
    data = _read_vault_sources(vault_root)
    to_drop = [k for k, v in data.items() if v == source_name]
    if not to_drop:
        return 0
    for k in to_drop:
        data.pop(k, None)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return len(to_drop)


def _paths_to_tree_node(paths: list[str], source_map: dict[str, str] | None = None) -> dict:
    """Build a tree node: { name, type: file|dir, path?, source?, children? }. source_map: path -> source name (vault only)."""
    root: dict = {}
    for path in sorted(paths):
        parts = path.split("/")
        current = root
        for i, p in enumerate(parts):
            if i == len(parts) - 1:
                current[p] = ("file", path)
            else:
                if p not in current:
                    current[p] = {}
                if isinstance(current[p], dict):
                    current = current[p]
                else:
                    current = {}
                    break
    def to_node(name: str, val) -> dict:
        if isinstance(val, dict):
            children = [to_node(k, v) for k, v in sorted(val.items(), key=lambda x: (0 if isinstance(x[1], dict) else 1, x[0]))]
            return {"name": name, "type": "dir", "children": children}
        _, path = val
        node: dict = {"name": name, "type": "file", "path": path}
        if source_map is not None and path in source_map:
            node["source"] = source_map[path]
        return node
    return {"name": "", "type": "dir", "children": [to_node(k, v) for k, v in sorted(root.items(), key=lambda x: (0 if isinstance(x[1], dict) else 1, x[0]))]}


def _doc_sources_root() -> Path:
    """Root for repo dirs: ~/.draft/.doc_sources (or DRAFT_HOME)."""
    return get_doc_sources_root()


def _repo_tree_entry(name: str, repo_dir: Path, url: str | None = None) -> dict:
    """Build one repo entry: name, url, tree (children). Uses global ALLOWED_DOC_EXTENSIONS. For vault, file nodes get source from .draft_sources.json."""
    paths = []
    for f in repo_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in ALLOWED_DOC_EXTENSIONS:
            # Exclude the vault sources manifest from the tree
            if name == VAULT_DIR and f.name == VAULT_SOURCES_FILENAME:
                continue
            try:
                rel = f.relative_to(repo_dir)
                paths.append(rel.as_posix())
            except ValueError:
                continue
    source_map = _read_vault_sources(repo_dir) if name == VAULT_DIR else None
    tree = _paths_to_tree_node(paths, source_map=source_map)
    return {"name": name, "url": url, "tree": tree["children"]}


def _resolve_repo_dir(name: str, source: str) -> Path | None:
    """Resolve repo directory from sources.yaml entry. Vault: DRAFT_HOME/vault; others: .doc_sources/name."""
    if name == VAULT_DIR:
        ensure_vault_ready()
        return get_vault_root()
    # Normal source: stored under .doc_sources/<name>/
    return _doc_sources_root() / name


def get_tree() -> list:
    """Build tree from sources.yaml in DRAFT_HOME (source of truth). Vault first, then others in yaml order."""
    sources_yaml = ensure_sources_yaml(DRAFT_ROOT)
    if not sources_yaml.is_file():
        return []
    repos = _parse_repos_yaml(sources_yaml)
    doc_sources = _doc_sources_root()
    result = []
    for name in repos:
        repo_dir = _resolve_repo_dir(name, repos[name]["source"])
        if repo_dir is None:
            continue
        if not repo_dir.is_dir():
            continue
        result.append(_repo_tree_entry(name, repo_dir, repos[name].get("url")))
    # Keep vault first if present
    vault_idx = next((i for i, r in enumerate(result) if r["name"] == VAULT_DIR), -1)
    if vault_idx > 0:
        result.insert(0, result.pop(vault_idx))
    return result


app = FastAPI(title="Draft", description="Browse draft documents")


@app.on_event("startup")
def _startup():
    ensure_sources_yaml(DRAFT_ROOT)
    ensure_vault_ready()


try:
    ensure_sources_yaml(DRAFT_ROOT)
    from lib.manifest import update_manifest
    update_manifest(DRAFT_ROOT)
except Exception:
    pass


@app.get("/api/tree")
def api_tree():
    return {"repos": get_tree()}


def _search_module():
    from . import search_index
    return search_index


def _ai_engine():
    from lib import ai_engine
    return ai_engine


class AskBody(BaseModel):
    query: str = ""


class ReindexAIBody(BaseModel):
    mode: str = "quick"


@app.get("/api/llm_status")
def api_llm_status():
    """Return current LLM provider and model from env (for debugging)."""
    from lib import ai_engine
    ai_engine._ensure_env_loaded(DRAFT_ROOT)
    provider = ai_engine._env_strip("DRAFT_LLM_PROVIDER", "")
    model = ai_engine._env_strip("OLLAMA_MODEL") or ai_engine._env_strip("LOCAL_AI_MODEL") or ""
    if model and model.startswith("ollama_chat/"):
        model = model.replace("ollama_chat/", "", 1)
    if not model and provider == "ollama":
        model = "qwen3:8b"
    cloud = ai_engine._env_strip("CLOUD_AI_MODEL", "")
    if not provider and cloud:
        provider = "gemini"
        model = cloud
    if not provider:
        provider = "ollama"
        model = model or "qwen3:8b"
    return {"provider": provider, "model": model}


@app.post("/api/ask")
def api_ask(body: AskBody):
    """Stream an AI answer over your docs via SSE. Requires AI index (run scripts/index_for_ai.py) and Ollama or cloud API key."""
    query = (body.query or "").strip()
    if not query:
        return {"error": "Missing query."}

    def event_stream():
        try:
            engine = _ai_engine()
            for kind, payload in engine.ask_stream(DRAFT_ROOT, query):
                if kind == "text":
                    yield f"data: {json.dumps({'type': 'text', 'text': payload})}\n\n"
                elif kind == "citations":
                    yield f"data: {json.dumps({'type': 'citations', 'citations': payload})}\n\n"
                elif kind == "error":
                    yield f"data: {json.dumps({'type': 'error', 'error': payload})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/reindex_ai")
def api_reindex_ai(body: ReindexAIBody | None = None):
    """Rebuild the RAG vector index from draft docs (for the Ask feature)."""
    logger.info("Reindex AI requested")
    try:
        mode = ((body.mode if body else "quick") or "quick").strip().lower()
        if mode not in ("quick", "deep"):
            return {"ok": False, "error": "Invalid mode. Use quick or deep.", "logs": []}
        result = subprocess.run(
            [sys.executable, str(DRAFT_ROOT / "scripts" / "index_for_ai.py"), "--profile", mode, "-v"],
            cwd=str(DRAFT_ROOT),
            capture_output=True,
            text=True,
            timeout=1800,
            env=os.environ.copy(),
        )
        logs = _pull_log_lines(result.stdout or "", result.stderr or "")
        n = 0
        for line in logs:
            if line.startswith("Indexed ") and line.endswith(" chunks."):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    n = int(parts[1])
                break
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "AI reindex failed.").strip()
            return {"ok": False, "error": err, "logs": logs}
        label = "deep (nomic)" if mode == "deep" else "quick"
        if not logs:
            logs = [f"Rebuilding AI index ({label})…", f"Indexed {n} chunks."]
        return {"ok": True, "indexed": n, "mode": mode, "logs": logs}
    except Exception as e:
        return {"ok": False, "error": str(e), "logs": [f"Error: {e}"]}


@app.get("/api/search")
def api_search(q: str = ""):
    """Full-text search over indexed .md documents. Requires index (build via Pull or /api/reindex)."""
    try:
        search_index = _search_module()
        search_index.ensure_index(DRAFT_ROOT)
        results = search_index.search(DRAFT_ROOT, q, limit=50)
        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@app.post("/api/reindex")
def api_reindex():
    """Rebuild the full-text search index from current draft documents."""
    try:
        search_index = _search_module()
        count = search_index.build_index(DRAFT_ROOT)
        return {"ok": True, "indexed": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _pull_log_lines(stdout: str, stderr: str) -> list[str]:
    """Split stdout/stderr into lines for the system console."""
    lines = []
    if stdout:
        lines.extend(s for s in stdout.replace("\r", "\n").splitlines() if s.strip())
    if stderr:
        lines.extend(s for s in stderr.replace("\r", "\n").splitlines() if s.strip())
    return lines


@app.post("/api/pull")
def api_pull():
    """Run scripts/pull.py to refresh docs from managed repos (quiet = summary for UI)."""
    logger.info("Pull requested")
    try:
        result = subprocess.run(
            [sys.executable, str(DRAFT_ROOT / "scripts" / "pull.py"), "-q"],
            cwd=str(DRAFT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        logs = _pull_log_lines(stdout, stderr)
        if result.returncode == 0:
            out = stdout.strip()
            try:
                search_index = _search_module()
                count = search_index.build_index(DRAFT_ROOT)
                logs.append(f"Search index rebuilt: {count} document(s).")
            except Exception:
                pass
            return {"ok": True, "message": out or "Pull complete.", "logs": logs}
        err = (stderr or stdout or "Pull failed.").strip()
        return {"ok": False, "error": err, "logs": logs}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Pull timed out.", "logs": ["Pull timed out."]}
    except Exception as e:
        return {"ok": False, "error": str(e), "logs": [f"Error: {e}"]}


class AddSourceBody(BaseModel):
    source: str = ""


@app.post("/api/add_source")
def api_add_source(body: AddSourceBody):
    """Add a source (GitHub URL or local path). Same logic as pull.py -a. Verifies sources.yaml after add."""
    try:
        source = (body.source or "").strip()
        if not source:
            return {"ok": False, "error": "Missing source.", "logs": []}
        result = subprocess.run(
            [sys.executable, str(DRAFT_ROOT / "scripts" / "pull.py"), "-a", source, "-q"],
            cwd=str(DRAFT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        logs = _pull_log_lines(stdout, stderr)
        if result.returncode != 0:
            err = (stderr or stdout or "Add failed.").strip()
            return {"ok": False, "error": err, "logs": logs}
        # Mandatory verify after add
        from lib.verify_sources import verify_sources_yaml
        path = get_sources_yaml_path()
        ok, errors, warnings = verify_sources_yaml(path)
        for w in warnings:
            logs.append(f"Verify: {w}")
        if not ok:
            return {"ok": False, "error": "sources.yaml invalid after add: " + "; ".join(errors), "logs": logs}
        # Build RAG index if LLM is configured so Ask works
        try:
            from lib.ai_engine import llm_ready
            if llm_ready(DRAFT_ROOT):
                logs.append("Building RAG index...")
                index_result = subprocess.run(
                    [sys.executable, str(DRAFT_ROOT / "scripts" / "index_for_ai.py")],
                    cwd=str(DRAFT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=os.environ.copy(),
                )
                if index_result.stdout:
                    for line in (index_result.stdout or "").strip().splitlines():
                        if line.strip():
                            logs.append(line.strip())
                if index_result.returncode == 0:
                    logs.append("Done.")
                else:
                    err = (index_result.stderr or index_result.stdout or "RAG index build failed.").strip()
                    logs.append("RAG index error: " + err)
        except Exception as e:
            logs.append("RAG index: " + str(e))
        return {"ok": True, "message": stdout.strip() or "Source added.", "logs": logs}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Add timed out.", "logs": ["Add timed out."]}
    except Exception as e:
        return {"ok": False, "error": str(e), "logs": [f"Error: {e}"]}


class RemoveSourceBody(BaseModel):
    name: str = ""


@app.post("/api/remove_source")
def api_remove_source(body: RemoveSourceBody):
    """Remove a tracked source by name: sources.yaml entry + .doc_sources folder + metadata indexes."""
    logs: list[str] = []
    try:
        name = (body.name or "").strip()
        if not name:
            return {"ok": False, "error": "Missing source name.", "logs": logs}
        if name == VAULT_DIR:
            return {"ok": False, "error": "Vault cannot be removed.", "logs": logs}

        sources_yaml = ensure_sources_yaml(DRAFT_ROOT)
        repos = _parse_repos_yaml(sources_yaml)
        if name not in repos:
            return {"ok": False, "error": f"Source '{name}' is not tracked.", "logs": logs}

        backup_text = sources_yaml.read_text(encoding="utf-8")
        removed = _remove_repo_from_sources_yaml(sources_yaml, name)
        if not removed:
            return {"ok": False, "error": f"Could not remove '{name}' from sources.yaml.", "logs": logs}
        logs.append(f"Removed '{name}' from sources.yaml.")

        # Verify sources.yaml after removal; rollback if invalid.
        from lib.verify_sources import verify_sources_yaml
        ok, errors, warnings = verify_sources_yaml(sources_yaml)
        for w in warnings:
            logs.append(f"Verify: {w}")
        if not ok:
            sources_yaml.write_text(backup_text, encoding="utf-8")
            return {"ok": False, "error": "sources.yaml invalid after remove: " + "; ".join(errors), "logs": logs}

        doc_sources_root = _doc_sources_root().resolve()
        repo_dir = (doc_sources_root / name).resolve()
        if repo_dir.exists():
            try:
                repo_dir.relative_to(doc_sources_root)
            except ValueError:
                return {"ok": False, "error": "Unsafe source directory path.", "logs": logs}
            if repo_dir.is_dir():
                shutil.rmtree(repo_dir)
            else:
                repo_dir.unlink()
            logs.append(f"Removed folder: {repo_dir}")
        else:
            logs.append(f"Folder not found (already removed): {repo_dir}")

        # Clean vault source tags for removed source (metadata layer).
        try:
            removed_refs = _remove_vault_source_refs(get_vault_root(), name)
            if removed_refs:
                logs.append(f"Removed {removed_refs} vault source tag(s).")
        except Exception as e:
            logs.append(f"Vault metadata warning: {e}")

        # Refresh metadata layer.
        try:
            from lib.manifest import update_manifest
            update_manifest(DRAFT_ROOT)
            logs.append("Manifest updated.")
        except Exception as e:
            logs.append(f"Manifest update warning: {e}")

        try:
            search_index = _search_module()
            count = search_index.build_index(DRAFT_ROOT)
            logs.append(f"Search index rebuilt: {count} document(s).")
        except Exception as e:
            logs.append(f"Search index warning: {e}")

        try:
            from lib.ai_engine import llm_ready
            if llm_ready(DRAFT_ROOT):
                logs.append("Building RAG index...")
                index_result = subprocess.run(
                    [sys.executable, str(DRAFT_ROOT / "scripts" / "index_for_ai.py")],
                    cwd=str(DRAFT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=os.environ.copy(),
                )
                if index_result.stdout:
                    for line in (index_result.stdout or "").strip().splitlines():
                        if line.strip():
                            logs.append(line.strip())
                if index_result.returncode == 0:
                    logs.append("Done.")
                else:
                    err = (index_result.stderr or index_result.stdout or "RAG index build failed.").strip()
                    logs.append("RAG index warning: " + err)
        except Exception as e:
            logs.append("RAG index warning: " + str(e))

        return {"ok": True, "message": f"Removed source '{name}'.", "logs": logs}
    except Exception as e:
        return {"ok": False, "error": str(e), "logs": logs + [f"Error: {e}"]}


def _safe_vault_basename(name: str) -> str:
    """Return a safe basename for vault (no path traversal, no empty)."""
    base = Path(name).name.strip()
    return base or "uploaded"


def _vault_dest_path(vault_root: Path, name: str) -> Path:
    """Choose a path under vault for an uploaded file. Append-only: never overwrite; use a numeric suffix if name exists."""
    dest = vault_root / name
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    n = 1
    while True:
        dest = vault_root / f"{stem}_{n}{suffix}"
        if not dest.exists():
            return dest
        n += 1


class VaultSaveFromDocBody(BaseModel):
    repo: str
    path: str


class VaultRemoveBody(BaseModel):
    path: str


@app.post("/api/vault/save-from-doc")
def api_vault_save_from_doc(body: VaultSaveFromDocBody):
    """Copy the current document (repo/path) into the vault. Fails if path is invalid or not an allowed doc type."""
    if ".." in body.path or body.path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    if body.repo == VAULT_DIR:
        raise HTTPException(status_code=400, detail="Document is already in vault")
    repo_root = _doc_sources_root() / body.repo
    full = (repo_root / body.path).resolve()
    try:
        full.relative_to(repo_root.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Not found")
    suffix = full.suffix.lower()
    if not full.is_file() or suffix not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Not found")
    name = _safe_vault_basename(full.name)
    vault_root = get_vault_root()
    vault_root.mkdir(parents=True, exist_ok=True)
    dest = _vault_dest_path(vault_root, name)
    try:
        content = full.read_bytes()
        dest.write_bytes(content)
        rel_path = dest.relative_to(vault_root).as_posix()
        _write_vault_source(vault_root, rel_path, body.repo)
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "saved": [dest.name]}


@app.post("/api/vault/remove")
def api_vault_remove(body: VaultRemoveBody):
    """Remove one file from vault by relative path and clean vault source metadata entry."""
    rel_path = (body.path or "").strip()
    if not rel_path:
        return {"ok": False, "error": "Missing path.", "logs": []}
    if ".." in rel_path or rel_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    vault_root = get_vault_root()
    full = (vault_root / rel_path).resolve()
    try:
        full.relative_to(vault_root.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not full.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    logs: list[str] = []
    try:
        full.unlink()
        logs.append(f"Removed vault file: {rel_path}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Remove source metadata for this specific vault file if present.
    try:
        source_map_path = vault_root / VAULT_SOURCES_FILENAME
        source_map = _read_vault_sources(vault_root)
        if rel_path in source_map:
            source_map.pop(rel_path, None)
            source_map_path.write_text(json.dumps(source_map, indent=2), encoding="utf-8")
            logs.append("Removed vault source tag.")
    except Exception as e:
        logs.append(f"Vault metadata warning: {e}")

    # Refresh search and optional RAG index so metadata/search layer stays in sync.
    try:
        search_index = _search_module()
        count = search_index.build_index(DRAFT_ROOT)
        logs.append(f"Search index rebuilt: {count} document(s).")
    except Exception as e:
        logs.append(f"Search index warning: {e}")

    try:
        from lib.ai_engine import llm_ready
        if llm_ready(DRAFT_ROOT):
            logs.append("Building RAG index...")
            index_result = subprocess.run(
                [sys.executable, str(DRAFT_ROOT / "scripts" / "index_for_ai.py")],
                cwd=str(DRAFT_ROOT),
                capture_output=True,
                text=True,
                timeout=600,
                env=os.environ.copy(),
            )
            if index_result.stdout:
                for line in (index_result.stdout or "").strip().splitlines():
                    if line.strip():
                        logs.append(line.strip())
            if index_result.returncode == 0:
                logs.append("Done.")
            else:
                err = (index_result.stderr or index_result.stdout or "RAG index build failed.").strip()
                logs.append("RAG index warning: " + err)
    except Exception as e:
        logs.append("RAG index warning: " + str(e))

    return {"ok": True, "removed": [rel_path], "logs": logs}


@app.post("/api/vault/upload")
async def api_vault_upload(files: list[UploadFile] = File(default=[])):
    """Copy uploaded files into ~/.draft/vault (or DRAFT_HOME/vault). Vault is append-only: no delete; existing names get a numeric suffix."""
    if not files:
        return {"ok": False, "error": "No files uploaded.", "saved": []}
    vault_root = get_vault_root()
    vault_root.mkdir(parents=True, exist_ok=True)
    saved = []
    errors = []
    for uf in files:
        name = _safe_vault_basename(uf.filename or "uploaded")
        if not name:
            continue
        dest = _vault_dest_path(vault_root, name)
        try:
            content = await uf.read()
            dest.write_bytes(content)
            rel_path = dest.relative_to(vault_root).as_posix()
            _write_vault_source(vault_root, rel_path, "upload")
            saved.append(dest.name)
        except Exception as e:
            errors.append(f"{name}: {e}")
    if errors and not saved:
        return {"ok": False, "error": "; ".join(errors), "saved": []}
    return {"ok": True, "saved": saved, "error": "; ".join(errors) if errors else None}


@app.get("/api/doc/{repo}/{path:path}")
def api_doc(repo: str, path: str):
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    if repo == VAULT_DIR:
        repo_root = get_vault_root()
    else:
        repo_root = _doc_sources_root() / repo
    full = repo_root / path
    try:
        full = full.resolve()
        full.relative_to(repo_root.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Not found")
    suffix = full.suffix.lower()
    if not full.is_file() or suffix not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Not found")
    media_type = DOC_CONTENT_TYPES.get(suffix, "application/octet-stream")
    try:
        if suffix in (".md", ".txt"):
            return PlainTextResponse(
                full.read_text(encoding="utf-8", errors="replace"),
                media_type=media_type,
            )
        content = full.read_bytes()
        return Response(content=content, media_type=media_type)
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")


app.mount("/assets", StaticFiles(directory=Path(__file__).parent / "assets"), name="assets")
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
