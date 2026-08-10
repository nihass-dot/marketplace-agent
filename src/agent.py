# """
# The agent: control loop + guardrails + grounding.

# Design decisions (see README for the full write-up):

# 1. Tool contracts are strict JSON schemas with required fields. The model
#    cannot pass free-form arguments; Claude's tool-use forces structured
#    calls, and we additionally validate/normalize inside tools.py.

# 2. The loop is bounded by config.MAX_TOOL_STEPS and a wall-clock timeout.
#    Every tool call, whatever happens, decrements the step budget. If the
#    budget runs out we stop and return whatever we've grounded so far
#    instead of looping forever.

# 3. Groundedness is enforced two ways:
#    a) System prompt instructs the model to answer ONLY from tool results
#       and to say "I don't have that information" rather than guess.
#    b) The trace we return alongside the answer contains the exact tool
#       calls and raw results, so a human can check the answer against the
#       receipts. We do not currently do automated claim-checking (see
#       evals/README for what a v2 would add), but the traceability itself
#       is what makes an ungrounded answer *detectable*.

# 4. Unknown tool name / bad arguments from the model are caught and turned
#    into a tool_result error message fed back to the model — not a crash.
#    This lets the model self-correct on the next step.
# """

# import time
# import json
# from google import genai

# from src import config
# from src.tools import TOOL_REGISTRY, ToolExecutionError

# SYSTEM_PROMPT = """You are an internal support assistant for an online marketplace's operations team.

# You answer questions about orders, sellers, and reviews using ONLY the tools provided.

# Rules you must follow strictly:
# 1. Never state a fact (an order status, a date, a rating, a review) unless it came from a tool
#    result in this conversation. If you have not called a tool for a fact, you do not know it.
# 2. If a tool returns "found": false, tell the user the record does not exist. Do not guess an
#    order id or seller id, and do not assume it exists under a different id.
# 3. If a tool call fails (an error is returned), tell the user you were unable to retrieve that
#    information right now. Do not fabricate a plausible-sounding answer to cover the failure.
# 4. If the question is unrelated to orders, sellers, or reviews on this marketplace (e.g. general
#    chit-chat, coding help, questions about other companies), politely refuse and say this
#    assistant only handles marketplace order/seller/review questions.
# 5. If the question requires information no available tool can provide (e.g. refund policy,
#    internal financial data), say so plainly instead of guessing.
# 6. Keep answers short and factual. When you state a fact, mention which record it came from
#    (e.g. "Order ORD1002" or "seller SEL02"), so the answer can be checked against the tools.
# 7. You may call more than one tool if the question needs it (e.g. an order's seller's reviews),
#    but do not call tools for information you already have in this conversation.
# """

# TOOLS = [
#     {
#         "name": "lookup_order",
#         "description": "Look up a single order by its order ID. Returns order status, buyer, "
#                         "seller_id, item, dates and amount. Returns found=false if the order "
#                         "id does not exist.",
#         "input_schema": {
#             "type": "object",
#             "properties": {
#                 "order_id": {
#                     "type": "string",
#                     "description": "The order id, e.g. 'ORD1001'."
#                 }
#             },
#             "required": ["order_id"],
#         },
#     },
#     {
#         "name": "search_reviews",
#         "description": "Get all reviews left for a given seller ID. Returns found=false if the "
#                         "seller id does not exist, or an empty review list if the seller exists "
#                         "but has no reviews.",
#         "input_schema": {
#             "type": "object",
#             "properties": {
#                 "seller_id": {
#                     "type": "string",
#                     "description": "The seller id, e.g. 'SEL01'."
#                 }
#             },
#             "required": ["seller_id"],
#         },
#     },
#     {
#         "name": "get_seller_info",
#         "description": "Get profile info for a seller: name, join date, average rating, total "
#                         "orders. Returns found=false if the seller id does not exist.",
#         "input_schema": {
#             "type": "object",
#             "properties": {
#                 "seller_id": {
#                     "type": "string",
#                     "description": "The seller id, e.g. 'SEL01'."
#                 }
#             },
#             "required": ["seller_id"],
#         },
#     },
# ]


# class AgentTimeoutError(Exception):
#     pass


# def _execute_tool_call(name: str, args: dict) -> dict:
#     """Dispatch to the real tool, turning any failure mode into a structured
#     result rather than letting an exception escape the loop."""
#     if name not in TOOL_REGISTRY:
#         return {"ok": False, "error": "unknown_tool", "message": f"No tool named '{name}' exists."}

#     if not isinstance(args, dict):
#         return {"ok": False, "error": "invalid_arguments", "message": "Arguments must be an object."}

#     try:
#         return TOOL_REGISTRY[name](**args)
#     except ToolExecutionError as e:
#         return {"ok": False, "error": "tool_execution_error", "message": str(e)}
#     except TypeError as e:
#         # e.g. missing/unexpected kwargs from a malformed model call
#         return {"ok": False, "error": "bad_call_signature", "message": str(e)}
#     except Exception as e:  # last-resort net so the API endpoint never 500s on a tool bug
#         return {"ok": False, "error": "unexpected_error", "message": str(e)}


# def run_agent(question: str) -> dict:
#     """
#     Runs the bounded tool-use loop for a single question.

#     Returns:
#         {
#           "answer": str,
#           "trace": [ {"step": int, "tool": str, "arguments": dict, "result": dict}, ... ],
#           "steps_used": int,
#           "stopped_reason": "completed" | "max_steps" | "timeout" | "error",
#         }
#     """
#     if not question or not question.strip():
#         return {
#             "answer": "Please provide a question.",
#             "trace": [],
#             "steps_used": 0,
#             "stopped_reason": "invalid_input",
#         }

#     client = genai.Client(
#     api_key=config.GEMINI_API_KEY
# )

#     messages = [{"role": "user", "content": question.strip()}]
#     trace = []
#     start_time = time.monotonic()
#     stopped_reason = "completed"

#     for step in range(1, config.MAX_TOOL_STEPS + 1):
#         if time.monotonic() - start_time > config.REQUEST_TIMEOUT_SECONDS:
#             stopped_reason = "timeout"
#             break

#         try:
#             response = client.messages.create(
#                 model=config.MODEL_NAME,
#                 max_tokens=config.MAX_OUTPUT_TOKENS,
#                 system=SYSTEM_PROMPT,
#                 tools=TOOLS,
#                 messages=messages,
#             )
#         except Exception as e:
#             return {
#                 "answer": "The agent hit an internal error while reasoning about your question. "
#                           "Please try again.",
#                 "trace": trace,
#                 "steps_used": step - 1,
#                 "stopped_reason": "error",
#                 "error_detail": str(e),
#             }

#         # No tool call requested -> model is giving its final answer.
#         if response.stop_reason != "tool_use":
#             final_text = "".join(
#                 block.text for block in response.content if getattr(block, "type", None) == "text"
#             ).strip()
#             return {
#                 "answer": final_text or "I don't have enough information to answer that.",
#                 "trace": trace,
#                 "steps_used": step - 1,
#                 "stopped_reason": stopped_reason,
#             }

#         # Model wants to call one or more tools. Append its turn, then run every
#         # tool_use block and feed results back as tool_result blocks.
#         messages.append({"role": "assistant", "content": response.content})

#         tool_results = []
#         for block in response.content:
#             if getattr(block, "type", None) != "tool_use":
#                 continue

#             result = _execute_tool_call(block.name, block.input)
#             trace.append({
#                 "step": step,
#                 "tool": block.name,
#                 "arguments": block.input,
#                 "result": result,
#             })
#             tool_results.append({
#                 "type": "tool_result",
#                 "tool_use_id": block.id,
#                 "content": json.dumps(result),
#                 "is_error": not result.get("ok", False),
#             })

#         messages.append({"role": "user", "content": tool_results})
#     else:
#         stopped_reason = "max_steps"

#     if stopped_reason == "max_steps":
#         return {
#             "answer": "I wasn't able to fully resolve this within the allowed number of tool "
#                       "calls. Here's what I found so far — you may want to check it manually.",
#             "trace": trace,
#             "steps_used": config.MAX_TOOL_STEPS,
#             "stopped_reason": "max_steps",
#         }

#     # Timed out before the model produced a final answer.
#     return {
#         "answer": "This request took too long to resolve and was stopped. Please try again or "
#                   "narrow your question.",
#         "trace": trace,
#         "steps_used": len(set(t["step"] for t in trace)),
#         "stopped_reason": "timeout",
#     }
"""
The agent: control loop + guardrails + grounding.
"""
import time
import json
from google import genai
from google.genai import types

from src import config
from src.tools import TOOL_REGISTRY, ToolExecutionError

SYSTEM_PROMPT = """You are an internal support assistant for an online marketplace's operations team.

You answer questions about orders, sellers, and reviews using ONLY the tools provided.

Rules you must follow strictly:
1. Never state a fact (an order status, a date, a rating, a review) unless it came from a tool
   result in this conversation. If you have not called a tool for a fact, you do not know it.
2. If a tool returns "found": false, tell the user the record does not exist. Do not guess an
   order id or seller id, and do not assume it exists under a different id.
3. If a tool call fails (an error is returned), tell the user you were unable to retrieve that
   information right now. Do not fabricate a plausible-sounding answer to cover the failure.
4. If the question is unrelated to orders, sellers, or reviews on this marketplace (e.g. general
   chit-chat, coding help, questions about other companies), politely refuse and say this
   assistant only handles marketplace order/seller/review questions.
5. If the question requires information no available tool can provide (e.g. refund policy,
   internal financial data), say so plainly instead of guessing.
6. Keep answers short and factual. When you state a fact, mention which record it came from
   (e.g. "Order ORD1002" or "seller SEL02"), so the answer can be checked against the tools.
7. You may call more than one tool if the question needs it (e.g. an order's seller's reviews),
   but do not call tools for information you already have in this conversation.
"""

# Tool definitions using google.genai types
TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="lookup_order",
                description="Look up a single order by its order ID. Returns order status, buyer, "
                            "seller_id, item, dates and amount. Returns found=false if the order "
                            "id does not exist.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "order_id": types.Schema(type="STRING", description="The order id, e.g. 'ORD1001'.")
                    },
                    required=["order_id"]
                )
            ),
            types.FunctionDeclaration(
                name="search_reviews",
                description="Get all reviews left for a given seller ID. Returns found=false if the "
                            "seller id does not exist, or an empty review list if the seller exists "
                            "but has no reviews.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "seller_id": types.Schema(type="STRING", description="The seller id, e.g. 'SEL01'.")
                    },
                    required=["seller_id"]
                )
            ),
            types.FunctionDeclaration(
                name="get_seller_info",
                description="Get profile info for a seller: name, join date, average rating, total "
                            "orders. Returns found=false if the seller id does not exist.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "seller_id": types.Schema(type="STRING", description="The seller id, e.g. 'SEL01'.")
                    },
                    required=["seller_id"]
                )
            ),
        ]
    )
]


def _execute_tool_call(name: str, args: dict) -> dict:
    """Dispatch to the real tool, turning any failure mode into a structured
    result rather than letting an exception escape the loop."""
    if name not in TOOL_REGISTRY:
        return {"ok": False, "error": "unknown_tool", "message": f"No tool named '{name}' exists."}

    if not isinstance(args, dict):
        return {"ok": False, "error": "invalid_arguments", "message": "Arguments must be an object."}

    try:
        return TOOL_REGISTRY[name](**args)
    except ToolExecutionError as e:
        return {"ok": False, "error": "tool_execution_error", "message": str(e)}
    except TypeError as e:
        return {"ok": False, "error": "bad_call_signature", "message": str(e)}
    except Exception as e:
        return {"ok": False, "error": "unexpected_error", "message": str(e)}


def run_agent(question: str) -> dict:
    """
    Runs the bounded tool-use loop for a single question.
    """
    if not question or not question.strip():
        return {
            "answer": "Please provide a question.",
            "trace": [],
            "steps_used": 0,
            "stopped_reason": "invalid_input",
        }

    # Initialize the new google-genai Client
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    
    # Configure generation settings
    generate_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=TOOLS,
        max_output_tokens=config.MAX_OUTPUT_TOKENS,
        temperature=0,
    )
    
    # Start a chat session
    chat = client.chats.create(model=config.MODEL_NAME, config=generate_config)
    
    trace = []
    start_time = time.monotonic()
    stopped_reason = "completed"

    # Send the initial question
    try:
        response = chat.send_message(question.strip())
    except Exception as e:
        return {
            "answer": "The agent hit an internal error while reasoning about your question. Please try again.",
            "trace": trace,
            "steps_used": 0,
            "stopped_reason": "error",
            "error_detail": str(e),
        }

    for step in range(1, config.MAX_TOOL_STEPS + 1):
        if time.monotonic() - start_time > config.REQUEST_TIMEOUT_SECONDS:
            stopped_reason = "timeout"
            break

        # Check if the model wants to call a tool
        parts = response.candidates[0].content.parts
        tool_calls = [p for p in parts if p.function_call and p.function_call.name]

        if not tool_calls:
            # No tool call requested -> model is giving its final answer.
            final_text = "".join([p.text for p in parts if hasattr(p, "text") and p.text]).strip()
            return {
                "answer": final_text or "I don't have enough information to answer that.",
                "trace": trace,
                "steps_used": step - 1,
                "stopped_reason": stopped_reason,
            }

        # Model wants to call one or more tools. 
        # Run every tool_use block and feed results back as FunctionResponse objects.
        function_responses = []
        for part in tool_calls:
            name = part.function_call.name
            # Convert Protobuf Map to standard dict
            args = {key: value for key, value in part.function_call.args.items()}
            
            result = _execute_tool_call(name, args)
            
            trace.append({
                "step": step,
                "tool": name,
                "arguments": args,
                "result": result,
            })
            
            # Append the function response for this specific tool call
            function_responses.append(
                types.Part(function_response=types.FunctionResponse(name=name, response=result))
            )

        # Send tool results back to the model
        try:
            response = chat.send_message(function_responses)
        except Exception as e:
            return {
                "answer": f"Gemini error: {type(e).__name__}: {str(e)}",
                "trace": trace,
                "steps_used": 0,
                "stopped_reason": "error",
                "error_detail": str(e),
            }
    else:
        stopped_reason = "max_steps"

    if stopped_reason == "max_steps":
        return {
            "answer": "I wasn't able to fully resolve this within the allowed number of tool "
                      "calls. Here's what I found so far — you may want to check it manually.",
            "trace": trace,
            "steps_used": config.MAX_TOOL_STEPS,
            "stopped_reason": "max_steps",
        }

    # Timed out before the model produced a final answer.
    return {
        "answer": "This request took too long to resolve and was stopped. Please try again or "
                  "narrow your question.",
        "trace": trace,
        "steps_used": len(set(t["step"] for t in trace)),
        "stopped_reason": "timeout",
    }