#!/usr/bin/env bash
# Test Ask (AI) endpoint with curl. Start the server first: python scripts/serve.py
# Uses local Ollama model (default qwen3:8b) unless .env sets DRAFT_LLM_PROVIDER + cloud keys.
set -e
BASE="${1:-http://127.0.0.1:8058}"
echo "Testing POST $BASE/api/ask (model: OLLAMA_MODEL or qwen3:8b)"
echo "---"
curl -s -X POST "$BASE/api/ask" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is this project?"}' | head -50
echo ""
echo "--- (first 50 lines of SSE stream above)"
