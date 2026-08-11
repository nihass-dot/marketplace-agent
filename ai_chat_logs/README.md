# AI Tool Usage Log

This assignment requires submitting the actual chat history you used to build
this project (Cursor, Claude, ChatGPT, Copilot, etc.) — see the assignment
PDF, section 6.

**Before you submit: export this real conversation and put it in this folder.**

How to export a Claude.ai conversation:
1. Open this conversation in the Claude app / claude.ai.
2. Use the browser "Print" -> "Save as PDF" on the conversation page, OR
   copy the full conversation text into a `.md` file.
3. Save it here as `ai_chat_logs/conversation.pdf` (or `.md`).

If you also used another tool (e.g. asked ChatGPT a clarifying question, used
Copilot autocomplete in your editor), export/screenshot those too and drop
them in this folder, named by tool, e.g. `chatgpt_log.png`.

## What to say in the debrief about this
Be ready to speak to, honestly:
- Which parts came directly from AI suggestions vs. which you rewrote —
  e.g. the exact max-steps loop-termination logic, the tool_result
  `is_error` wiring, and the eval question set are things worth being able
  to explain in your own words line by line, not just "the AI wrote it."
- Any AI suggestion you rejected and why (for example: an early suggestion
  to let the agent call tools in an unbounded loop, or to skip validating
  tool arguments, would both fail the "robustness" requirement in the brief).
- Where you changed structure/naming/behavior after reviewing the output.

This file is a placeholder — Plexe wants your *actual* logs, not this text.
