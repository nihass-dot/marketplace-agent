# """
# Config for the marketplace agent.

# Everything that might change between environments (model name, limits,
# API key) lives here — never hardcoded inside agent.py.
# """

# import os

# # --- Google Generative AI ---
# GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# MODEL_NAME = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")  # or "claude-sonnet-4.5" for Anthropic

# # --- Control loop limits (this is what stops the agent from running away) ---
# MAX_TOOL_STEPS = int(os.environ.get("MAX_TOOL_STEPS", "4"))       # max tool calls per question
# MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "1024"))
# REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))

# # --- Server ---
# HOST = os.environ.get("HOST", "0.0.0.0")
# PORT = int(os.environ.get("PORT", "8000"))
"""
Application configuration.

Provider/model selection is environment-driven so the agent logic does not
need to change between environments.
"""

import os
from dotenv import load_dotenv

load_dotenv(".env", override=True)

# ---------------------------------------------------------------------------


# LLM PROVIDERS
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

PRIMARY_LLM = os.environ.get("PRIMARY_LLM", "gemini").lower()
FALLBACK_LLM = os.environ.get("FALLBACK_LLM", "groq").lower()


# ---------------------------------------------------------------------------
# AGENT LIMITS
# ---------------------------------------------------------------------------

MAX_TOOL_STEPS = int(
    os.environ.get("MAX_TOOL_STEPS", "4")
)

MAX_OUTPUT_TOKENS = int(
    os.environ.get("MAX_OUTPUT_TOKENS", "1024")
)

REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("REQUEST_TIMEOUT_SECONDS", "30")
)


# ---------------------------------------------------------------------------
# SERVER
# ---------------------------------------------------------------------------

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))