"""
The tool layer.

Five read-only tools over two data sources. This file is where the actual
engineering of the system lives, and there are three decisions in it worth
defending.

DECISION 1: AUTHORIZATION IS ENFORCED HERE, NOT IN THE PROMPT.
   You cannot ask a model nicely to keep a secret. If a tool can return a
   phone number, some prompt will eventually get it to return the phone
   number. So the check runs inside the tool, where the data is reached, and
   the model has no way to route around it.

DECISION 2: THE REDACTION IS APPLIED AT THE DATA LAYER, NOT PER TOOL.
   The obvious mistake is to gate only get_oncall_contact and leave contact
   fields sitting in the rows returned by get_incident. Then the restriction
   is theatre: the caller just asks for the incident instead. Every path to
   the table goes through the same redaction function, so there is exactly
   one place where the rule is expressed.

DECISION 3: TOOL DESCRIPTIONS ARE DOCUMENTATION WITH A NON-HUMAN READER.
   The model chooses which tool to call by reading these descriptions. A
   vague description does not produce a confused user, it produces a wrong
   tool call and therefore a wrong answer. They are written to make the
   boundaries between tools unambiguous, including saying explicitly what
   each tool is NOT for.

Everything is read-only. There is no tool that restarts a service, updates a
ticket, or writes anything at all. That is a deliberate boundary, not an
unfinished feature: every tool you add is another thing the agent can get
wrong and another thing you have to secure.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import chromadb

from trace import traced, AccessDenied

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "incidents.db"
CHROMA_DIR = ROOT / "data" / "chroma"

# Fields that carry personal contact information. Redacted unless the caller
# holds a role that is permitted to see them.
RESTRICTED_FIELDS = {"contact_name", "contact_phone"}

# Roles permitted to see contact details. In a real system this comes from the
# identity provider, and the same group membership that governs every other
# system governs this one. The agent does not have its own parallel
# permission model, which is the single most important property here.
ROLES_WITH_CONTACT_ACCESS = {"engineer", "incident_commander"}


@dataclass
class UserContext:
    """Who is asking. Supplied by the caller, never by the model.

    The model never sees this object and cannot modify it. It is passed to
    every tool out of band, the same way a request context carries an
    authenticated principal in a normal service.
    """
    user_id: str
    role: str

    @property
    def may_see_contacts(self) -> bool:
        return self.role in ROLES_WITH_CONTACT_ACCESS


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _redact(row: dict, ctx: UserContext) -> dict:
    """Single point where the contact-field rule is applied."""
    if ctx.may_see_contacts:
        return row
    return {k: v for k, v in row.items() if k not in RESTRICTED_FIELDS}


# ---------------------------------------------------------------------------
# Tool 1: semantic search over postmortem documents
# ---------------------------------------------------------------------------

_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_collection("postmortems")
    return _collection


@traced(lambda r: f"{len(r)} chunk(s) from "
                  f"{len(set(x['incident_id'] for x in r))} postmortem(s)")
def search_postmortems(ctx, query: str, service: str = None,
                       limit: int = 10) -> list:
    where = {"service": service} if service else None
    res = _get_collection().query(
        query_texts=[query],
        n_results=limit,
        where=where,
    )
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0],
                               res["distances"][0]):
        out.append({
            "incident_id": meta["incident_id"],
            "service": meta["service"],
            "severity": meta["severity"],
            "date": meta["date"],
            "section": meta["section"],
            "source_file": meta["source_file"],
            "relevance": round(1 / (1 + dist), 3),
            "text": doc,
        })
    return out


# ---------------------------------------------------------------------------
# Tool 2: filtered list of incidents from the structured table
# ---------------------------------------------------------------------------

@traced(lambda r: f"{len(r)} incident(s)")
def list_incidents(ctx, service: str = None, severity: str = None,
                   root_cause_category: str = None, since: str = None,
                   until: str = None, limit: int = 100) -> list:
    clauses, params = [], []
    if service:
        clauses.append("service = ?")
        params.append(service)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if root_cause_category:
        clauses.append("root_cause_category = ?")
        params.append(root_cause_category)
    if since:
        clauses.append("opened_at >= ?")
        params.append(since)
    if until:
        clauses.append("opened_at <= ?")
        params.append(until)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (f"SELECT * FROM incidents {where} "
           f"ORDER BY opened_at DESC LIMIT ?")
    params.append(min(limit, 50))

    with _connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, params)]
    return [_redact(r, ctx) for r in rows]


# ---------------------------------------------------------------------------
# Tool 3: one incident by id
# ---------------------------------------------------------------------------

@traced(lambda r: r["incident_id"] if r else "not found")
def get_incident(ctx, incident_id: str) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ?",
            (incident_id,)).fetchone()
    if row is None:
        return {}
    return _redact(dict(row), ctx)


# ---------------------------------------------------------------------------
# Tool 4: aggregates. This is the one retrieval cannot do.
# ---------------------------------------------------------------------------

@traced(lambda r: f"n={r['incident_count']}, "
                  f"median={r['median_resolution_minutes']}min")
def incident_stats(ctx, service: str = None, severity: str = None,
                   since: str = None, until: str = None,
                   group_by: str = None) -> dict:
    clauses, params = [], []
    if service:
        clauses.append("service = ?")
        params.append(service)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if since:
        clauses.append("opened_at >= ?")
        params.append(since)
    if until:
        clauses.append("opened_at <= ?")
        params.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect() as conn:
        durations = [r[0] for r in conn.execute(
            f"SELECT duration_minutes FROM incidents {where} "
            f"ORDER BY duration_minutes", params)]

        breakdown = {}
        if group_by in {"service", "severity", "root_cause_category",
                        "owning_team"}:
            breakdown = {
                r[0]: r[1] for r in conn.execute(
                    f"SELECT {group_by}, COUNT(*) FROM incidents {where} "
                    f"GROUP BY {group_by} ORDER BY COUNT(*) DESC", params)
            }

    n = len(durations)
    if n == 0:
        return {"incident_count": 0, "median_resolution_minutes": None,
                "mean_resolution_minutes": None, "longest_minutes": None,
                "breakdown": {}}

    median = durations[n // 2] if n % 2 else \
        (durations[n // 2 - 1] + durations[n // 2]) // 2

    return {
        "incident_count": n,
        "median_resolution_minutes": median,
        "mean_resolution_minutes": round(sum(durations) / n),
        "longest_minutes": durations[-1],
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# Tool 5: on-call contact. Gated.
# ---------------------------------------------------------------------------

@traced(lambda r: f"{r['owning_team']} / {r['contact_name']}")
def get_oncall_contact(ctx, service: str) -> dict:
    if not ctx.may_see_contacts:
        raise AccessDenied(
            f"role '{ctx.role}' is not permitted to read contact details"
        )

    with _connect() as conn:
        row = conn.execute(
            "SELECT DISTINCT service, owning_team, contact_name, "
            "contact_phone FROM incidents WHERE service = ?",
            (service,)).fetchone()
    if row is None:
        return {}
    return dict(row)


# ---------------------------------------------------------------------------
# Tool schemas. These are what the model reads in order to choose.
#
# Note how much work the descriptions do. Each one says what the tool is for,
# and several say explicitly what it is NOT for, because the most common
# failure is not a tool that breaks but a tool that gets picked for the wrong
# question.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "search_postmortems",
        "description": (
            "Search written postmortem documents by meaning, for questions "
            "about WHY something happened, what the root cause was, what was "
            "done to fix it, or what was learned. Only about 14 of the 200 "
            "incidents have a postmortem, so this covers depth, not "
            "coverage. Do not use this to count incidents or to compute "
            "statistics; it searches prose and cannot aggregate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language description of what you "
                                   "are looking for. Describe the symptom or "
                                   "the concept, not keywords.",
                },
                "service": {
                    "type": "string",
                    "description": "Optional. Restrict to one service. Omit "
                                   "when looking for a pattern across "
                                   "services.",
                },
                "limit": {"type": "integer",
                          "description": "Max rows. Omit unless the user "
                                         "asked for a specific number; the "
                                         "default returns full history."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_incidents",
        "description": (
            "List incidents from the structured incident table, with optional "
            "filters. Use this for questions about WHICH incidents happened, "
            "WHEN, or HOW MANY of a specific kind, where the caller wants the "
            "individual records. Covers all 200 incidents. Returns records "
            "only, not written analysis; use search_postmortems for why "
            "something happened."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string",
                            "description": "One of: payments, checkout, auth, "
                                           "search, inventory, notifications, "
                                           "reporting, media-upload."},
                "severity": {"type": "string",
                             "description": "Sev-1, Sev-2 or Sev-3."},
                "root_cause_category": {
                    "type": "string",
                    "description": "e.g. connection_pool, memory_leak, "
                                   "deploy_regression, downstream_timeout.",
                },
                "since": {"type": "string",
                          "description": "ISO date, inclusive lower bound on "
                                         "opened_at. e.g. 2026-07-01"},
                "until": {"type": "string",
                          "description": "ISO date, inclusive upper bound."},
                "limit": {"type": "integer",
                          "description": "Max rows. Omit unless the user "
                                         "asked for a specific number; the "
                                         "default returns full history."},
            },
        },
    },
    {
        "name": "get_incident",
        "description": (
            "Fetch one incident record by its exact id, e.g. INC-0100. Use "
            "when an id is already known, typically one returned by "
            "search_postmortems or list_incidents, and full details are "
            "needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string",
                                "description": "Exact id, format INC-0000."},
            },
            "required": ["incident_id"],
        },
    },
    {
        "name": "incident_stats",
        "description": (
            "Compute aggregate statistics over the incident table: count, "
            "median and mean resolution time, longest incident, and an "
            "optional breakdown by a field. Use this for any question "
            "involving how many, how often, how long on average, or which "
            "service or team has the most. This is the only tool that can "
            "answer aggregate questions; searching documents cannot."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "severity": {"type": "string"},
                "since": {"type": "string", "description": "ISO date."},
                "until": {"type": "string", "description": "ISO date."},
                "group_by": {
                    "type": "string",
                    "description": "Optional breakdown field: service, "
                                   "severity, root_cause_category or "
                                   "owning_team.",
                },
            },
        },
    },
    {
        "name": "get_oncall_contact",
        "description": (
            "Get the owning team and the on-call contact name and phone "
            "number for a service. Use when the caller needs to know who to "
            "contact or escalate to. Access is restricted: callers without "
            "the required role will be refused, and that refusal must be "
            "reported to the user plainly rather than worked around."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string",
                            "description": "The service whose on-call contact "
                                           "is needed."},
            },
            "required": ["service"],
        },
    },
]

TOOL_FUNCTIONS = {
    "search_postmortems": search_postmortems,
    "list_incidents": list_incidents,
    "get_incident": get_incident,
    "incident_stats": incident_stats,
    "get_oncall_contact": get_oncall_contact,
}
