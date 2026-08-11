# """
# Runs the eval questions from eval_questions.md against the agent directly
# (not through the HTTP layer, to keep this fast and dependency-free) and
# prints the answer + trace for manual inspection.

# Usage:
#     export ANTHROPIC_API_KEY=sk-...
#     python -m evals.run_evals

# Note on non-determinism: this script runs each question once. Because the
# model is non-deterministic, a single run is a spot-check, not a proof of
# correctness. For anything beyond a take-home, this should run N times per
# question (e.g. N=5) and report a pass rate per question, since a flaky 1/5
# question is a real production risk that a single run hides. See README
# "What I'd add" for how I'd wire that up given more time.
# """

# import json
# import sys
# import os

# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# from src.agent import run_agent

# QUESTIONS = [
#     "Where is order ORD1001?",
#     "Why is order ORD1002 delayed?",
#     "What's the status of order ORD9999?",
#     "Can you look up order ORD_ERROR?",
#     "What do customers say about seller SEL02?",
#     "Does seller SEL03 have any reviews?",
#     "Give me a full profile of seller SEL01 including their rating and recent reviews.",
#     "Draft a reply to the buyer of ORD1002 explaining the delay.",
#     "What's the weather in Mumbai today?",
#     "What's our refund policy for damaged goods?",
# ]


# def main():
#     if not os.environ.get("GEMINI_API_KEY"):
#         print("ERROR: set GEMINI_API_KEY before running evals.")
#         sys.exit(1)

#     for i, q in enumerate(QUESTIONS, start=1):
#         print("=" * 80)
#         print(f"[{i}] Q: {q}")
#         result = run_agent(q)
#         print(f"Answer: {result['answer']}")
#         print(f"Stopped reason: {result['stopped_reason']}   Steps used: {result['steps_used']}")
#         print("Trace:")
#         print(json.dumps(result["trace"], indent=2))
#         print()


# if __name__ == "__main__":
#     main()
"""
Runs the evaluation questions against the agent.

The agent itself decides which LLM provider to use:

    Gemini -> primary
    Groq   -> fallback when Gemini is unavailable

Usage:

    python .\evals\run_evals.py

The evaluator runs every question once.

A checkpoint file prevents already completed questions
from consuming additional API calls.

Delete evals/checkpoint.json if you want to run
the entire evaluation again.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

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


CHECKPOINT_FILE = Path(
    __file__
).parent / "checkpoint.json"


def load_checkpoint():

    if not CHECKPOINT_FILE.exists():
        return {
            "completed": []
        }

    try:

        with open(
            CHECKPOINT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):
            return {
                "completed": []
            }

        data.setdefault(
            "completed",
            []
        )

        return data

    except Exception:

        return {
            "completed": []
        }


def save_checkpoint(completed):

    with open(
        CHECKPOINT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "completed": completed
            },
            f,
            indent=2
        )


def main():

    if not os.environ.get("GEMINI_API_KEY"):

        print(
            "WARNING: GEMINI_API_KEY is not configured."
        )

    if not os.environ.get("GROQ_API_KEY"):

        print(
            "WARNING: GROQ_API_KEY is not configured."
        )

    checkpoint = load_checkpoint()

    completed = set(
        checkpoint.get(
            "completed",
            []
        )
    )

    print(
        f"Already completed: "
        f"{sorted(completed)}"
    )

    for i, question in enumerate(
        QUESTIONS,
        start=1
    ):

        if i in completed:

            print(
                f"[{i}] SKIPPED - checkpoint already completed"
            )

            continue

        print("=" * 80)

        print(
            f"[{i}] Q: {question}"
        )

        result = run_agent(
            question
        )

        print(
            f"Answer: {result['answer']}"
        )

        print(
            f"Stopped reason: "
            f"{result['stopped_reason']}   "
            f"Steps used: "
            f"{result['steps_used']}"
        )

        print("Trace:")

        print(
            json.dumps(
                result["trace"],
                indent=2
            )
        )

        print()

        # Only checkpoint after the question
        # completed successfully.
        if result["stopped_reason"] in {
            "completed",
            "max_steps",
        }:

            completed.add(i)

            save_checkpoint(
                sorted(completed)
            )

            print(
                f"Checkpoint updated: "
                f"{sorted(completed)}"
            )

        else:

            print(
                f"Question {i} was NOT checkpointed "
                f"because it ended with "
                f"{result['stopped_reason']}."
            )


if __name__ == "__main__":
    main()