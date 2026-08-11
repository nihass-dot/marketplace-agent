https://chat.z.ai/s/5df333f9-3ccb-4a9d-afec-de22a5341f83
claude prompt can you plan this out then system design and architecture and start implementing it with correct fuctionality as mention and give me copy paste code for it what to according to 1. What we're actually building

The final system will look like this:

                     USER / OPS PERSON
                            |
                            | POST /ask
                            v
                    +----------------+
                    |    FastAPI     |
                    |   REST API     |
                    +-------+--------+
                            |
                            v
                    +----------------+
                    |   AI AGENT     |
                    |                |
                    | 1. Understand  |
                    | 2. Select tool |
                    | 3. Execute     |
                    | 4. Verify     |
                    | 5. Answer     |
                    +---+--------+---+
                        |        |
             -----------         -----------
             |                           |
             v                           v
      +---------------+           +---------------+
      | lookup_order  |           |search_reviews|
      +-------+-------+           +-------+-------+
              |                           |
              v                           v
        Mock order data             Mock seller/review
                                        data
              \                           /
               \                         /
                +----------+-------------+
                           |
                           v
                    GROUNDED ANSWER
                           +
                         TRACE

The important idea is:

The LLM does not have access to our fake database directly. It can only obtain marketplace facts through our tools.

That is exactly aligned with the assignment's requirement that answers be grounded in what the tools actually return rather than what the model guesses.

2. Technology choice

I recommend:

Part	Technology
Language	Python
API	FastAPI
AI	OpenAI API
Agent	Our own Python control loop
Data	In-memory Python dictionaries
Validation	Pydantic
Configuration	.env
Testing	pytest
Container	Docker
API testing	Swagger + curl
Deployment	Optional

Why not LangChain?

Because the assignment specifically says that if you use a framework, you should be able to explain what's happening underneath.

For a 3–5 hour take-home, implementing the loop ourselves is actually better for your interview.

The current OpenAI Python SDK supports the Responses API and custom function tools, so we can use the SDK directly.

3. Features our MVP will have

We'll implement:

Tool 1 — lookup_order

Input:

{
  "order_id": "ORD-1001"
}

Output:

{
  "found": true,
  "order": {
    "order_id": "ORD-1001",
    "buyer": "Alice",
    "seller_id": "SEL-001",
    "status": "shipped",
    "tracking_number": "TRK123456",
    "estimated_delivery": "2026-08-12"
  }
}
Tool 2 — search_reviews

Input:

{
  "seller_id": "SEL-001"
}

Output:

{
  "found": true,
  "seller_id": "SEL-001",
  "average_rating": 2.4,
  "review_count": 5,
  "reviews": [...]
}

These two tools map directly to the assignment's examples of lookup_order(order_id) and search_reviews(seller_id).

4. Agent behavior

Suppose the user asks:

Where is order ORD-1001?

The agent should NOT simply answer:

Your order is shipped.

Instead:

User
 ↓
Agent
 ↓
Recognizes order question
 ↓
lookup_order("ORD-1001")
 ↓
Tool returns:
status = shipped
tracking = TRK123456
ETA = Aug 12
 ↓
Agent generates answer ONLY from tool result
 ↓
Response + receipt

The API response will contain something like:

{
  "answer": "Order ORD-1001 is currently shipped. Its estimated delivery date is August 12, 2026.",
  "grounded": true,
  "trace": [
    {
      "tool": "lookup_order",
      "arguments": {
        "order_id": "ORD-1001"
      },
      "result": {
        "found": true,
        "status": "shipped"
      }
    }
  ]
}

That trace is important because the assignment explicitly asks for the answer plus a trace of what the agent did, including tool calls, arguments, and returned data.

5. Guardrails

This is where we can make the project look much stronger.

We'll enforce:

Maximum agent steps
MAX_STEPS = 4

So the model can't endlessly call tools.

The assignment specifically asks for basic limits such as a step/token cap and timeout.

Unknown tool

If the model somehow asks for:

delete_order()

our code rejects it.

Invalid arguments

If it calls:

{
  "order_id": 12345
}

instead of a string, validation catches it.

Tool failure

If:

lookup_order()

fails:

{
  "found": false,
  "error": "ORDER_SERVICE_UNAVAILABLE"
}

the model must not invent an answer.

It should say something like:

I couldn't retrieve the order information right now.

No result

If an order doesn't exist:

ORD-9999

the answer should be:

I couldn't find order ORD-9999 in the marketplace data.

Not:

Your order is processing.

Out-of-scope question

User:

What's the weather in Mumbai?

Agent:

I can help with marketplace order and seller-review questions, but I don't have a tool for weather information.

The assignment explicitly requires safely handling out-of-scope/unanswerable questions rather than confidently making things up.

6. Final project structure

We'll create:

plexe-marketplace-agent/
│
├── src/
│   ├── __init__.py
│   ├── agent.py
│   ├── serve.py
│   ├── config.py
│   ├── models.py
│   ├── tools.py
│   └── mock_data.py
│
├── 
│   └── test_api.py
│
├── evals/
│   └── evaluation_cases.json
│
├── ai_chat_logs/
│   └── README.md
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── Dockerfile
├── README.md
└── run_evals.py

This closely follows the structure Plexe requested, including src, evals, ai_chat_logs, README.md, and optional Dockerfile.Create requirements.txt

Create:

requirements.txt

Paste:

fastapi
uvicorn[standard]
gemini # edited 
groq # edited
python-dotenv
pydantic
pytest