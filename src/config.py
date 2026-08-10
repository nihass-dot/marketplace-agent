"""
Config for the marketplace agent.

Everything that might change between environments (model name, limits,
API key) lives here — never hardcoded inside agent.py.
"""

import os

# --- Google Generative AI ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")  # or "claude-sonnet-4.5" for Anthropic

# --- Control loop limits (this is what stops the agent from running away) ---
MAX_TOOL_STEPS = int(os.environ.get("MAX_TOOL_STEPS", "4"))       # max tool calls per question
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "1024"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))

# --- Server ---
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
