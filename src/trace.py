"""
Trace layer.

Traditional monitoring answers "is the service up". That question is useless
for an agent, because an agent can be completely healthy and still have
reached its answer through the wrong tools, on the wrong data, for the wrong
user.

So every tool call records: who asked, which tool, what arguments, how long it
took, what came back, and whether it was refused. That record is the only
honest way to answer "why did it say that", and it is the thing you need when
somebody disputes an answer three weeks later.

This is deliberately boring. A list of dictionaries and a decorator. The point
is not the implementation, it is that the boundary where tools are called is
the only place you can capture this, so it has to be built in at that boundary
rather than bolted on afterwards.
"""

import functools
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    tool: str
    user: str
    role: str
    arguments: dict
    duration_ms: float
    outcome: str          # "ok" | "denied" | "error"
    result_summary: str


@dataclass
class Trace:
    events: list = field(default_factory=list)

    def record(self, event: TraceEvent):
        self.events.append(event)

    def clear(self):
        self.events = []

    def render(self) -> str:
        if not self.events:
            return "(no tool calls)"

        lines = []
        header = (f"{'#':<3} {'TOOL':<20} {'USER':<12} {'OUTCOME':<9} "
                  f"{'MS':>7}  ARGUMENTS")
        lines.append(header)
        lines.append("-" * len(header))
        for i, e in enumerate(self.events, 1):
            args = ", ".join(f"{k}={v!r}" for k, v in e.arguments.items()
                             if v is not None)
            lines.append(f"{i:<3} {e.tool:<20} {e.user:<12} {e.outcome:<9} "
                         f"{e.duration_ms:>7.1f}  {args[:60]}")
            lines.append(f"{'':<3} {'└─ ' + e.result_summary[:88]}")
        total = sum(e.duration_ms for e in self.events)
        lines.append("-" * len(header))
        lines.append(f"{len(self.events)} tool call(s), {total:.1f} ms total "
                     f"in tools")
        return "\n".join(lines)


# One trace per process is enough for a single-user CLI demo. In a real
# deployment this would be per-request and carry a correlation id.
TRACE = Trace()


class AccessDenied(Exception):
    """Raised inside a tool when the caller is not permitted to reach data.

    Deliberately an exception rather than a silent empty result: a refusal is
    an event worth recording, and the agent should be told clearly that it was
    refused rather than being allowed to assume the data does not exist.
    """


def traced(summarise):
    """Wrap a tool so every call is recorded.

    `summarise` turns the return value into one short line for the trace.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(ctx, **kwargs):
            start = time.perf_counter()
            try:
                result = fn(ctx, **kwargs)
            except AccessDenied as exc:
                TRACE.record(TraceEvent(
                    tool=fn.__name__,
                    user=ctx.user_id,
                    role=ctx.role,
                    arguments=kwargs,
                    duration_ms=(time.perf_counter() - start) * 1000,
                    outcome="denied",
                    result_summary=str(exc),
                ))
                raise
            except Exception as exc:
                TRACE.record(TraceEvent(
                    tool=fn.__name__,
                    user=ctx.user_id,
                    role=ctx.role,
                    arguments=kwargs,
                    duration_ms=(time.perf_counter() - start) * 1000,
                    outcome="error",
                    result_summary=f"{type(exc).__name__}: {exc}",
                ))
                raise

            TRACE.record(TraceEvent(
                tool=fn.__name__,
                user=ctx.user_id,
                role=ctx.role,
                arguments=kwargs,
                duration_ms=(time.perf_counter() - start) * 1000,
                outcome="ok",
                result_summary=summarise(result),
            ))
            return result
        return wrapper
    return decorator
