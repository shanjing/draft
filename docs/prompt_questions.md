# Prompt questions for Draft (MCP design and operations)

Use these questions with Draft’s Ask (or any RAG over this repo) when the draft repo is in `sources.yaml`. They are written so retrieval surfaces the right runbook sections without re-reading all `.md` files.

**Goal:** 90 days later, you don’t recall the details; you ask Draft these questions and get back the core MCP design and operation guidance from the docs.

---

## Local Kubernetes and sources

- How does Draft when running in local Kubernetes manage sources?
- Where do I configure document sources for the MCP server in Kubernetes?
- What is the recommended way to give the Helm-deployed MCP server its list of repos and doc directories?
- The pod’s DRAFT_HOME is empty after install; how do I bootstrap sources and docs so list_sources and retrieve_chunks work?
- What is values.local.yaml and when do I use it?
- How do I mount host document directories into the Draft pod and point sources.yaml at them?
- What are sourcesConfig and docSources in the Helm chart?

---

## MCP design and architecture

- Why is retrieve_chunks the primary MCP tool for LLM clients instead of query_docs?
- What is the difference between retrieve_chunks and query_docs and when should I use each?
- Is the MCP server read-only? Can it run pull or add_source?
- How does the MCP server get document content — does it call the UI over HTTP or something else?
- Where does the MCP server read sources and indexes from (DRAFT_HOME, lib, UI)?
- What tools does the Draft MCP server expose and what does each one call under the hood?
- Why is the package named draft_mcp and not mcp?
- How does the SRE runbook use case work with the MCP server (retrieve_chunks flow)?

---

## MCP operations: running and auth

- How do I run the MCP server locally (HTTP vs stdio)?
- What transports does the Draft MCP server support and which needs a Bearer token?
- How do I get the MCP Bearer token and where do I set it?
- How do I call the MCP server over HTTP with curl — what headers and what order of calls?
- Why do I need to call initialize before tools/call and what is Mcp-Session-Id?
- Where are MCP server logs written and how do I get JSON log lines?
- How do I connect Claude Desktop to the Draft MCP server (stdio config)?
- What does the /health endpoint return and what do llm_ready and index_ready mean?
- If retrieve_chunks returns empty content, what should I check (index_ready, bootstrap)?

---

## Kubernetes and Docker

- How do I deploy the MCP server to Kubernetes and what does the Helm chart deploy?
- How do I get the MCP token from the cluster after installing with Helm?
- How do I run the RAG indexer inside the Draft pod after bootstrap so index_ready becomes true?
- Does the Draft container need to be restarted when I change embed or LLM config?
- Where does the vector store and Hugging Face cache live in the container and how do I persist them?
- How much disk do I need for DRAFT_HOME and HF cache when running in Kubernetes?
- How do I run the MCP server in Docker with my existing ~/.draft and .env?

---

## Scripts and testing

- What does sre.sh do and how do I use it against the MCP server?
- For local Kubernetes with port-forward, how do I point sre.sh at the server and match the token?
- How do I test the MCP server with curl (list_sources, retrieve_chunks, auth, session)?
- Where are the MCP integration tests and what do they require (server, token, index)?

---

## Cloud and future extensions

- Is the design ready for S3 or other cloud doc roots with minimal code change?
- How would we add a new source type like S3 without rewriting the whole pipeline?
- Where is the single place that resolves where document content is read from (effective repo root)?

---

## Quick reference (what to ask when…)

| I want to… | Ask Draft… |
|------------|------------|
| Set up sources in local K8s | “How does Draft when running in local Kubernetes manage sources?” |
| Understand why chunks are empty in K8s | “The pod’s DRAFT_HOME is empty after install; how do I bootstrap sources and docs?” |
| Use LLM with MCP correctly | “Why is retrieve_chunks the primary MCP tool for LLM clients instead of query_docs?” |
| Call MCP from curl/script | “How do I call the MCP server over HTTP with curl — what headers and what order of calls?” |
| Get the token from the cluster | “How do I get the MCP token from the cluster after installing with Helm?” |
| Run indexer in the pod | “How do I run the RAG indexer inside the Draft pod after bootstrap?” |
| Add S3 later | “Is the design ready for S3 or other cloud doc roots with minimal code change?” |
