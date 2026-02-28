"""Tests for Ask (AI) API and RAG pipeline."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ASK_SCRIPT = REPO_ROOT / "scripts" / "ask.py"


def parse_sse_lines(raw: bytes):
    """Parse SSE data lines from response body."""
    text = raw.decode("utf-8", errors="replace")
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


class TestAskAPI:
    """POST /api/ask returns 200 and SSE stream."""

    def test_ask_accepts_post(self, client):
        """POST /api/ask with valid body returns 200 (not 405)."""
        r = client.post("/api/ask", json={"query": "What is Draft?"})
        assert r.status_code == 200

    def test_ask_response_is_sse(self, client):
        """Response has SSE-style data lines."""
        r = client.post("/api/ask", json={"query": "What is Draft?"})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        events = parse_sse_lines(r.content)
        assert len(events) >= 1
        types = {e.get("type") for e in events}
        assert types & {"text", "citations", "error"}

    def test_ask_empty_query_rejected(self, client):
        """Empty query returns 200 with error message or 422."""
        r = client.post("/api/ask", json={"query": ""})
        if r.status_code == 200:
            data = r.json()
            assert "error" in data
        else:
            assert r.status_code == 422

    def test_ask_stream_contains_citations_or_error(self, client):
        """Stream has citations (if index + LLM) or error."""
        r = client.post("/api/ask", json={"query": "What is the vault?"})
        assert r.status_code == 200
        events = parse_sse_lines(r.content)
        has_citations = any(e.get("type") == "citations" for e in events)
        has_error = any(e.get("type") == "error" for e in events)
        has_text = any(e.get("type") == "text" for e in events)
        assert has_citations or has_error or has_text


class TestLLMStatus:
    """GET /api/llm_status returns provider and model."""

    def test_llm_status_returns_200(self, client):
        r = client.get("/api/llm_status")
        assert r.status_code == 200

    def test_llm_status_has_provider_and_model(self, client):
        r = client.get("/api/llm_status")
        data = r.json()
        assert "provider" in data
        assert "model" in data
        assert data["provider"] in ("ollama", "claude", "gemini", "openai", "")
        assert isinstance(data["model"], str)


class TestAskCLI:
    """scripts/ask.py CLI."""

    def test_ask_cli_help(self):
        """--help works."""
        r = subprocess.run(
            [sys.executable, str(ASK_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode == 0
        assert "-q" in r.stdout or "--query" in r.stdout
        assert "debug" in r.stdout.lower()

    def test_ask_cli_empty_query_exits_nonzero(self):
        """Empty query exits with error."""
        r = subprocess.run(
            [sys.executable, str(ASK_SCRIPT), "-q", ""],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert r.returncode != 0
        assert "empty" in r.stderr.lower() or "error" in r.stderr.lower()
