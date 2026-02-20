"""Tests for full-text search API and tree."""
import pytest


class TestSearchAPI:
    """GET /api/search returns results or empty list."""

    def test_search_returns_200(self, client):
        r = client.get("/api/search", params={"q": "Draft"})
        assert r.status_code == 200

    def test_search_returns_results_key(self, client):
        r = client.get("/api/search", params={"q": "Draft"})
        data = r.json()
        assert "results" in data
        assert isinstance(data["results"], list)


class TestTreeAPI:
    """GET /api/tree returns repo list with vault."""

    def test_tree_returns_200(self, client):
        r = client.get("/api/tree")
        assert r.status_code == 200

    def test_tree_has_repos(self, client):
        r = client.get("/api/tree")
        data = r.json()
        assert "repos" in data
        assert isinstance(data["repos"], list)

    def test_tree_includes_vault(self, client):
        """Vault is a shipped source; tree should include it."""
        r = client.get("/api/tree")
        data = r.json()
        names = [repo.get("name") for repo in data.get("repos", [])]
        assert "vault" in names
