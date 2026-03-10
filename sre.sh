#!/bin/sh
# a script to test the Draft MCP server from cli
# randomly pick a question from the questions.md, a production related issue
# extract the mcp token from the .env file
# create a session and call the retrieve_chunks tool
# receive chunks from the MCP server per runbooks
# this is a transit step from a sub-agent prospect
# the sub-agent would use LLM along with the chunks to finalize the action
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
QUESTIONS_FILE="${SCRIPT_DIR}/tests/questions.md"

# Extract MCP token from .env (DRAFT_MCP_TOKEN=...); use -f2- in case token contains =
# For local Kubernetes: kubectl port-forward svc/draft 8059:8059 -n draft; .env token must match cluster Secret.
MCP_TOKEN=$(grep -E '^DRAFT_MCP_TOKEN=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r')
if [ -z "$MCP_TOKEN" ]; then echo "DRAFT_MCP_TOKEN not found in .env"; exit 1; fi

# Default: local server or port-forward to local Kubernetes (e.g. k port-forward svc/draft 8059:8059 -n draft)
BASE="${MCP_BASE_URL:-http://localhost:8059/mcp}"

# Pick one question at random (sections in questions.md are separated by ##)
question=$(grep -E '^## ' "$QUESTIONS_FILE" 2>/dev/null | sed 's/^## //' | awk 'BEGIN{srand()}{a[NR]=$0}END{if(NR>0)print a[int(rand()*NR)+1]}')
if [ -z "$question" ]; then echo "No questions found in $QUESTIONS_FILE"; exit 1; fi
echo "Question: $question"

# Initialize session
SESSION=$(curl -si -X POST "$BASE" \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | head -1 | sed 's/.*:[[:space:]]*//' | tr -d '\r\n')

if [ -z "$SESSION" ]; then echo "Failed to get MCP session (is the server running on $BASE?)"; exit 1; fi
echo "Session: $SESSION"

# Call retrieve_chunks with the chosen question (jq escapes the string for JSON)
payload=$(jq -n --arg q "$question" '{
  jsonrpc: "2.0",
  id: 2,
  method: "tools/call",
  params: {
    name: "retrieve_chunks",
    arguments: {
      query: $q,
      top_k: 3,
      rerank: true
    }
  }
}')

curl -s -X POST "$BASE" \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d "$payload" | grep '^data:' | cut -c7- | python3 -m json.tool
