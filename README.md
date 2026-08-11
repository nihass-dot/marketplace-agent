# Plexe Marketplace Agent

A small production-style AI agent for an online marketplace operations team.

The agent can answer questions about **orders, sellers, and reviews** by deciding which local tools to call and then generating a grounded response from the retrieved data.

## Features

* LLM-powered agent loop
* Gemini as the primary LLM
* Groq as the fallback LLM
* Local marketplace tools for:

  * Order lookup
  * Seller information
  * Seller reviews
* Duplicate tool-call prevention
* Tool execution error handling
* Provider fallback handling
* Request timeout / maximum tool-step guardrails
* REST API using FastAPI
* Docker support
* Evaluation script with checkpointing

## Project Structure

```text
plexe-marketplace-agent/
│
├── README.md
├── requirements.txt
├── Dockerfile
├── .env
│
├── src/
│   ├── agent.py
│   ├── serve.py
│   ├── config.py
│   └── tools.py
│
├── evals/
│   ├── eval_questions.md
│   ├── run_evals.py
│   └── checkpoint.json
│
└── ai_chat_logs/
```

## How It Works

The agent follows this flow:

```text
User Request
     │
     ▼
LLM Provider
     │
     ├── Gemini (Primary)
     │
     └── Groq (Fallback)
     │
     ▼
Tool Selection
     │
     ├── lookup_order
     ├── get_seller_info
     └── search_reviews
     │
     ▼
Local Tool Execution
     │
     ▼
Verified Tool Results
     │
     ▼
LLM Final Response
```

Marketplace facts are obtained from the local tools rather than being hardcoded into the agent's responses.

## LLM Providers

The configured provider order is:

```text
Gemini → Groq
```

If the primary provider encounters a recognized provider failure such as an API failure, rate limit, timeout, or service unavailability, the agent attempts to use the fallback provider.

Provider configuration is controlled through environment variables.

Example `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key

PRIMARY_LLM=gemini
FALLBACK_LLM=groq
```

Other model and runtime settings are configured in `src/config.py`.

## Installation

Python 3.11 is used for the Docker image.

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a `.env` file and configure the required API keys.

## Run the API

Start the FastAPI application with:

```powershell
uvicorn src.serve:app --host 0.0.0.0 --port 8000
```

The API will be available at:

```text
http://localhost:8000
```

The API can also be tested through Postman.

## Example API Request

Example request:

```http
POST /chat
Content-Type: application/json
```

```json
{
  "question": "What seller is associated with order ORD1001 and what reviews does that seller have?"
}
```

Example response:

```json
{
  "answer": "The seller associated with order ORD1001 is SEL01. This seller has 2 reviews. The reviews are as follows: ...",
  "trace": [
    {
      "step": 1,
      "tool": "lookup_order",
      "arguments": {
        "order_id": "ORD1001"
      }
    },
    {
      "step": 1,
      "tool": "search_reviews",
      "arguments": {
        "seller_id": "SEL01"
      }
    }
  ],
  "steps_used": 2,
  "stopped_reason": "completed"
}
```

The response includes the final answer together with the tool trace so the agent's behavior can be inspected.

## Agent Guardrails

The agent is designed to keep an unpredictable LLM component bounded.

### Grounded responses

Marketplace facts must come from tool results.

The system prompt instructs the model not to invent:

* Order information
* Seller information
* Reviews
* Ratings
* Dates
* Buyers
* Products
* Delivery information

### Tool error handling

Tool failures are converted into structured results instead of crashing the agent.

For example:

```json
{
  "ok": false,
  "error": "tool_execution_error",
  "message": "orders-service returned 500"
}
```

### Duplicate tool-call prevention

Executed tool calls are tracked using a stable key based on:

```text
tool name + arguments
```

This prevents the same tool request from being executed repeatedly.

### Maximum steps and timeout

The agent has configurable limits for:

* Maximum tool steps
* Request execution time

This prevents an LLM from remaining in a tool-calling loop indefinitely.

## Evaluation

The evaluation questions are defined in:

```text
evals/eval_questions.md
```

Run the evaluations with:

```powershell
python .\evals\run_evals.py
```

The evaluator runs each question once and prints:

* Question
* Final answer
* Stopped reason
* Number of steps
* Tool trace

A checkpoint file is used so already completed questions are not unnecessarily executed again.

To run all evaluations again, remove:

```text
evals/checkpoint.json
```

and run:

```powershell
python .\evals\run_evals.py
```

### Example evaluation coverage

The evaluation set covers:

1. Order lookup
2. Delayed order explanation
3. Missing order
4. Tool execution error
5. Seller reviews
6. Seller with no reviews
7. Multi-tool seller profile
8. Customer-facing draft
9. Unsupported weather request
10. Unsupported refund-policy request

The completed evaluation run successfully reached:

```text
[1] completed
[2] completed
[3] completed
[4] completed
[5] completed
[6] completed
[7] completed
[8] completed
[9] completed
[10] completed
```

A multi-tool API test was also performed for:

```text
What seller is associated with order ORD1001 and what reviews does that seller have?
```

The agent correctly:

```text
lookup_order → SEL01
search_reviews → SEL01 reviews
final response → completed
```

## Docker

Build the image:

```powershell
docker build -t plexe-marketplace-agent .
```

Run the container:

```powershell
docker run --env-file .env -p 8000:8000 plexe-marketplace-agent
```

The Docker image uses:

```dockerfile
FROM python:3.11-slim
```

and starts the FastAPI application with Uvicorn.

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "src.serve:app", "--host", "0.0.0.0", "--port", "8000"]
```

## AI Conversation Logs

The `ai_chat_logs/` directory contains the AI-assisted development conversation exports requested as part of the submission.

## Design Notes

The implementation intentionally stays small rather than introducing additional infrastructure.

The main reliability mechanisms are:

* Tool-grounded answers
* Structured tool errors
* Duplicate-call prevention
* Provider fallback
* Maximum tool-step limits
* Request timeout
* Evaluation questions for manual inspection
* API and Docker execution paths

The evaluation script currently runs each question once. Because LLM behavior is non-deterministic, a stronger future evaluation would run each question multiple times and calculate a pass rate per question.

## What I Would Improve Next

Given more time, I would add:

* Repeated evaluation runs with pass-rate reporting
* Automated assertions for expected tool usage
* More provider-specific error classification
* Automated API tests
* CI execution of the evaluation suite
* More comprehensive observability and structured logging
