"""
The agent loop.

This is the whole of the "agent" part, and it is deliberately short enough to
read on a slide. A model, a set of tools, and a loop that runs until the model
stops asking for tools.

WHY THIS IS HAND-WRITTEN RATHER THAN A FRAMEWORK.
   LangGraph, CrewAI and the rest give you checkpointing, human-in-the-loop
   interrupts, branching state machines and multi-agent handoff. This is a
   single-turn, read-only question answerer. It needs none of that, and a
   framework would add a layer of abstraction between the audience and the
   thing they are trying to understand. If this grew to need durable state
   across turns or a human approval step, a framework would start earning its
   place.

WHAT THE LOOP ACTUALLY DOES.
   1. Send the question plus the tool schemas to the model.
   2. If the model asks for tools, run them and send the results back.
   3. Repeat until the model answers with text instead of a tool request.
   4. Stop hard at MAX_ITERATIONS regardless.

   The iteration cap matters. An agent that can loop can loop forever, and
   "it kept calling tools until the bill was enormous" is a real failure
   mode, not a theoretical one.

WHAT THE MODEL IS NOT TRUSTED WITH.
   It never sees the UserContext and cannot set it. Identity is passed to the
   tools out of band by this loop. The model can ask for any tool it likes;
   whether that call is permitted is decided in the tool, not here and not in
   the prompt.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS, UserContext
from trace import TRACE, AccessDenied

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = os.getenv("MODEL", "claude-sonnet-4-5-20250929")
MAX_ITERATIONS = 6

from datetime import date

SYSTEM_PROMPT = f"""Today's date is {date.today().isoformat()}. \
The incident data covers roughly the twelve months before today. \
Resolve relative time expressions such as "last quarter", "last month" \
or "recently" against today's date.

You are an incident response assistant. You answer \
questions about production incidents using only the tools provided.

How to work:

- Decide which tools this specific question needs. Some questions need one \
tool, some need several. A question about what happened and who owns it \
needs both the written history and the structured records.
- Questions about how many, how often, or how long on average require \
incident_stats. Searching documents cannot compute an aggregate.
- Only about 14 of the 200 incidents have a written postmortem. If you \
searched documents and found nothing, the incident may still exist in the \
structured table. Check before concluding something never happened.

How to answer:

- Ground every claim in what the tools returned. Cite specific incident ids \
(for example INC-0100) so the reader can verify. If a claim comes from a \
postmortem, say which one.
- If the data does not answer the question, say so plainly and say what you \
do have. Never fill a gap with what you know about software in general. A \
confident wrong answer during an incident is worse than no answer.
- If a tool refuses your call because the user is not permitted to access \
that data, tell the user plainly that they are not authorised to see it and \
who they could ask. Do not attempt to obtain the same information another \
way, and do not pretend the data does not exist.
- Be brief. The person reading this is usually in the middle of an incident.
"""


def run_tool(name, arguments, ctx):
    """Execute one tool call and return a string result for the model."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"ERROR: no such tool '{name}'"
    try:
        result = fn(ctx, **arguments)
        return json.dumps(result, default=str)
    except AccessDenied as exc:
        # The refusal is returned to the model as data, not raised. The model
        # needs to know it was refused so it can tell the user, rather than
        # the loop crashing or silently returning nothing.
        return json.dumps({
            "error": "access_denied",
            "message": str(exc),
            "guidance": "Tell the user they are not authorised to see this.",
        })
    except Exception as exc:
        return json.dumps({"error": type(exc).__name__, "message": str(exc)})


def ask(question: str, ctx: UserContext, verbose: bool = False) -> str:
    client = Anthropic()
    messages = [{"role": "user", "content": question}]

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content
                           if b.type == "text")

        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"  → {block.name}({block.input})")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": run_tool(block.name, block.input, ctx),
            })

        messages.append({"role": "user", "content": results})

    return ("Stopped after the maximum number of tool calls without reaching "
            "an answer.")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Ask the incident assistant a question.")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--user", default="p.zinzuvadia",
                        help="User id of the caller.")
    parser.add_argument("--role", default="engineer",
                        help="engineer | incident_commander | contractor")
    parser.add_argument("--trace", action="store_true",
                        help="Print the tool call trace after answering.")
    parser.add_argument("--verbose", action="store_true",
                        help="Print tool calls as they happen.")
    args = parser.parse_args()

    ctx = UserContext(user_id=args.user, role=args.role)
    question = " ".join(args.question)

    print(f"\n\033[1mQ [{ctx.user_id} / {ctx.role}]:\033[0m {question}\n")
    answer = ask(question, ctx, verbose=args.verbose)
    print(answer)

    if args.trace:
        print("\n" + "=" * 78)
        print("TRACE")
        print("=" * 78)
        print(TRACE.render())
    print()


if __name__ == "__main__":
    main()
