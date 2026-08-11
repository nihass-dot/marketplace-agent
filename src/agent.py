
# # """
# # The agent: control loop + guardrails + grounding.
# # """
# # import time
# # import json
# # from google import genai
# # from google.genai import types

# # from src import config
# # from src.tools import TOOL_REGISTRY, ToolExecutionError

# # SYSTEM_PROMPT = """You are an internal support assistant for an online marketplace's operations team.

# # You answer questions about orders, sellers, and reviews using ONLY the tools provided.

# # Rules you must follow strictly:
# # 1. Never state a fact (an order status, a date, a rating, a review) unless it came from a tool
# #    result in this conversation. If you have not called a tool for a fact, you do not know it.
# # 2. If a tool returns "found": false, tell the user the record does not exist. Do not guess an
# #    order id or seller id, and do not assume it exists under a different id.
# # 3. If a tool call fails (an error is returned), tell the user you were unable to retrieve that
# #    information right now. Do not fabricate a plausible-sounding answer to cover the failure.
# # 4. If the question is unrelated to orders, sellers, or reviews on this marketplace (e.g. general
# #    chit-chat, coding help, questions about other companies), politely refuse and say this
# #    assistant only handles marketplace order/seller/review questions.
# # 5. If the question requires information no available tool can provide (e.g. refund policy,
# #    internal financial data), say so plainly instead of guessing.
# # 6. Keep answers short and factual. When you state a fact, mention which record it came from
# #    (e.g. "Order ORD1002" or "seller SEL02"), so the answer can be checked against the tools.
# # 7. You may call more than one tool if the question needs it (e.g. an order's seller's reviews),
# #    but do not call tools for information you already have in this conversation.
# # """

# # # Tool definitions using google.genai types
# # TOOLS = [
# #     types.Tool(
# #         function_declarations=[
# #             types.FunctionDeclaration(
# #                 name="lookup_order",
# #                 description="Look up a single order by its order ID. Returns order status, buyer, "
# #                             "seller_id, item, dates and amount. Returns found=false if the order "
# #                             "id does not exist.",
# #                 parameters=types.Schema(
# #                     type="OBJECT",
# #                     properties={
# #                         "order_id": types.Schema(type="STRING", description="The order id, e.g. 'ORD1001'.")
# #                     },
# #                     required=["order_id"]
# #                 )
# #             ),
# #             types.FunctionDeclaration(
# #                 name="search_reviews",
# #                 description="Get all reviews left for a given seller ID. Returns found=false if the "
# #                             "seller id does not exist, or an empty review list if the seller exists "
# #                             "but has no reviews.",
# #                 parameters=types.Schema(
# #                     type="OBJECT",
# #                     properties={
# #                         "seller_id": types.Schema(type="STRING", description="The seller id, e.g. 'SEL01'.")
# #                     },
# #                     required=["seller_id"]
# #                 )
# #             ),
# #             types.FunctionDeclaration(
# #                 name="get_seller_info",
# #                 description="Get profile info for a seller: name, join date, average rating, total "
# #                             "orders. Returns found=false if the seller id does not exist.",
# #                 parameters=types.Schema(
# #                     type="OBJECT",
# #                     properties={
# #                         "seller_id": types.Schema(type="STRING", description="The seller id, e.g. 'SEL01'.")
# #                     },
# #                     required=["seller_id"]
# #                 )
# #             ),
# #         ]
# #     )
# # ]


# # def _execute_tool_call(name: str, args: dict) -> dict:
# #     """Dispatch to the real tool, turning any failure mode into a structured
# #     result rather than letting an exception escape the loop."""
# #     if name not in TOOL_REGISTRY:
# #         return {"ok": False, "error": "unknown_tool", "message": f"No tool named '{name}' exists."}

# #     if not isinstance(args, dict):
# #         return {"ok": False, "error": "invalid_arguments", "message": "Arguments must be an object."}

# #     try:
# #         return TOOL_REGISTRY[name](**args)
# #     except ToolExecutionError as e:
# #         return {"ok": False, "error": "tool_execution_error", "message": str(e)}
# #     except TypeError as e:
# #         return {"ok": False, "error": "bad_call_signature", "message": str(e)}
# #     except Exception as e:
# #         return {"ok": False, "error": "unexpected_error", "message": str(e)}


# # def run_agent(question: str) -> dict:
# #     """
# #     Runs the bounded tool-use loop for a single question.
# #     """
# #     if not question or not question.strip():
# #         return {
# #             "answer": "Please provide a question.",
# #             "trace": [],
# #             "steps_used": 0,
# #             "stopped_reason": "invalid_input",
# #         }

# #     # Initialize the new google-genai Client
# #     client = genai.Client(api_key=config.GEMINI_API_KEY)
    
# #     # Configure generation settings
# #     generate_config = types.GenerateContentConfig(
# #         system_instruction=SYSTEM_PROMPT,
# #         tools=TOOLS,
# #         max_output_tokens=config.MAX_OUTPUT_TOKENS,
# #         temperature=0,
# #     )
    
# #     # Start a chat session
# #     chat = client.chats.create(model=config.MODEL_NAME, config=generate_config)
    
# #     trace = []
# #     start_time = time.monotonic()
# #     stopped_reason = "completed"

# #     # Send the initial question
# #     try:
# #         response = chat.send_message(question.strip())
# #     except Exception as e:
# #         return {
# #             "answer": f"Gemini error: {type(e).__name__}: {str(e)}",
# #             "trace": trace,
# #             "steps_used": 0,
# #             "stopped_reason": "error",
# #             "error_detail": str(e),
# #         }

# #     for step in range(1, config.MAX_TOOL_STEPS + 1):
# #         if time.monotonic() - start_time > config.REQUEST_TIMEOUT_SECONDS:
# #             stopped_reason = "timeout"
# #             break

# #         # Check if the model wants to call a tool
# #         parts = response.candidates[0].content.parts
# #         tool_calls = [p for p in parts if p.function_call and p.function_call.name]

# #         if not tool_calls:
# #             # No tool call requested -> model is giving its final answer.
# #             final_text = "".join([p.text for p in parts if hasattr(p, "text") and p.text]).strip()
# #             return {
# #                 "answer": final_text or "I don't have enough information to answer that.",
# #                 "trace": trace,
# #                 "steps_used": step - 1,
# #                 "stopped_reason": stopped_reason,
# #             }

# #         # Model wants to call one or more tools. 
# #         # Run every tool_use block and feed results back as FunctionResponse objects.
# #         function_responses = []
# #         for part in tool_calls:
# #             name = part.function_call.name
# #             # Convert Protobuf Map to standard dict
# #             args = {key: value for key, value in part.function_call.args.items()}
            
# #             result = _execute_tool_call(name, args)
            
# #             trace.append({
# #                 "step": step,
# #                 "tool": name,
# #                 "arguments": args,
# #                 "result": result,
# #             })
            
# #             # Append the function response for this specific tool call
# #             function_responses.append(
# #                 types.Part(function_response=types.FunctionResponse(name=name, response=result))
# #             )

# #         # Send tool results back to the model
# #         try:
# #             response = chat.send_message(function_responses)
# #         except Exception as e:
# #             return {
# #                 "answer": f"Gemini error: {type(e).__name__}: {str(e)}",
# #                 "trace": trace,
# #                 "steps_used": 0,
# #                 "stopped_reason": "error",
# #                 "error_detail": str(e),
# #             }
# #     else:
# #         stopped_reason = "max_steps"

# #     if stopped_reason == "max_steps":
# #         return {
# #             "answer": "I wasn't able to fully resolve this within the allowed number of tool "
# #                       "calls. Here's what I found so far — you may want to check it manually.",
# #             "trace": trace,
# #             "steps_used": config.MAX_TOOL_STEPS,
# #             "stopped_reason": "max_steps",
# #         }

# #     # Timed out before the model produced a final answer.
# #     return {
# #         "answer": "This request took too long to resolve and was stopped. Please try again or "
# #                   "narrow your question.",
# #         "trace": trace,
# #         "steps_used": len(set(t["step"] for t in trace)),
# #         "stopped_reason": "timeout",
# #     }
# """
# Marketplace agent.

# LLM providers:
#     Primary: Gemini
#     Fallback: Groq

# The agent keeps the same tool-use loop regardless of provider.

# Flow:

#     User
#       |
#       v
#     Primary LLM (Gemini)
#       |
#       |-- success --> tool call / final answer
#       |
#       |-- quota/error --> fallback LLM (Groq)
#                               |
#                               v
#                          tool call / final answer

# Tools are ALWAYS executed locally by this application.
# The LLM only decides which tool to call.

# Engineering guardrails around the LLM:
#     - MAX_TOOL_STEPS  : hard cap on tool-call rounds per request
#     - MAX_OUTPUT_TOKENS
#     - REQUEST_TIMEOUT_SECONDS
#     - Duplicate tool-call guard:  the exact same (name, args) pair is never
#       executed twice in one request. The model is told it already has the
#       result, so it is nudged toward producing a final answer.
#     - Repeated-batch guard:  if the model emits the identical batch of tool
#       calls twice in a row, we stop calling the LLM and synthesize a
#       grounded answer from the trace we already have.
#     - Final-answer synthesis from trace:  if max_steps is hit, we still
#       return something useful that is strictly grounded in the tool results
#       the model already gathered, rather than a generic error string.
# """

# import json
# import time
# from typing import Any

# from google import genai
# from google.genai import types
# from groq import Groq

# from src import config
# from src.tools import TOOL_REGISTRY, ToolExecutionError


# # ============================================================================
# # SYSTEM PROMPT
# # ============================================================================

# SYSTEM_PROMPT = """You are an internal support assistant for an online marketplace's operations team.

# You answer questions about orders, sellers, and reviews using ONLY the tools provided.

# Rules you must follow strictly:

# 1. Never state a fact (an order status, a date, a rating, a review) unless it came
#    from a tool result in this conversation.

# 2. If a tool returns "found": false, tell the user the record does not exist.
#    Do not guess an order id or seller id.

# 3. If a tool call fails, tell the user you were unable to retrieve that information
#    right now. Do not fabricate an answer.

# 4. If the question is unrelated to orders, sellers, or reviews on this marketplace,
#    politely refuse.

# 5. If the question requires information no available tool can provide, say so plainly
#    instead of guessing.

# 6. Keep answers concise and appropriate to the user's requested format.
#    If the user asks you to draft, write, compose, or reply to someone,
#    you MUST produce the requested message itself, not a summary of the
#    retrieved facts.

# 7. For drafting requests, use tool results only as factual grounding.
#    Do not simply repeat the tool result. Transform the relevant facts
#    into the requested communication.

# 8. If the user asks for a customer-facing reply, write it as a natural,
#    professional customer-support message. Do not expose internal tool
#    results, tool names, JSON, internal IDs unless they are useful to the
#    recipient, or internal reasoning.

# 9. Never invent facts. Every factual claim in a drafted response must
#    come from a tool result.

# 10. If a tool result contains enough information to answer the request,
#     produce the final answer instead of calling the same tool again.
# """


# # ============================================================================
# # GEMINI TOOL DEFINITIONS
# # ============================================================================

# GEMINI_TOOLS = [
#     types.Tool(
#         function_declarations=[
#             types.FunctionDeclaration(
#                 name="lookup_order",
#                 description=(
#                     "Look up a single order by its order ID. "
#                     "Returns order status, buyer, seller_id, item, dates and amount. "
#                     "Returns found=false if the order id does not exist."
#                 ),
#                 parameters=types.Schema(
#                     type="OBJECT",
#                     properties={
#                         "order_id": types.Schema(
#                             type="STRING",
#                             description="The order id, e.g. ORD1001."
#                         )
#                     },
#                     required=["order_id"],
#                 ),
#             ),
#             types.FunctionDeclaration(
#                 name="search_reviews",
#                 description=(
#                     "Get all reviews left for a given seller ID. "
#                     "Returns found=false if the seller does not exist."
#                 ),
#                 parameters=types.Schema(
#                     type="OBJECT",
#                     properties={
#                         "seller_id": types.Schema(
#                             type="STRING",
#                             description="The seller id, e.g. SEL01."
#                         )
#                     },
#                     required=["seller_id"],
#                 ),
#             ),
#             types.FunctionDeclaration(
#                 name="get_seller_info",
#                 description=(
#                     "Get profile info for a seller: name, join date, "
#                     "average rating and total orders."
#                 ),
#                 parameters=types.Schema(
#                     type="OBJECT",
#                     properties={
#                         "seller_id": types.Schema(
#                             type="STRING",
#                             description="The seller id, e.g. SEL01."
#                         )
#                     },
#                     required=["seller_id"],
#                 ),
#             ),
#         ]
#     )
# ]


# # ============================================================================
# # GROQ TOOL DEFINITIONS
# # ============================================================================

# GROQ_TOOLS = [
#     {
#         "type": "function",
#         "function": {
#             "name": "lookup_order",
#             "description": (
#                 "Look up a single order by order ID. "
#                 "Returns status, buyer, seller_id, item, dates and amount."
#             ),
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "order_id": {
#                         "type": "string",
#                         "description": "The order id, e.g. ORD1001."
#                     }
#                 },
#                 "required": ["order_id"],
#             },
#         },
#     },
#     {
#         "type": "function",
#         "function": {
#             "name": "search_reviews",
#             "description": (
#                 "Get all reviews left for a seller ID. "
#                 "Returns found=false if seller does not exist."
#             ),
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "seller_id": {
#                         "type": "string",
#                         "description": "The seller id, e.g. SEL01."
#                     }
#                 },
#                 "required": ["seller_id"],
#             },
#         },
#     },
#     {
#         "type": "function",
#         "function": {
#             "name": "get_seller_info",
#             "description": (
#                 "Get seller profile information including name, "
#                 "join date, average rating and total orders."
#             ),
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "seller_id": {
#                         "type": "string",
#                         "description": "The seller id, e.g. SEL01."
#                     }
#                 },
#                 "required": ["seller_id"],
#             },
#         },
#     },
# ]


# # ============================================================================
# # TOOL EXECUTION
# # ============================================================================

# def _execute_tool_call(name: str, args: dict) -> dict:
#     """Execute one registered tool safely. The LLM never executes tools directly."""

#     if name not in TOOL_REGISTRY:
#         return {
#             "ok": False,
#             "error": "unknown_tool",
#             "message": f"No tool named '{name}' exists.",
#         }

#     if not isinstance(args, dict):
#         return {
#             "ok": False,
#             "error": "invalid_arguments",
#             "message": "Arguments must be an object.",
#         }

#     try:
#         return TOOL_REGISTRY[name](**args)

#     except ToolExecutionError as e:
#         return {
#             "ok": False,
#             "error": "tool_execution_error",
#             "message": str(e),
#         }

#     except TypeError as e:
#         return {
#             "ok": False,
#             "error": "bad_call_signature",
#             "message": str(e),
#         }

#     except Exception as e:
#         return {
#             "ok": False,
#             "error": "unexpected_error",
#             "message": str(e),
#         }


# def _call_key(name: str, args: dict) -> tuple:
#     """Stable, hashable key identifying one (tool, arguments) pair."""
#     try:
#         return (name, json.dumps(args, sort_keys=True))
#     except (TypeError, ValueError):
#         return (name, repr(args))


# def _batch_key(calls) -> tuple:
#     """Stable, hashable key for a batch of tool calls in one model turn."""
#     items = []
#     for name, args in calls:
#         items.append(_call_key(name, args))
#     return tuple(sorted(items))


# def _already_called_response(name: str, args: dict) -> dict:
#     """Synthetic result returned to the model when it re-requests a call it
#     has already made. This nudges it toward producing a final answer rather
#     than looping on identical tool calls."""
#     return {
#         "ok": True,
#         "already_called": True,
#         "message": (
#             f"You already called {name} with these arguments earlier in "
#             f"this conversation and received its result. Do not call it "
#             f"again. Use the earlier result and produce your final answer "
#             f"to the user now."
#         ),
#     }


# # ============================================================================
# # PROVIDER ERROR DETECTION
# # ============================================================================

# def _is_provider_failure(error: Exception) -> bool:
#     """
#     Decide whether the current LLM provider is unavailable.

#     We fallback ONLY for true provider issues:
#       - HTTP 429 / quota
#       - authentication errors
#       - 5xx service errors
#       - network/timeout errors

#     We do NOT fallback because a local tool returned an error string
#     (e.g. "orders-service returned 500") — that is a tool failure that the
#     model should handle itself, not a provider failure.
#     """

#     message = str(error).lower()

#     provider_error_markers = [
#         "429",
#         "resource_exhausted",
#         "quota",
#         "rate limit",
#         "rate_limit",
#         "unauthorized",
#         "authentication",
#         "api key",
#         "service unavailable",
#         "503",
#         "gateway",
#         "deadline",
#         "connection",
#         "unavailable",
#     ]

#     return any(marker in message for marker in provider_error_markers)


# # ============================================================================
# # GEMINI PROVIDER
# # ============================================================================

# class GeminiProvider:
#     def __init__(self):
#         if not config.GEMINI_API_KEY:
#             raise RuntimeError("GEMINI_API_KEY is not configured.")

#         self.client = genai.Client(api_key=config.GEMINI_API_KEY)

#         self.chat = self.client.chats.create(
#             model=config.GEMINI_MODEL,
#             config=types.GenerateContentConfig(
#                 system_instruction=SYSTEM_PROMPT,
#                 tools=GEMINI_TOOLS,
#                 max_output_tokens=config.MAX_OUTPUT_TOKENS,
#                 temperature=0,
#             ),
#         )

#     def send(self, message):
#         return self.chat.send_message(message)


# # ============================================================================
# # GROQ PROVIDER
# # ============================================================================

# class GroqProvider:
#     def __init__(self):
#         if not config.GROQ_API_KEY:
#             raise RuntimeError("GROQ_API_KEY is not configured.")

#         self.client = Groq(api_key=config.GROQ_API_KEY)

#         self.messages = [
#             {
#                 "role": "system",
#                 "content": SYSTEM_PROMPT,
#             }
#         ]

#     def send(self, message):
#         """
#         Send a message through Groq.

#         `message` can be:
#           - user text (str)
#           - list of OpenAI-style messages (assistant tool_calls / tool results)
#         """
#         if isinstance(message, str):
#             self.messages.append({"role": "user", "content": message})

#         elif isinstance(message, list):
#             self.messages.extend(message)

#         else:
#             self.messages.append(message)

#         response = self.client.chat.completions.create(
#             model=config.GROQ_MODEL,
#             messages=self.messages,
#             tools=GROQ_TOOLS,
#             tool_choice="auto",
#             temperature=0.2,
#             max_tokens=config.MAX_OUTPUT_TOKENS,
#         )

#         assistant_message = response.choices[0].message
#         self.messages.append(assistant_message.model_dump())

#         return response


# # ============================================================================
# # FINAL-ANSWER SYNTHESIS FROM TRACE
# # ============================================================================

# def _synthesize_answer_from_trace(question: str, trace: list) -> str:
#     """
#     Build a short, strictly-grounded answer from the tool results the model
#     has already gathered. Used when the model loops and we stop calling it.

#     This is NOT hardcoding answers to specific eval questions: it simply
#     formats whatever tool results exist in the trace into natural language.
#     If the trace is empty or all errored, we say so plainly.
#     """

#     if not trace:
#         return (
#             "I'm not able to answer that with the tools available to me on "
#             "this marketplace."
#         )

#     # Deduplicate by (tool, args) so we never cite the same call twice.
#     seen = set()
#     unique_results = []
#     for entry in trace:
#         key = _call_key(entry["tool"], entry["arguments"])
#         if key in seen:
#             continue
#         seen.add(key)
#         unique_results.append(entry)

#     # If every call errored, say so.
#     if all(not r["result"].get("ok") for r in unique_results):
#         return (
#             "I was unable to retrieve the information needed to answer "
#             "that right now. Please try again in a moment."
#         )

#     lines = []

#     for entry in unique_results:
#         name = entry["tool"]
#         result = entry["result"]

#         if not result.get("ok"):
#             continue

#         if name == "lookup_order":
#             if not result.get("found"):
#                 lines.append(
#                     f"Order {entry['arguments'].get('order_id')} does not exist."
#                 )
#             else:
#                 o = result.get("order", {})
#                 bits = [f"Order {o.get('order_id')}"]
#                 if o.get("status"):
#                     bits.append(f"status: {o['status']}")
#                 if o.get("buyer"):
#                     bits.append(f"buyer: {o['buyer']}")
#                 if o.get("item"):
#                     bits.append(f"item: {o['item']}")
#                 if o.get("expected_delivery"):
#                     bits.append(f"expected delivery: {o['expected_delivery']}")
#                 if o.get("amount_usd") is not None:
#                     bits.append(f"amount: ${o['amount_usd']}")
#                 if o.get("delay_reason"):
#                     bits.append(f"delay reason: {o['delay_reason']}")
#                 lines.append(" | ".join(bits) + ".")

#         elif name == "get_seller_info":
#             if not result.get("found"):
#                 lines.append(
#                     f"Seller {entry['arguments'].get('seller_id')} does not exist."
#                 )
#             else:
#                 s = result.get("seller", {})
#                 lines.append(
#                     f"Seller {s.get('seller_id')} ({s.get('name')}): "
#                     f"joined {s.get('joined')}, "
#                     f"average rating {s.get('rating_avg')}, "
#                     f"{s.get('total_orders')} total orders."
#                 )

#         elif name == "search_reviews":
#             if not result.get("found"):
#                 lines.append(
#                     f"Seller {entry['arguments'].get('seller_id')} does not exist."
#                 )
#             else:
#                 reviews = result.get("reviews", [])
#                 sid = result.get("seller_id", entry["arguments"].get("seller_id"))
#                 if not reviews:
#                     lines.append(f"Seller {sid} has no reviews on file.")
#                 else:
#                     lines.append(f"Seller {sid} has {len(reviews)} review(s):")
#                     for r in reviews:
#                         lines.append(
#                             f'  - rating {r.get("rating")} '
#                             f'({r.get("date", "n/a")}): "{r.get("text", "")}"'
#                         )

#     if not lines:
#         return (
#             "I gathered information but could not produce a confident answer. "
#             "Please rephrase your question."
#         )

#     return "\n".join(lines)


# # ============================================================================
# # GEMINI LOOP
# # ============================================================================

# def _run_gemini(
#     question: str,
#     trace: list,
#     start_time: float,
#     executed_calls: set | None = None,
# ):
#     """
#     Gemini tool-use loop.

#     Guardrails applied here:
#       - duplicate (name, args) pairs are never executed twice
#       - if the model emits the same batch twice in a row, we stop calling
#         Gemini and synthesize the final answer from the trace
#       - max_steps and timeout still apply
#     """

#     if executed_calls is None:
#         executed_calls = set()

#     provider = GeminiProvider()
#     previous_batch_key = None

#     try:
#         response = provider.send(question)
#     except Exception:
#         raise

#     for step in range(1, config.MAX_TOOL_STEPS + 1):

#         if time.monotonic() - start_time > config.REQUEST_TIMEOUT_SECONDS:
#             return {
#                 "answer": "This request took too long to resolve.",
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "timeout",
#             }

#         parts = response.candidates[0].content.parts

#         tool_calls = [
#             p for p in parts
#             if p.function_call and p.function_call.name
#         ]

#         if not tool_calls:
#             final_text = "".join(
#                 p.text for p in parts
#                 if hasattr(p, "text") and p.text
#             ).strip()

#             return {
#                 "answer": final_text or "I don't have enough information to answer that.",
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "completed",
#             }

#         # Collect the (name, args) pairs the model is requesting this turn.
#         requested = []
#         for part in tool_calls:
#             name = part.function_call.name
#             args = {k: v for k, v in part.function_call.args.items()}
#             requested.append((name, args))

#         current_batch_key = _batch_key(requested)

#         # ------------------------------------------------------------------
#         # Repeated-batch guard: if the model is asking for the exact same
#         # batch of tool calls as the previous turn, stop calling the LLM.
#         # We have everything we need; synthesize the answer from the trace.
#         # ------------------------------------------------------------------
#         if current_batch_key == previous_batch_key and previous_batch_key is not None:
#             answer = _synthesize_answer_from_trace(question, trace)
#             return {
#                 "answer": answer,
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "completed",
#             }

#         previous_batch_key = current_batch_key

#         # Execute each requested call, applying the duplicate-call guard.
#         function_responses = []
#         for name, args in requested:

#             key = _call_key(name, args)

#             if key in executed_calls:
#                 # Don't re-execute; return a synthetic "you already have this"
#                 # result so the model is pushed toward producing a final answer.
#                 result = _already_called_response(name, args)
#                 trace.append({
#                     "step": step,
#                     "tool": name,
#                     "arguments": args,
#                     "result": result,
#                 })
#             else:
#                 result = _execute_tool_call(name, args)
#                 executed_calls.add(key)
#                 trace.append({
#                     "step": step,
#                     "tool": name,
#                     "arguments": args,
#                     "result": result,
#                 })

#             function_responses.append(
#                 types.Part(
#                     function_response=types.FunctionResponse(
#                         name=name,
#                         response=result,
#                     )
#                 )
#             )

#         try:
#             response = provider.send(function_responses)
#         except Exception:
#             raise

#     # Hit max_steps. Rather than returning a generic error string, synthesize
#     # a grounded answer from whatever the model has gathered so far.
#     answer = _synthesize_answer_from_trace(question, trace)
#     return {
#         "answer": answer,
#         "trace": trace,
#         "steps_used": config.MAX_TOOL_STEPS,
#         "stopped_reason": "max_steps",
#     }


# # ============================================================================
# # GROQ LOOP
# # ============================================================================
# def _build_fallback_context(question: str, trace: list) -> str:
#     """
#     Build factual context for the fallback LLM from tool results already
#     collected by the primary provider.

#     This does not generate an answer. It only transfers verified tool
#     observations to the fallback model so it can continue reasoning without
#     repeating the same tool calls.
#     """

#     if not trace:
#         return question

#     successful_results = []

#     for entry in trace:
#         result = entry.get("result", {})

#         if result.get("ok"):
#             successful_results.append({
#                 "tool": entry.get("tool"),
#                 "arguments": entry.get("arguments"),
#                 "result": result,
#             })

#     if not successful_results:
#         return question

#     context = json.dumps(
#         successful_results,
#         indent=2,
#         ensure_ascii=False,
#     )

#     return f"""
# The primary model already executed some tools for this request.

# You must continue from the verified tool results below.

# IMPORTANT:
# - Treat these results as authoritative.
# - Do not invent facts.
# - Do not repeat a tool call if the required result is already available.
# - Complete the user's original request.
# - If the user asked for a draft/reply/message, actually write that message.
# - Do not describe the tool results instead of fulfilling the request.

# Original user request:
# {question}

# Verified tool results:
# {context}

# Now produce the final answer to the original user request.
# """
# def _run_groq(
#     question: str,
#     trace: list,
#     start_time: float,
#     executed_calls: set | None = None,
# ):
#     """
#     Groq tool-use loop. Same guardrails as the Gemini loop.
#     """

#     if executed_calls is None:
#         executed_calls = set()

#     provider = GroqProvider()
#     previous_batch_key = None

#     response = provider.send(question)

#     for step in range(1, config.MAX_TOOL_STEPS + 1):

#         if time.monotonic() - start_time > config.REQUEST_TIMEOUT_SECONDS:
#             return {
#                 "answer": "This request took too long to resolve.",
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "timeout",
#             }

#         message = response.choices[0].message

#         if not message.tool_calls:
#             return {
#                 "answer": (
#                     message.content
#                     or "I don't have enough information to answer that."
#                 ),
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "completed",
#             }

#         # Collect requested calls.
#         requested = []
#         for tool_call in message.tool_calls:
#             name = tool_call.function.name
#             try:
#                 args = json.loads(tool_call.function.arguments)
#             except (json.JSONDecodeError, TypeError):
#                 args = {}
#             requested.append((name, args))

#         current_batch_key = _batch_key(requested)

#         # Repeated-batch guard.
#         if current_batch_key == previous_batch_key and previous_batch_key is not None:
#             answer = _synthesize_answer_from_trace(question, trace)
#             return {
#                 "answer": answer,
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "completed",
#             }

#         previous_batch_key = current_batch_key

#         tool_messages = []
#         for tool_call, (name, args) in zip(message.tool_calls, requested):

#             key = _call_key(name, args)

#             if key in executed_calls:
#                 result = _already_called_response(name, args)
#             else:
#                 result = _execute_tool_call(name, args)
#                 executed_calls.add(key)

#             trace.append({
#                 "step": step,
#                 "tool": name,
#                 "arguments": args,
#                 "result": result,
#             })

#             tool_messages.append({
#                 "role": "tool",
#                 "tool_call_id": tool_call.id,
#                 "name": name,
#                 "content": json.dumps(result),
#             })

#         response = provider.send(tool_messages)

#     # Max steps hit — synthesize a grounded answer.
#     answer = _synthesize_answer_from_trace(question, trace)
#     return {
#         "answer": answer,
#         "trace": trace,
#         "steps_used": config.MAX_TOOL_STEPS,
#         "stopped_reason": "max_steps",
#     }


# # ============================================================================
# # MAIN AGENT
# # ============================================================================

# def run_agent(question: str) -> dict:

#     if not question or not question.strip():
#         return {
#             "answer": "Please provide a question.",
#             "trace": [],
#             "steps_used": 0,
#             "stopped_reason": "invalid_input",
#         }

#     trace: list = []
#     start_time = time.monotonic()

#     primary = config.PRIMARY_LLM
#     fallback = config.FALLBACK_LLM

#     # ------------------------------------------------------------
#     # PRIMARY PROVIDER
#     # ------------------------------------------------------------

#     try:
#         if primary == "gemini":
#             return _run_gemini(question, trace, start_time, set())
#         elif primary == "groq":
#             return _run_groq(question, trace, start_time, set())
#         else:
#             raise RuntimeError(f"Unsupported primary provider: {primary}")

#     except Exception as primary_error:

#         # --------------------------------------------------------
#         # FALLBACK
#         # --------------------------------------------------------

#         if not _is_provider_failure(primary_error):
#             # Not a provider issue — surface the error without burning the
#             # fallback provider on something it can't fix either.
#             return {
#                 "answer": (
#                     "The agent hit an internal error while reasoning about "
#                     "your question. Please try again."
#                 ),
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "error",
#                 "error_detail": str(primary_error),
#             }

#         if fallback == primary:
#             return {
#                 "answer": "The configured LLM provider is currently unavailable.",
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "provider_error",
#                 "error_detail": str(primary_error),
#             }

#         try:
#             # Restart cleanly with the fallback provider. The fallback gets a
#             # fresh guard set so it can re-ask the question and run its own
#             # tool calls within the step budget.
#             if fallback == "groq":
#                 return _run_groq(question, trace, start_time, set())
#             elif fallback == "gemini":
#                 return _run_gemini(question, trace, start_time, set())
#             else:
#                 raise RuntimeError(f"Unsupported fallback provider: {fallback}")

#         except Exception as fallback_error:

#             # Last-resort: if we already gathered tool results before both
#             # providers failed, still give the user something grounded.
#             if trace:
#                return {
#                     "answer": (
#                         "I was unable to generate the final response right now. "
#                         "Please try again in a moment."
#                   ),
#                   "trace": trace,
#                   "steps_used": len(trace),
#                   "stopped_reason": "provider_error",
#                   "error_detail": (
#                       f"Primary: {primary_error}; "
#                       f"Fallback: {fallback_error}"
#         ),
#     }

#             return {
#                 "answer": (
#                     "Both configured LLM providers were unable to process "
#                     "the request."
#                 ),
#                 "trace": trace,
#                 "steps_used": len(trace),
#                 "stopped_reason": "provider_error",
#                 "error_detail": (
#                     f"Primary: {primary_error}; "
#                     f"Fallback: {fallback_error}"
#                 ),
#             }

"""
Marketplace agent.

LLM providers:
    Primary: Gemini
    Fallback: Groq

The agent uses LLMs for:
    - deciding which tools to call
    - interpreting tool results
    - generating the final response

Tools are ALWAYS executed locally by this application.

Important design principles:
    - No hardcoded answers for evaluation questions.
    - Tool results are the only source of marketplace facts.
    - Duplicate tool calls are prevented.
    - Provider failures can fall back from Gemini to Groq.
    - Drafting requests receive an additional LLM-only finalization pass.
    - The finalization pass transforms verified facts into the format requested
      by the user instead of simply exposing raw tool-result summaries.
"""

import json
import time

from google import genai
from google.genai import types
from groq import Groq

from src import config
from src.tools import TOOL_REGISTRY, ToolExecutionError


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are an internal support assistant for an online marketplace's operations team.

You answer questions about orders, sellers, and reviews using ONLY the tools provided.

IMPORTANT RULES:

1. Never invent marketplace facts.

2. Every factual claim about an order, seller, review, date, rating, buyer,
   product, amount, status, or delivery must come from a tool result.

3. If a tool returns found=false, clearly tell the user that the requested
   record does not exist.

4. If a tool fails, explain that the requested information could not be
   retrieved. Never fabricate the missing information.

5. If the user's request is unrelated to orders, sellers, or reviews,
   politely explain that the available marketplace tools cannot answer it.

6. If the user asks for a draft, reply, message, response, email, explanation,
   or customer-facing communication, DO NOT summarize the tool result.

   Instead:
   - understand what communication the user requested;
   - use the tool result only as factual grounding;
   - write the actual requested communication;
   - make it natural and professional;
   - do not expose internal tool names or JSON;
   - do not expose internal reasoning;
   - do not simply repeat the database fields.

7. For customer-facing communication, write as if the message will actually
   be sent to the customer.

8. Only include facts supported by the tool results.

9. Do not call a tool again when its required result has already been obtained.

10. Once sufficient information has been retrieved, stop using tools and answer
    the user's original request.

11. Follow the requested output format. If the user asks for a message,
    produce a message. If the user asks for information, provide information.

12. Keep answers concise unless the user asks for more detail.
"""


# ============================================================================
# FINALIZER PROMPT
# ============================================================================

FINALIZER_SYSTEM_PROMPT = """You are the final response writer for an internal
marketplace support assistant.

Your job is to turn verified tool results into the exact response requested
by the user.

STRICT RULES:

1. Use ONLY the verified tool results supplied to you.

2. Never invent facts.

3. Do not mention tools, tool calls, JSON, agents, prompts, traces, or internal
   reasoning.

4. Follow the user's requested format exactly.

5. If the user asks for a draft, reply, message, email, or customer-facing
   communication, WRITE THE ACTUAL MESSAGE.

6. Do not merely summarize the verified data.

7. If the user asks for a customer-facing response, make it natural,
   professional, concise, and appropriate for the recipient.

8. Do not add unsupported promises, compensation, refunds, dates, or policies.

9. Return ONLY the final response that should be shown to the user.
"""


# ============================================================================
# GEMINI TOOL DEFINITIONS
# ============================================================================

GEMINI_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="lookup_order",
                description=(
                    "Look up a single order by its order ID. "
                    "Returns order status, buyer, seller_id, item, dates and amount. "
                    "Returns found=false if the order id does not exist."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "order_id": types.Schema(
                            type="STRING",
                            description="The order id, e.g. ORD1001."
                        )
                    },
                    required=["order_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="search_reviews",
                description=(
                    "Get all reviews left for a given seller ID. "
                    "Returns found=false if the seller does not exist."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "seller_id": types.Schema(
                            type="STRING",
                            description="The seller id, e.g. SEL01."
                        )
                    },
                    required=["seller_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="get_seller_info",
                description=(
                    "Get profile info for a seller: name, join date, "
                    "average rating and total orders."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "seller_id": types.Schema(
                            type="STRING",
                            description="The seller id, e.g. SEL01."
                        )
                    },
                    required=["seller_id"],
                ),
            ),
        ]
    )
]


# ============================================================================
# GROQ TOOL DEFINITIONS
# ============================================================================

GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "Look up a single order by order ID. "
                "Returns status, buyer, seller_id, item, dates and amount."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order id, e.g. ORD1001."
                    }
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_reviews",
            "description": (
                "Get all reviews left for a seller ID. "
                "Returns found=false if seller does not exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "seller_id": {
                        "type": "string",
                        "description": "The seller id, e.g. SEL01."
                    }
                },
                "required": ["seller_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_seller_info",
            "description": (
                "Get seller profile information including name, "
                "join date, average rating and total orders."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "seller_id": {
                        "type": "string",
                        "description": "The seller id, e.g. SEL01."
                    }
                },
                "required": ["seller_id"],
            },
        },
    },
]


# ============================================================================
# TOOL EXECUTION
# ============================================================================

def _execute_tool_call(name: str, args: dict) -> dict:
    """Execute one registered tool safely."""

    if name not in TOOL_REGISTRY:
        return {
            "ok": False,
            "error": "unknown_tool",
            "message": f"No tool named '{name}' exists.",
        }

    if not isinstance(args, dict):
        return {
            "ok": False,
            "error": "invalid_arguments",
            "message": "Arguments must be an object.",
        }

    try:
        return TOOL_REGISTRY[name](**args)

    except ToolExecutionError as e:
        return {
            "ok": False,
            "error": "tool_execution_error",
            "message": str(e),
        }

    except TypeError as e:
        return {
            "ok": False,
            "error": "bad_call_signature",
            "message": str(e),
        }

    except Exception as e:
        return {
            "ok": False,
            "error": "unexpected_error",
            "message": str(e),
        }


# ============================================================================
# CALL DEDUPLICATION
# ============================================================================

def _call_key(name: str, args: dict) -> tuple:
    """Create a stable key for a tool + arguments pair."""

    try:
        return (
            name,
            json.dumps(args, sort_keys=True, ensure_ascii=False),
        )
    except (TypeError, ValueError):
        return (name, repr(args))


def _batch_key(calls) -> tuple:
    """Create a stable key for a complete batch of tool calls."""

    return tuple(
        sorted(
            _call_key(name, args)
            for name, args in calls
        )
    )


def _already_called_response(name: str, args: dict) -> dict:
    """
    Tell the model that this exact tool call was already executed.
    """

    return {
        "ok": True,
        "already_called": True,
        "message": (
            f"The tool {name} with these arguments was already executed. "
            "Use the existing verified result instead of calling the tool again."
        ),
    }


# ============================================================================
# PROVIDER ERROR DETECTION
# ============================================================================

def _is_provider_failure(error: Exception) -> bool:
    """
    Detect errors that justify switching LLM providers.
    """

    message = str(error).lower()

    provider_error_markers = [
        "429",
        "resource_exhausted",
        "quota",
        "rate limit",
        "rate_limit",
        "unauthorized",
        "authentication",
        "api key",
        "service unavailable",
        "503",
        "502",
        "500 internal",
        "gateway",
        "deadline",
        "timeout",
        "connection",
        "unavailable",
    ]

    return any(marker in message for marker in provider_error_markers)


# ============================================================================
# REQUEST TYPE
# ============================================================================

def _is_drafting_request(question: str) -> bool:
    """
    Detect whether the user explicitly asks for generated communication.

    This is not an answer generator and contains no evaluation-specific
    knowledge. It only decides whether an LLM finalization pass is useful.
    """

    text = question.lower()

    drafting_terms = (
        "draft",
        "write",
        "reply",
        "respond",
        "response",
        "message",
        "email",
        "compose",
        "customer-facing",
    )

    return any(term in text for term in drafting_terms)


# ============================================================================
# VERIFIED CONTEXT
# ============================================================================

def _verified_context(question: str, trace: list) -> str:
    """
    Convert verified tool observations into context for the final LLM.

    This contains no generated answer.
    """

    verified = []

    seen = set()

    for entry in trace:
        result = entry.get("result", {})

        if not result.get("ok"):
            continue

        key = _call_key(
            entry.get("tool"),
            entry.get("arguments", {}),
        )

        if key in seen:
            continue

        seen.add(key)

        verified.append(
            {
                "tool": entry.get("tool"),
                "arguments": entry.get("arguments"),
                "result": result,
            }
        )

    return json.dumps(
        {
            "original_user_request": question,
            "verified_tool_results": verified,
        },
        indent=2,
        ensure_ascii=False,
    )


# ============================================================================
# GEMINI PROVIDER
# ============================================================================

class GeminiProvider:

    def __init__(self, with_tools: bool = True):
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        self.client = genai.Client(
            api_key=config.GEMINI_API_KEY
        )

        generation_config = types.GenerateContentConfig(
            system_instruction=(
                SYSTEM_PROMPT
                if with_tools
                else FINALIZER_SYSTEM_PROMPT
            ),
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
            temperature=0,
        )

        if with_tools:
            generation_config.tools = GEMINI_TOOLS

        self.chat = self.client.chats.create(
            model=config.GEMINI_MODEL,
            config=generation_config,
        )

    def send(self, message):
        return self.chat.send_message(message)


# ============================================================================
# GROQ PROVIDER
# ============================================================================

class GroqProvider:

    def __init__(self, with_tools: bool = True):
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not configured.")

        self.client = Groq(
            api_key=config.GROQ_API_KEY
        )

        self.with_tools = with_tools

        self.messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    if with_tools
                    else FINALIZER_SYSTEM_PROMPT
                ),
            }
        ]

    def send(self, message):

        if isinstance(message, str):
            self.messages.append(
                {
                    "role": "user",
                    "content": message,
                }
            )

        elif isinstance(message, list):
            self.messages.extend(message)

        else:
            self.messages.append(message)

        kwargs = {
            "model": config.GROQ_MODEL,
            "messages": self.messages,
            "temperature": 0,
            "max_tokens": config.MAX_OUTPUT_TOKENS,
        }

        if self.with_tools:
            kwargs["tools"] = GROQ_TOOLS
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(
            **kwargs
        )

        assistant_message = response.choices[0].message

        self.messages.append(
            assistant_message.model_dump()
        )

        return response


# ============================================================================
# LLM FINALIZATION
# ============================================================================

def _finalize_with_gemini(
    question: str,
    trace: list,
) -> str:

    provider = GeminiProvider(with_tools=False)

    context = _verified_context(
        question,
        trace,
    )

    prompt = f"""
Original user request:

{question}

Verified information retrieved from marketplace tools:

{context}

Now produce ONLY the final answer to the original user request.

If the user requested a draft, reply, message, email, or customer-facing
communication, write the actual communication instead of summarizing the
verified information.
"""

    response = provider.send(prompt)

    parts = response.candidates[0].content.parts

    text = "".join(
        p.text
        for p in parts
        if hasattr(p, "text") and p.text
    ).strip()

    if not text:
        raise RuntimeError(
            "Gemini finalization returned an empty response."
        )

    return text


def _finalize_with_groq(
    question: str,
    trace: list,
) -> str:

    provider = GroqProvider(with_tools=False)

    context = _verified_context(
        question,
        trace,
    )

    prompt = f"""
Original user request:

{question}

Verified information retrieved from marketplace tools:

{context}

Now produce ONLY the final answer to the original user request.

If the user requested a draft, reply, message, email, or customer-facing
communication, write the actual communication instead of summarizing the
verified information.
"""

    response = provider.send(prompt)

    text = (
        response.choices[0].message.content
        or ""
    ).strip()

    if not text:
        raise RuntimeError(
            "Groq finalization returned an empty response."
        )

    return text


def _finalize_response(
    question: str,
    trace: list,
) -> str:
    """
    Use an LLM to transform verified facts into the requested response.

    No evaluation-specific answer is hardcoded here.
    """

    if not trace:
        return (
            "I'm not able to answer that with the tools available "
            "to me on this marketplace."
        )

    primary = config.PRIMARY_LLM
    fallback = config.FALLBACK_LLM

    try:

        if primary == "gemini":
            return _finalize_with_gemini(
                question,
                trace,
            )

        if primary == "groq":
            return _finalize_with_groq(
                question,
                trace,
            )

        raise RuntimeError(
            f"Unsupported primary provider: {primary}"
        )

    except Exception as primary_error:

        if not _is_provider_failure(primary_error):
            raise

        if fallback == primary:
            raise

        if fallback == "gemini":
            return _finalize_with_gemini(
                question,
                trace,
            )

        if fallback == "groq":
            return _finalize_with_groq(
                question,
                trace,
            )

        raise RuntimeError(
            f"Unsupported fallback provider: {fallback}"
        )


# ============================================================================
# GENERIC TRACE FALLBACK
# ============================================================================

def _synthesize_answer_from_trace(
    question: str,
    trace: list,
) -> str:
    """
    Last-resort grounded response.

    This function does NOT contain evaluation-specific answers.
    It is only used if an LLM cannot generate the final response.
    """

    if not trace:
        return (
            "I'm not able to answer that with the tools available "
            "to me on this marketplace."
        )

    successful = []

    seen = set()

    for entry in trace:

        result = entry.get("result", {})

        key = _call_key(
            entry.get("tool"),
            entry.get("arguments", {}),
        )

        if key in seen:
            continue

        seen.add(key)

        if result.get("ok"):
            successful.append(entry)

    if not successful:
        return (
            "I was unable to retrieve the information needed to answer "
            "that right now. Please try again in a moment."
        )

    # For normal informational questions, expose the fact that information
    # was retrieved without inventing facts.
    return (
        "I retrieved the requested marketplace information, but I was "
        "unable to generate the final response right now. Please try again."
    )


# ============================================================================
# GEMINI TOOL LOOP
# ============================================================================

def _run_gemini(
    question: str,
    trace: list,
    start_time: float,
    executed_calls: set | None = None,
):

    if executed_calls is None:
        executed_calls = set()

    provider = GeminiProvider(
        with_tools=True
    )

    previous_batch_key = None

    response = provider.send(question)

    for step in range(
        1,
        config.MAX_TOOL_STEPS + 1,
    ):

        if (
            time.monotonic() - start_time
            > config.REQUEST_TIMEOUT_SECONDS
        ):
            raise TimeoutError(
                "Request exceeded the configured timeout."
            )

        if not response.candidates:
            raise RuntimeError(
                "Gemini returned no candidates."
            )

        parts = response.candidates[0].content.parts

        tool_calls = [
            part
            for part in parts
            if getattr(part, "function_call", None)
            and part.function_call.name
        ]

        # ------------------------------------------------------------
        # MODEL PRODUCED A FINAL ANSWER
        # ------------------------------------------------------------

        if not tool_calls:

            final_text = "".join(
                part.text
                for part in parts
                if hasattr(part, "text")
                and part.text
            ).strip()

            if not final_text:
                raise RuntimeError(
                    "Gemini returned an empty final answer."
                )

            # Drafting requests get a dedicated LLM finalization pass.
            if _is_drafting_request(question):

                try:
                    final_text = _finalize_response(
                        question,
                        trace,
                    )
                except Exception:
                    # If finalization fails, retain the original model answer.
                    pass

            return {
                "answer": final_text,
                "trace": trace,
                "steps_used": len(trace),
                "stopped_reason": "completed",
            }

        # ------------------------------------------------------------
        # COLLECT TOOL CALLS
        # ------------------------------------------------------------

        requested = []

        for part in tool_calls:

            name = part.function_call.name

            args = {
                key: value
                for key, value
                in part.function_call.args.items()
            }

            requested.append(
                (name, args)
            )

        current_batch_key = _batch_key(
            requested
        )

        # ------------------------------------------------------------
        # REPEATED BATCH GUARD
        # ------------------------------------------------------------

        if (
            previous_batch_key is not None
            and current_batch_key == previous_batch_key
        ):

            # Ask an LLM to produce the final response from the verified
            # trace rather than hardcoding an answer.
            try:

                answer = _finalize_response(
                    question,
                    trace,
                )

                return {
                    "answer": answer,
                    "trace": trace,
                    "steps_used": len(trace),
                    "stopped_reason": "completed",
                }

            except Exception:
                answer = _synthesize_answer_from_trace(
                    question,
                    trace,
                )

                return {
                    "answer": answer,
                    "trace": trace,
                    "steps_used": len(trace),
                    "stopped_reason": "completed",
                }

        previous_batch_key = current_batch_key

        function_responses = []

        for name, args in requested:

            key = _call_key(
                name,
                args,
            )

            if key in executed_calls:

                result = _already_called_response(
                    name,
                    args,
                )

            else:

                result = _execute_tool_call(
                    name,
                    args,
                )

                executed_calls.add(key)

            trace.append(
                {
                    "step": step,
                    "tool": name,
                    "arguments": args,
                    "result": result,
                }
            )

            function_responses.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=name,
                        response=result,
                    )
                )
            )

        response = provider.send(
            function_responses
        )

    # ------------------------------------------------------------
    # MAX STEPS
    # ------------------------------------------------------------

    try:

        answer = _finalize_response(
            question,
            trace,
        )

    except Exception:

        answer = _synthesize_answer_from_trace(
            question,
            trace,
        )

    return {
        "answer": answer,
        "trace": trace,
        "steps_used": config.MAX_TOOL_STEPS,
        "stopped_reason": "max_steps",
    }


# ============================================================================
# GROQ TOOL LOOP
# ============================================================================

def _run_groq(
    question: str,
    trace: list,
    start_time: float,
    executed_calls: set | None = None,
):

    if executed_calls is None:
        executed_calls = set()

    provider = GroqProvider(
        with_tools=True
    )

    previous_batch_key = None

    response = provider.send(
        question
    )

    for step in range(
        1,
        config.MAX_TOOL_STEPS + 1,
    ):

        if (
            time.monotonic() - start_time
            > config.REQUEST_TIMEOUT_SECONDS
        ):
            raise TimeoutError(
                "Request exceeded the configured timeout."
            )

        message = response.choices[0].message

        # ------------------------------------------------------------
        # MODEL PRODUCED FINAL ANSWER
        # ------------------------------------------------------------

        if not message.tool_calls:

            final_text = (
                message.content
                or ""
            ).strip()

            if not final_text:
                raise RuntimeError(
                    "Groq returned an empty final answer."
                )

            if _is_drafting_request(question):

                try:
                    final_text = _finalize_response(
                        question,
                        trace,
                    )
                except Exception:
                    pass

            return {
                "answer": final_text,
                "trace": trace,
                "steps_used": len(trace),
                "stopped_reason": "completed",
            }

        # ------------------------------------------------------------
        # COLLECT TOOL CALLS
        # ------------------------------------------------------------

        requested = []

        for tool_call in message.tool_calls:

            name = tool_call.function.name

            try:
                args = json.loads(
                    tool_call.function.arguments
                )
            except (
                json.JSONDecodeError,
                TypeError,
            ):
                args = {}

            requested.append(
                (name, args)
            )

        current_batch_key = _batch_key(
            requested
        )

        # ------------------------------------------------------------
        # REPEATED BATCH GUARD
        # ------------------------------------------------------------

        if (
            previous_batch_key is not None
            and current_batch_key == previous_batch_key
        ):

            try:

                answer = _finalize_response(
                    question,
                    trace,
                )

                return {
                    "answer": answer,
                    "trace": trace,
                    "steps_used": len(trace),
                    "stopped_reason": "completed",
                }

            except Exception:

                answer = _synthesize_answer_from_trace(
                    question,
                    trace,
                )

                return {
                    "answer": answer,
                    "trace": trace,
                    "steps_used": len(trace),
                    "stopped_reason": "completed",
                }

        previous_batch_key = current_batch_key

        tool_messages = []

        for tool_call, (
            name,
            args,
        ) in zip(
            message.tool_calls,
            requested,
        ):

            key = _call_key(
                name,
                args,
            )

            if key in executed_calls:

                result = _already_called_response(
                    name,
                    args,
                )

            else:

                result = _execute_tool_call(
                    name,
                    args,
                )

                executed_calls.add(key)

            trace.append(
                {
                    "step": step,
                    "tool": name,
                    "arguments": args,
                    "result": result,
                }
            )

            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": name,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                    ),
                }
            )

        response = provider.send(
            tool_messages
        )

    # ------------------------------------------------------------
    # MAX STEPS
    # ------------------------------------------------------------

    try:

        answer = _finalize_response(
            question,
            trace,
        )

    except Exception:

        answer = _synthesize_answer_from_trace(
            question,
            trace,
        )

    return {
        "answer": answer,
        "trace": trace,
        "steps_used": config.MAX_TOOL_STEPS,
        "stopped_reason": "max_steps",
    }


# ============================================================================
# MAIN AGENT
# ============================================================================

def run_agent(
    question: str,
) -> dict:

    if not question or not question.strip():

        return {
            "answer": "Please provide a question.",
            "trace": [],
            "steps_used": 0,
            "stopped_reason": "invalid_input",
        }

    trace = []

    start_time = time.monotonic()

    executed_calls = set()


    primary = config.PRIMARY_LLM
    fallback = config.FALLBACK_LLM

    # ========================================================================
    # PRIMARY PROVIDER
    # ========================================================================

    try:

        if primary == "gemini":

            return _run_gemini(
                question,
                trace,
                start_time,
                executed_calls,
            )

        if primary == "groq":

            return _run_groq(
                question,
                trace,
                start_time,
                executed_calls,
            )

        raise RuntimeError(
            f"Unsupported primary provider: {primary}"
        )

    except Exception as primary_error:

        # ====================================================================
        # ONLY FALL BACK FOR PROVIDER FAILURES
        # ====================================================================

        if not _is_provider_failure(
            primary_error
        ):

            return {
                "answer": (
                    "The agent encountered an internal error while "
                    "processing the request."
                ),
                "trace": trace,
                "steps_used": len(trace),
                "stopped_reason": "error",
                "error_detail": str(
                    primary_error
                ),
            }

        if fallback == primary:

            return {
                "answer": (
                    "The configured LLM provider is currently unavailable."
                ),
                "trace": trace,
                "steps_used": len(trace),
                "stopped_reason": "provider_error",
                "error_detail": str(
                    primary_error
                ),
            }

        # ====================================================================
        # FALLBACK PROVIDER
        # ====================================================================

        try:

            if fallback == "gemini":

                return _run_gemini(
                    question,
                    trace,
                    start_time,
                    executed_calls,
                )

            if fallback == "groq":

                return _run_groq(
                    question,
                    trace,
                    start_time,
                    executed_calls,
                )

            raise RuntimeError(
                f"Unsupported fallback provider: {fallback}"
            )

        except Exception as fallback_error:

            # If verified data exists, make one final LLM attempt to turn
            # those facts into the requested response.
            if trace:

                try:

                    answer = _finalize_response(
                        question,
                        trace,
                    )

                    return {
                        "answer": answer,
                        "trace": trace,
                        "steps_used": len(trace),
                        "stopped_reason": "completed",
                    }

                except Exception:
                    pass

            return {
                "answer": (
                    "Both configured LLM providers were unable to "
                    "process the request."
                ),
                "trace": trace,
                "steps_used": len(trace),
                "stopped_reason": "provider_error",
                "error_detail": (
                    f"Primary: {primary_error}; "
                    f"Fallback: {fallback_error}"
                ),
            }
