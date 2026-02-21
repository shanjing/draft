"""
Draft UI: serve document tree and markdown content. Launch with uvicorn.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# Disable Chroma telemetry before any chromadb import (avoids "capture() takes 1 positional argument" error)
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DRAFT_ROOT = Path(__file__).resolve().parent.parent
DOC_SOURCES_DIR = ".doc_sources"
VAULT_DIR = "vault"
if str(DRAFT_ROOT) not in sys.path:
    sys.path.insert(0, str(DRAFT_ROOT))

# Load .env so DRAFT_LLM_* and OLLAMA_MODEL work regardless of how server is started
try:
    from dotenv import load_dotenv
    load_dotenv(DRAFT_ROOT / ".env")
except ImportError:
    pass

from lib.log import logger, configure as configure_log
from lib.paths import get_doc_sources_root, get_vault_root

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


def _paths_to_tree_node(paths: list[str]) -> dict:
    """Build a tree node: { name, type: file|dir, path?, children? }."""
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
        return {"name": name, "type": "file", "path": path}
    return {"name": "", "type": "dir", "children": [to_node(k, v) for k, v in sorted(root.items(), key=lambda x: (0 if isinstance(x[1], dict) else 1, x[0]))]}


def _doc_sources_root() -> Path:
    """Root for repo dirs: ~/.draft/.doc_sources (or DRAFT_HOME)."""
    return get_doc_sources_root()


def get_tree() -> list:
    sources_yaml = DRAFT_ROOT / "sources.yaml"
    if not sources_yaml.is_file():
        return []
    repos = _parse_repos_yaml(sources_yaml)
    doc_sources = _doc_sources_root()
    result = []
    for name in repos:
        if name == VAULT_DIR:
            repo_dir = get_vault_root()
        else:
            repo_dir = doc_sources / name
        if not repo_dir.is_dir():
            continue
        paths = []
        for f in repo_dir.rglob("*.md"):
            try:
                rel = f.relative_to(repo_dir)
                paths.append(rel.as_posix())
            except ValueError:
                continue
        tree = _paths_to_tree_node(paths)
        result.append({
            "name": name,
            "url": repos[name].get("url"),
            "tree": tree["children"],
        })
    return result


app = FastAPI(title="Draft", description="Browse draft documents")

try:
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
def api_reindex_ai():
    """Rebuild the RAG vector index from draft docs (for the Ask feature)."""
    logger.info("Reindex AI requested")
    try:
        from lib.ingest import build_index
        n = build_index(DRAFT_ROOT, verbose=False)
        return {"ok": True, "indexed": n, "logs": ["Rebuilding AI index…", f"Indexed {n} chunks."]}
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
        lines.extend(s for s in stdout.splitlines() if s.strip())
    if stderr:
        lines.extend(s for s in stderr.splitlines() if s.strip())
    return lines


@app.post("/api/pull")
def api_pull():
    """Run scripts/pull.py to refresh docs from managed repos (quiet = summary for UI)."""
    logger.info("Pull requested")
    try:
        result = subprocess.run(
            [sys.executable, str(DRAFT_ROOT / "scripts" / "pull.py"), "--quiet"],
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
            [sys.executable, str(DRAFT_ROOT / "scripts" / "pull.py"), "-a", source, "--quiet"],
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
        path = DRAFT_ROOT / "sources.yaml"
        ok, errors, warnings = verify_sources_yaml(path)
        for w in warnings:
            logs.append(f"Verify: {w}")
        if not ok:
            return {"ok": False, "error": "sources.yaml invalid after add: " + "; ".join(errors), "logs": logs}
        return {"ok": True, "message": stdout.strip() or "Source added.", "logs": logs}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Add timed out.", "logs": ["Add timed out."]}
    except Exception as e:
        return {"ok": False, "error": str(e), "logs": [f"Error: {e}"]}


@app.get("/api/doc/{repo}/{path:path}", response_class=PlainTextResponse)
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
    if not full.is_file() or full.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")


app.mount("/assets", StaticFiles(directory=Path(__file__).parent / "assets"), name="assets")
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
