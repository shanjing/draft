#!/usr/bin/env bash
# Test Ask (AI) endpoint with curl. Start the server first: python scripts/serve.py
# If you see 405, another app is on the port — stop it and run: python scripts/serve.py
set -e
BASE="${1:-http://127.0.0.1:8058}"
echo "1. LLM config at $BASE/api/llm_status"
curl -s "$BASE/api/llm_status" | head -1
echo ""
echo "2. POST $BASE/api/ask (first 30 SSE lines)"
CODE=$(curl -s -o /tmp/ask_out.txt -w "%{http_code}" -X POST "$BASE/api/ask" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is this project?"}')
echo "HTTP $CODE"
if [ "$CODE" = "200" ]; then
  head -30 /tmp/ask_out.txt
else
  cat /tmp/ask_out.txt
fi
echo ""
echo "--- (if HTTP 405, another process is using the port; run Draft with: python scripts/serve.py)"
