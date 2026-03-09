TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d= -f2)
BASE="http://localhost:8059/mcp"
HEADERS=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")

# Initialize session
SESSION=$(curl -si -X POST "$BASE" "${HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r')

echo "Session: $SESSION"

curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "retrieve_chunks",
      "arguments": {
        "query": "How can I investigate resource constraints for a pod by checking its real-time usage against its defined requests and limits?",
        "top_k": 3,
        "rerank": true
      }
    }
  }' | grep '^data:' | cut -c7- | python3 -m json.tool
