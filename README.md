# Plexe Marketplace Ops Agent

An AI agent, served behind a REST API, that answers an ops person's plain-language
questions about **orders, sellers, and reviews** by calling tools — and grounds every
answer in what those tools actually returned.

```
"Where is order ORD1002?" 
   -> agent calls lookup_order("ORD1002")
   -> tool returns {status: "delayed", delay_reason: "inventory shortage", ...}
   -> agent answers using only that data, and returns the tool call as a "receipt"
```

---

## 1. Setup — from zero, step by step

You need: Python 3.11+ and an Anthropic API key (https://console.anthropic.com/).

```bash
# 1. Unzip and enter the project
cd plexe-marketplace-agent

# 2. Create a virtual environment (keeps dependencies isolated)
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API key
cp .env.example .env
# open .env and paste your real key after ANTHROPIC_API_KEY=
export $(cat .env | xargs)      # loads .env into your shell (macOS/Linux)
#   on Windows (PowerShell): Get-Content .env | ForEach-Object { if ($_ -match '(.+?)=(.+)') { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }

# 5. Run the API server
uvicorn src.serve:app --reload --port 8000
```

You should see `Uvicorn running on http://0.0.0.0:8000`. Leave this running.

### Test it (in a second terminal)

```bash
chmod +x test_api.sh
./test_api.sh
```

Or a single manual call:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is order ORD1001?"}'
```

You can also open **http://localhost:8000/docs** for an interactive Swagger UI —
easiest way to try questions without curl.

### Run the eval set

```bash
python -m evals.run_evals
```

This fires 10 example questions at the agent and prints the answer + full tool
trace for each, so you can eyeball groundedness and refusal behavior.

### Run with Docker (optional)

```bash
docker build -t plexe-agent .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-your-key plexe-agent
```

---

## 2. Design

### 2.1 Tools

I chose **three** small, narrow tools rather than two broader ones or a
sprawling toolkit:

| Tool | Input | Output |
|---|---|---|
| `lookup_order(order_id: str)` | order id | `{ok, found, order?, message?}` — order status, buyer, seller_id, item, dates, amount |
| `search_reviews(seller_id: str)` | seller id | `{ok, found, review_count?, reviews?, message?}` |
| `get_seller_info(seller_id: str)` | seller id | `{ok, found, seller?, message?}` — name, rating, join date, order volume |

**Why three, not two:** the brief's own examples (`lookup_order`,
`search_reviews`) don't cover "is this seller trustworthy," which is one of
the ops team's stated pain points ("why is this seller getting bad
reviews?"). Splitting seller *profile* (`get_seller_info`) from seller
*reviews* (`search_reviews`) means a question like "what's this seller's
rating" doesn't have to pull every review text, and a question about
reviews doesn't need the profile — smaller, single-purpose tools are easier
to test and easier for the model to pick correctly. I ruled out a single
`get_seller(seller_id, include_reviews: bool)` tool because a boolean flag
in a tool contract pushes a decision onto the model that's cheaper to make
by just exposing two tools — the schema itself should make correct usage
obvious.

**Why not more:** the assignment explicitly warns against a "sprawling"
toolset. Order/seller/review lookups cover the ops team's stated questions
("where's this order," "why is this seller getting bad reviews," "draft a
reply to this buyer" — which needs order lookup first). I didn't add things
like `issue_refund` or `contact_seller` because those are write actions with
real consequences — out of scope for a v1 that's explicitly about answering
questions, and a much bigger trust/guardrail problem than read-only lookups.

**Contract discipline:** every tool returns a consistent shape —
`{"ok": bool, "found": bool, ...}` for the read tools, or an `"error"` key
on the (rare) hard failures. The model never has to guess whether an empty
result means "not found" vs. "the call broke"; those are different, clearly
labeled states. This is what the assignment means by "a tool with a fuzzy
contract is a bug factory" — I wanted a human (or the model) to be able to
read a result and immediately know which of three things happened: found,
not-found, or errored.

### 2.2 The control loop

Implemented in `src/agent.py::run_agent`, using Anthropic's native tool-use
(`tools=[...]` on `messages.create`), not a framework like LangChain.

**Why raw SDK, not a framework:** the assignment explicitly says "if you use
a framework, be ready to explain what it's doing under the hood — 'the
library handles it' is not an answer we accept." For a 2-3 tool agent, the
loop is ~15 lines: call the model, check `stop_reason`, if it's `tool_use`
run the tool(s) and feed results back as `tool_result` blocks, repeat. A
framework buys nothing here except a layer I'd have to explain anyway, so I
wrote the loop directly and can walk through every line at the debrief.

**How it decides what to do and when it's done:**
1. Send the conversation to Claude with the tool schemas attached.
2. If `response.stop_reason == "tool_use"` — the model asked for one or more
   tool calls. Run each one, append the results as `tool_result` blocks, and
   loop back to step 1 so the model can use those results.
3. If `response.stop_reason != "tool_use"` — the model produced a text
   answer with no further tool calls requested. That's the final answer;
   stop.

**What stops it from looping forever:**
- `MAX_TOOL_STEPS` (default 4) hard-caps the number of model round-trips.
  If the model is still asking for tools after the cap, the loop exits and
  returns a partial answer plus whatever was actually grounded, rather than
  spinning.
- A wall-clock timeout (`REQUEST_TIMEOUT_SECONDS`, default 30s) is checked
  at the top of every loop iteration, so a slow model/tool combination can't
  hang the request indefinitely.
- `max_tokens` is capped per call (`MAX_OUTPUT_TOKENS`), bounding spend per
  turn regardless of steps.

I considered letting the model decide when to stop with no cap ("it'll
naturally converge") — that's the "anyone can wire up one happy path" trap
the assignment warns about. A model can get stuck re-querying, especially
with ambiguous ids or multi-hop questions; a hard cap is the cheap, boring
fix and it's non-negotiable for anything that touches a paid API in
production.

### 2.3 What "grounded" means here

Grounding is enforced at three layers, not just "a good prompt":

1. **System prompt contract** (`SYSTEM_PROMPT` in `agent.py`): explicit
   rules — never state a fact without a tool result backing it; report
   `found: false` as "doesn't exist," not silence; report tool errors as
   errors, not a smoothed-over guess; refuse out-of-scope questions.
   This is necessary but *not sufficient* on its own — a prompt is a
   request, not a guarantee, which is why the next two layers exist.

2. **Structural enforcement**: the model can only get facts via tool calls
   with defined schemas — there's no "just answer directly with data" path
   that bypasses a tool, because the tools are the only source of order/
   seller/review data the model has been given in the conversation at all.
   It literally cannot cite a real order id it invented, because inventing
   one doesn't put that data into its context — only a `lookup_order` call
   does.

3. **The trace as an audit trail (the "receipts")**: every API response
   includes `trace`: the exact tool name, arguments, and raw result for
   every call made. This is the actual mechanism for catching an ungrounded
   claim — if the final answer says something the trace doesn't support, a
   human reviewer (or an automated checker, see "what I'd add") can see that
   mismatch directly instead of having to trust the model's word for it.

**What I did *not* build, and why:** a fully automated "does every claim in
the answer trace back to a tool result" checker (e.g. re-prompting a second
model to verify each sentence against the trace). That's the right next
step for a production version but is real additional engineering — for this
take-home I focused the time budget on making the trace complete and
inspectable, which is the prerequisite for building that checker later.

### 2.4 Robustness — failure modes handled

| Failure mode | Handling |
|---|---|
| Tool errors (simulated backend 500) | `lookup_order("ORD_ERROR")` raises `ToolExecutionError`; caught in `_execute_tool_call`, turned into a structured `{"ok": false, "error": ...}` result fed back to the model with `is_error: True` on the `tool_result` block, so Claude knows to report a failure rather than treat it as "not found." |
| Tool returns nothing / not found | `found: false` is a first-class, distinct state from an error — see 2.1. |
| Model requests a tool that doesn't exist | `_execute_tool_call` checks the name against `TOOL_REGISTRY` and returns an `unknown_tool` error instead of crashing — fed back to the model to self-correct. |
| Model passes bad/malformed arguments | Each tool validates its own inputs (e.g. `order_id` must be a non-empty string) and returns `invalid_argument` rather than raising; a `TypeError` from a totally malformed call is also caught explicitly. |
| Model tries to answer without checking | Prevented structurally (2.3.2) — it has no data to answer *with* unless it called a tool. |
| Out-of-scope / unanswerable questions | Rule 4/5 in the system prompt instructs explicit refusal; the eval set (#9, #10) tests this. |
| Runaway loop / cost | `MAX_TOOL_STEPS`, timeout, and `max_tokens` cap — see 2.2. |
| Unexpected exceptions anywhere in a tool | Caught by a last-resort `except Exception` in `_execute_tool_call` so a bug in one tool can't 500 the whole API. |
| API/network failure calling Claude itself | Caught in the loop, returns a clean error response instead of an unhandled exception reaching the client. |

### 2.5 Serving

FastAPI, one endpoint: `POST /ask`. Chose FastAPI over Flask for built-in
request/response validation via Pydantic (so a malformed request body is
rejected before it reaches the agent) and free OpenAPI docs at `/docs`,
which doubles as a manual testing UI — useful at a live demo.

---

## 3. Evaluation

See `evals/eval_questions.md` for the full table and `evals/run_evals.py` to
run them. Summary of what's covered and why:

- **Groundedness / correct tool use** (Q1, 2, 5, 7): does the agent call the
  right tool(s) and state only what the tool returned?
- **Not-found handling** (Q3, 6): does it clearly say "doesn't exist"
  instead of guessing or staying silent?
- **Hard tool failure** (Q4): does it report a failure instead of
  fabricating a plausible-looking answer to paper over it?
- **Multi-tool orchestration** (Q7): can it chain two tool calls for a
  question that needs both?
- **Grounded generation, not just retrieval** (Q8): "draft a reply" is a
  writing task, but it must still be grounded in a prior `lookup_order`
  call for the real delay reason — this tests that groundedness holds even
  when the final output isn't a plain factual lookup.
- **Guardrails / refusal** (Q9, Q10): out-of-scope and no-tool-available
  questions.

**How I dealt with non-determinism:** the same question can produce
differently-worded (or, rarely, differently-behaved) answers across runs,
because the model is sampled. For this take-home, `run_evals.py` runs each
question once and I inspected the trace by hand — practical given the time
budget. What I'd change for anything beyond a take-home: run each eval
question N times (e.g. 5), score pass/fail per run against the *behavioral*
expectation in the table (called the right tool? refused when it should?),
and report a pass rate rather than a single pass/fail — a question that
fails 1 run in 5 is a real reliability signal a single run hides completely.
I did not build this multi-run harness here to keep the time budget on the
agent itself rather than eval tooling, but the eval table is written so it
already fits into that harness with no redesign.

**What I measured vs. didn't:** I checked tool-choice correctness and
groundedness by manual trace inspection. I did not build an automated
correctness scorer (e.g. exact-match against expected answer strings) —
free-text answers vary in wording even when factually correct, so a naive
string-match would produce false failures; a real scorer would need either
a rubric-based LLM judge or checking that specific required facts (e.g. "the
answer must contain the string 'inventory shortage'") appear, which I'd add
next.

---

## 4. Limitations & what I'd do with more time

- **No automated groundedness checker.** The trace makes ungrounded claims
  *detectable* by a human; it doesn't yet catch them automatically. I'd add
  a lightweight second pass that extracts factual claims from the final
  answer and checks each against the trace's tool results.
- **No conversation memory across requests.** Each `/ask` call is a fresh
  agent run — there's no session/thread concept, so the ops person can't
  ask a follow-up like "and what about their other orders?" referring to
  context from a previous call. Fine for a v1 single-question tool; a real
  ops console would need session state.
- **Mock data only, in-memory.** Swapping in a real orders/reviews service
  means replacing the bodies of the functions in `tools.py` — the schemas
  and the agent loop don't need to change, which is the point of keeping
  the tool contract strict.
- **Single-run evals, not a repeated-trial harness** — see section 3.
- **No auth / rate limiting on the API** — fine for a take-home demo, not
  for anything ops staff would hit directly; I'd add an API key or internal-
  network-only access before any real usage.
- **No retry/backoff on the Anthropic API call itself** (transient network
  errors currently surface as a single clean failure, not a retried
  success) — a straightforward addition, cut for time.

---

## 5. Project structure

```
plexe-marketplace-agent/
├── README.md              <- you are here
├── requirements.txt
├── Dockerfile
├── .env.example
├── test_api.sh             # curl smoke tests
├── src/
│   ├── config.py           # env-driven settings, separated from logic
│   ├── mock_data.py         # fake orders/sellers/reviews
│   ├── tools.py             # tool implementations + validation
│   ├── agent.py             # control loop, guardrails, grounding, system prompt
│   └── serve.py             # FastAPI REST endpoint
├── evals/
│   ├── eval_questions.md    # 10 questions + expected behavior
│   └── run_evals.py         # runs them against the live agent
└── ai_chat_logs/            # AI tool usage log (see its own README)
```
