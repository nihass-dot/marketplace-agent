# Eval Set

10 example questions used to sanity-check the agent. `run_evals.py` runs all
of them against the live agent and prints the answer + trace + a pass/fail
against the expectation described here.

| # | Question | Expected behavior |
|---|----------|--------------------|
| 1 | "Where is order ORD1001?" | Calls `lookup_order`, reports status "shipped" and expected delivery date, grounded in tool output. |
| 2 | "Why is order ORD1002 delayed?" | Calls `lookup_order`, reports the `delay_reason` field ("inventory shortage"). |
| 3 | "What's the status of order ORD9999?" | Calls `lookup_order`, gets `found: false`, tells user the order does not exist. Must NOT invent a status. |
| 4 | "Can you look up order ORD_ERROR?" | Calls `lookup_order`, tool raises a simulated backend error, agent tells user it couldn't retrieve the info — does not fabricate an answer to paper over the failure. |
| 5 | "What do customers say about seller SEL02?" | Calls `search_reviews`, summarizes the 3 reviews (mentions the negative tone / low ratings) without inventing quotes not in the data. |
| 6 | "Does seller SEL03 have any reviews?" | Calls `search_reviews`, seller not found -> agent says so. (Also tests: agent should not confuse "no reviews" with "seller doesn't exist" — SEL03 isn't in SELLERS at all.) |
| 7 | "Give me a full profile of seller SEL01 including their rating and recent reviews." | Calls both `get_seller_info` AND `search_reviews`, combines both into one grounded answer — tests multi-tool orchestration. |
| 8 | "Draft a reply to the buyer of ORD1002 explaining the delay." | Calls `lookup_order` first to get the real delay reason, then drafts a short reply referencing that reason — tests that "creative" output is still grounded in a prior tool call rather than invented. |
| 9 | "What's the weather in Mumbai today?" | Out-of-scope. Agent should politely refuse — no tool call, or a refusal without guessing an answer. |
| 10 | "What's our refund policy for damaged goods?" | No tool exists for this. Agent should say it doesn't have this information rather than guessing a policy. |

## What "pass" means here
For 1, 2, 5, 7, 8: the agent called the right tool(s) and the answer's factual
claims all trace back to a `result` in the trace (spot-checked by hand for
this take-home; see "What I'd add" in README for automating this).

For 3, 4, 6, 9, 10: the agent explicitly declines / reports "not found" /
reports failure, rather than confidently answering with something not in the
tool results.
