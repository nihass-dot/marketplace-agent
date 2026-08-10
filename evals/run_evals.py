"""
Runs the eval questions from eval_questions.md against the agent directly
(not through the HTTP layer, to keep this fast and dependency-free) and
prints the answer + trace for manual inspection.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python -m evals.run_evals

Note on non-determinism: this script runs each question once. Because the
model is non-deterministic, a single run is a spot-check, not a proof of
correctness. For anything beyond a take-home, this should run N times per
question (e.g. N=5) and report a pass rate per question, since a flaky 1/5
question is a real production risk that a single run hides. See README
"What I'd add" for how I'd wire that up given more time.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import run_agent

QUESTIONS = [
    "Where is order ORD1001?",
    "Why is order ORD1002 delayed?",
    "What's the status of order ORD9999?",
    "Can you look up order ORD_ERROR?",
    "What do customers say about seller SEL02?",
    "Does seller SEL03 have any reviews?",
    "Give me a full profile of seller SEL01 including their rating and recent reviews.",
    "Draft a reply to the buyer of ORD1002 explaining the delay.",
    "What's the weather in Mumbai today?",
    "What's our refund policy for damaged goods?",
]


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: set ANTHROPIC_API_KEY before running evals.")
        sys.exit(1)

    for i, q in enumerate(QUESTIONS, start=1):
        print("=" * 80)
        print(f"[{i}] Q: {q}")
        result = run_agent(q)
        print(f"Answer: {result['answer']}")
        print(f"Stopped reason: {result['stopped_reason']}   Steps used: {result['steps_used']}")
        print("Trace:")
        print(json.dumps(result["trace"], indent=2))
        print()


if __name__ == "__main__":
    main()
