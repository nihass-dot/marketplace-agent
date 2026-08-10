#!/usr/bin/env bash
# Quick smoke test for the running API.
# Usage: ./test_api.sh   (make sure the server is already running on :8000)

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "1) Health check"
curl -s "$BASE_URL/health"
echo -e "\n"

echo "2) Grounded order lookup"
curl -s -X POST "$BASE_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is order ORD1001?"}' | python3 -m json.tool
echo -e "\n"

echo "3) Not-found handling (should NOT invent an order)"
curl -s -X POST "$BASE_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the status of order ORD9999?"}' | python3 -m json.tool
echo -e "\n"

echo "4) Tool failure handling"
curl -s -X POST "$BASE_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Look up order ORD_ERROR"}' | python3 -m json.tool
echo -e "\n"

echo "5) Out-of-scope refusal"
curl -s -X POST "$BASE_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}' | python3 -m json.tool
echo -e "\n"

echo "6) Multi-tool orchestration"
curl -s -X POST "$BASE_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Give me a full profile of seller SEL01 including rating and recent reviews."}' | python3 -m json.tool
