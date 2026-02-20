"""Tests for lib components: chunking, ingest, ai_engine."""
from pathlib import Path

import pytest


class TestChunking:
    """lib.chunking: chunk_markdown produces Chunks with correct metadata."""

    def test_chunk_markdown_returns_list(self):
        from lib.chunking import chunk_markdown
        chunks = chunk_markdown("repo", "path.md", "# Hi\n\nParagraph one.")
        assert isinstance(chunks, list)

    def test_chunk_has_repo_path_heading_text_index(self):
        from lib.chunking import chunk_markdown, Chunk
        chunks = chunk_markdown("vault", "DRAFT.md", "# Draft\n\nDraft is a document mirror.")
        assert len(chunks) >= 1
        c = chunks[0]
        assert isinstance(c, Chunk)
        assert c.repo == "vault"
        assert c.path == "DRAFT.md"
        assert c.chunk_index >= 0
        assert isinstance(c.text, str)
        assert isinstance(c.heading, str)

    def test_chunk_splits_by_headers(self):
        from lib.chunking import chunk_markdown
        md = "## Section A\n\nText A.\n\n## Section B\n\nText B."
        chunks = chunk_markdown("r", "p.md", md)
        assert len(chunks) >= 2 or (len(chunks) == 1 and "Section" in chunks[0].text)


class TestIngest:
    """lib.ingest: should_include, collect_chunks, build_index."""

    def test_should_include_excludes_readme(self):
        from lib.ingest import should_include
        assert should_include("README.md") is False

    def test_should_include_excludes_claude_md(self):
        from lib.ingest import should_include
        assert should_include("docs/CLAUDE.md") is False

    def test_should_include_allows_vault_draft(self):
        from lib.ingest import should_include
        assert should_include("DRAFT.md") is True
        assert should_include("vault/DRAFT.md") is True

    def test_collect_chunks_from_temp_root(self, temp_draft_root):
        from lib.ingest import collect_chunks
        chunks = collect_chunks(temp_draft_root)
        assert len(chunks) >= 1
        assert any(c.repo == "vault" and "DRAFT" in c.path for c in chunks)

    def test_build_index_creates_vector_store(self, temp_draft_root):
        """build_index creates .vector_store and indexes chunks (may be slow: loads embed model)."""
        from lib.ingest import build_index
        n = build_index(temp_draft_root, verbose=False)
        assert n >= 1
        assert (temp_draft_root / ".vector_store").is_dir()


class TestAIEngine:
    """lib.ai_engine: _env_strip, retrieve, ask_stream structure."""

    def test_env_strip_strips_quotes(self):
        import os
        from lib import ai_engine
        os.environ["_TEST_STRIP"] = "  'value'  "
        try:
            assert ai_engine._env_strip("_TEST_STRIP", "") == "value"
        finally:
            os.environ.pop("_TEST_STRIP", None)

    def test_retrieve_empty_when_no_collection(self, temp_draft_root):
        """retrieve returns [] when there is no collection (no index)."""
        from lib.ai_engine import retrieve
        # temp_draft_root has no .vector_store by default
        out = retrieve(temp_draft_root, "test query")
        assert out == []

    def test_retrieve_after_build_index(self, temp_draft_root):
        """After build_index, retrieve returns chunks for a query."""
        from lib.ingest import build_index
        from lib.ai_engine import retrieve
        build_index(temp_draft_root, verbose=False)
        out = retrieve(temp_draft_root, "Draft document mirror")
        assert isinstance(out, list)
        # May have 0 or more depending on embedding
        assert all("repo" in c and "path" in c for c in out)
