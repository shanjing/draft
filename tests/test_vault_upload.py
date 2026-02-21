"""Test vault file upload API (drag-and-drop target)."""
import pytest


class TestVaultUpload:
    """POST /api/vault/upload copies files to DRAFT_HOME/vault."""

    def test_upload_single_md(self, client, draft_home):
        """Upload one .md file; it appears in vault and tree."""
        content = b"# Test\n\nDropped from MarginCall.\n"
        r = client.post(
            "/api/vault/upload",
            files=[("files", ("test-dropped.md", content, "text/markdown"))],
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert "saved" in data
        assert "test-dropped.md" in data["saved"]
        vault_file = draft_home / "vault" / "test-dropped.md"
        assert vault_file.is_file()
        assert vault_file.read_bytes() == content

    def test_upload_empty_rejected(self, client):
        """No files returns 200 with ok=False."""
        r = client.post("/api/vault/upload", data={})
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is False
        assert "No files uploaded" in data.get("error", "")

    def test_upload_append_only_duplicate_gets_suffix(self, client, draft_home):
        """Same filename twice: second gets _1 suffix (append-only)."""
        content = b"# First"
        r1 = client.post(
            "/api/vault/upload",
            files=[("files", ("dup.md", content, "text/markdown"))],
        )
        assert r1.status_code == 200 and r1.json().get("ok") is True
        assert (draft_home / "vault" / "dup.md").is_file()
        r2 = client.post(
            "/api/vault/upload",
            files=[("files", ("dup.md", b"# Second", "text/markdown"))],
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2.get("ok") is True
        assert "dup_1.md" in data2.get("saved", [])
        assert (draft_home / "vault" / "dup_1.md").is_file()
        assert (draft_home / "vault" / "dup_1.md").read_bytes() == b"# Second"
