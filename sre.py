#!/usr/bin/env python3
"""
sre.py — Draft MCP client for SRE testing.

Picks a random question from tests/sre_questions.md, queries the Draft MCP
server via retrieve_chunks, and prints a human-readable result.

Usage:
    python3 sre.py        # Kubernetes mode: token from kubectl secret
    python3 sre.py -l     # Local mode: token from .env (draft running as daemon)

Both modes assume the server is reachable on http://localhost:8059.
For Kubernetes, run `kubectl -n draft port-forward svc/draft 8059:8059` first.
"""

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

SCRIPT_DIR = Path(__file__).parent
QUESTIONS_FILE = SCRIPT_DIR / "tests" / "sre_questions.md"
ENV_FILE = SCRIPT_DIR / ".env"
DEFAULT_URL = "http://localhost:8059/mcp"
WIDTH = 72
RULE = "━" * WIDTH


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------

def get_token_local() -> str:
    if not ENV_FILE.exists():
        sys.exit(f"error: .env not found at {ENV_FILE}")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("DRAFT_MCP_TOKEN="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    sys.exit("error: DRAFT_MCP_TOKEN not found in .env")


def get_token_k8s() -> str:
    try:
        raw = subprocess.check_output(
            ["kubectl", "-n", "draft", "get", "secret", "draft",
             "-o", "jsonpath={.data.DRAFT_MCP_TOKEN}"],
            stderr=subprocess.DEVNULL,
        )
        import base64
        token = base64.b64decode(raw).decode().strip()
        if not token:
            sys.exit("error: DRAFT_MCP_TOKEN is empty in the Kubernetes secret")
        return token
    except subprocess.CalledProcessError:
        sys.exit(
            "error: could not retrieve secret from Kubernetes.\n"
            "  Is kubectl configured and is `kubectl -n draft port-forward svc/draft 8059:8059` running?"
        )
    except FileNotFoundError:
        sys.exit("error: kubectl not found — is it installed and on PATH?")


# ---------------------------------------------------------------------------
# Question selection
# ---------------------------------------------------------------------------

def pick_question() -> str:
    if not QUESTIONS_FILE.exists():
        sys.exit(f"error: questions file not found: {QUESTIONS_FILE}")
    questions = [
        line[3:].strip()
        for line in QUESTIONS_FILE.read_text().splitlines()
        if line.startswith("## ")
    ]
    if not questions:
        sys.exit(f"error: no questions found in {QUESTIONS_FILE}")
    return random.choice(questions)


# ---------------------------------------------------------------------------
# MCP query
# ---------------------------------------------------------------------------

async def query_draft(url: str, token: str, question: str):
    headers = {"Authorization": f"Bearer {token}"}
    t0 = time.perf_counter()
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "retrieve_chunks",
                {"query": question, "top_k": 3, "rerank": True},
            )
    latency = time.perf_counter() - t0

    if result.isError:
        content_text = result.content[0].text if result.content else "(no error detail)"
        sys.exit(f"error: MCP server returned an error:\n  {content_text}")

    # Prefer structuredContent; fall back to parsing content[*].text as JSON
    if result.structuredContent and "result" in result.structuredContent:
        chunks = result.structuredContent["result"]
    else:
        chunks = []
        for item in result.content:
            try:
                chunks.append(json.loads(item.text))
            except (json.JSONDecodeError, AttributeError):
                pass

    return chunks, latency


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def wrap_text(text: str, indent: str = "  ") -> str:
    """Wrap prose lines but preserve code blocks (``` fences) verbatim."""
    lines = text.splitlines()
    output = []
    in_code = False
    para: list[str] = []

    def flush_para():
        if para:
            joined = " ".join(para)
            output.append(
                textwrap.fill(joined, width=WIDTH,
                              initial_indent=indent,
                              subsequent_indent=indent)
            )
            para.clear()

    for line in lines:
        if line.strip().startswith("```"):
            flush_para()
            in_code = not in_code
            output.append(indent + line)
            continue
        if in_code:
            output.append(indent + line)
            continue
        stripped = line.strip()
        if not stripped:
            flush_para()
            output.append("")
        else:
            para.append(stripped)

    flush_para()
    return "\n".join(output)


def fmt_location(chunk: dict) -> str:
    repo = chunk.get("repo", "?")
    path = chunk.get("path", "?")
    heading = chunk.get("heading", "").strip()
    loc = f"{repo} / {path}"
    if heading:
        loc += f"  §  {heading}"
    return loc


def print_section(title: str) -> None:
    print(f"\n{RULE}")
    print(f" {title}")
    print(RULE)


def print_results(question: str, chunks: list, latency: float,
                  url: str, mode: str) -> None:
    if not chunks:
        print_section("ERROR")
        print("  No chunks returned. Is the index built?")
        print("  Run: kubectl -n draft exec deployment/draft -- python scripts/index_for_ai.py --profile quick")
        return

    best = chunks[0]
    score = best.get("score", 0.0)

    # ── QUESTION ────────────────────────────────────────────────────────
    print_section("QUESTION")
    print(wrap_text(question))

    # ── ANSWER ──────────────────────────────────────────────────────────
    print_section(f"ANSWER  ·  {fmt_location(best)}  (score {score:.2f})")
    print(wrap_text(best.get("text", "")))

    # ── ALL RESULTS ─────────────────────────────────────────────────────
    print_section("ALL RESULTS")
    for i, chunk in enumerate(chunks, 1):
        s = chunk.get("score", 0.0)
        loc = fmt_location(chunk)
        snippet = chunk.get("text", "").replace("\n", " ").strip()
        if len(snippet) > 100:
            snippet = snippet[:100] + "…"
        print(f"  {i}. [{s:+.2f}]  {loc}")
        print(f"       {snippet}")
        if i < len(chunks):
            print()

    # ── STATS ───────────────────────────────────────────────────────────
    print_section("STATS")
    print(f"  Mode:      {mode}")
    print(f"  Server:    {url}")
    print(f"  Latency:   {latency:.2f}s")
    print(f"  Results:   {len(chunks)} chunks")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the Draft MCP server with a random SRE question.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-l", "--local",
        action="store_true",
        help="Local mode: Draft runs as a local daemon. Token read from .env. "
             "(Default: Kubernetes mode — token from kubectl secret.)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"MCP server URL (default: {DEFAULT_URL})",
    )
    args = parser.parse_args()

    mode = "local" if args.local else "kubernetes"
    token = get_token_local() if args.local else get_token_k8s()
    question = pick_question()

    chunks, latency = asyncio.run(query_draft(args.url, token, question))
    print_results(question, chunks, latency, args.url, mode)


if __name__ == "__main__":
    main()
