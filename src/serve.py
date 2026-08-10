"""
REST API for the marketplace ops agent.

One endpoint: POST /ask
  request:  {"question": "Where is order ORD1002?"}
  response: {"answer": "...", "trace": [...], "steps_used": 1, "stopped_reason": "completed"}

Run with:  uvicorn src.serve:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.agent import run_agent
from src import config

app = FastAPI(
    title="Plexe Marketplace Ops Agent",
    description="Ask ops questions about orders, sellers and reviews. "
                 "Every answer comes with a trace of the tool calls behind it.",
    version="1.0.0",
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="Natural language question")


class ToolTraceItem(BaseModel):
    step: int
    tool: str
    arguments: dict
    result: dict


class AskResponse(BaseModel):
    answer: str
    trace: list[ToolTraceItem]
    steps_used: int
    stopped_reason: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    if not config.GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not set on the server. See README for setup.",
        )
    try:
        result = run_agent(request.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed unexpectedly: {e}")

    return result
