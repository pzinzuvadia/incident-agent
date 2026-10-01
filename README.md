# Incident Response Agent

An agent that answers plain-language questions about production incidents by
searching written postmortems, querying a structured incident history, and
enforcing who is allowed to see what at the tool layer.

---

The loop that makes this an "agent" is about 25 lines and took an afternoon.

Everything that took actual thought sits around it: how documents get cut up
before they are ever embedded, how tools are described so the model picks the
right one, where the permission check lives, and what you can see after the
fact. Those four things are what this repo is about. Incident response is just
the vehicle.

The narrative version — the problem, why the obvious alternatives fall short,
and what this means beyond one domain — is here: **[link to Medium post]**.
This README is the implementation reasoning.

### Who this is for

Anyone putting an LLM in front of data that is partly in a database and partly
in documents, where not everyone should see everything.

- **Building a RAG system?** [Retrieval](#1-retrieval-quality-is-decided-at-ingestion-not-at-query-time)
  and [tool descriptions](#2-tool-descriptions-are-documentation-with-a-non-human-reader)
  are the sections with the transferable parts.
- **Worried about what an agent can reach?**
  [Authorization](#3-authorization-belongs-in-the-tool-not-the-prompt) and
  [observability](#4-monitoring-tells-you-the-service-is-up-it-does-not-tell-you-what-the-agent-did).
- **Deciding whether to build an agent at all?**
  [When not to build this](#when-not-to-build-this) first. It is the shortest
  section and it will save the most time.
- **Just want to run it?** [Setup](#running-it).

---

## What it does

```bash
python src/agent.py "payments latency is spiking again, has this happened before and who do I talk to?" --trace
```

Four questions, four different shapes of work.

**A question that spans both data sources.**

> *payments latency is spiking again, has this happened before and who do I
> talk to?*

Returns a five-incident recurring failure (INC-0020, INC-0076, INC-0100,
INC-0144, INC-0187), the pattern connecting them, and the on-call contact.
Three tool calls: semantic search over documents, a structured query for
service history, a contact lookup. No single source answers it.

**An aggregate.**

> *how many Sev-1 incidents did we have last quarter and what was the median
> time to resolve?*

Five, median 90 minutes. One tool call. Vector search cannot answer this at
any level of retrieval quality — counting is not a retrieval problem. If your
users ask "how many" or "how often", retrieval alone will not serve them.

**The same question, a different user.**

```bash
python src/agent.py "...same question..." --user ext.contractor --role contractor --trace
```

Identical incident history. The contact tool is refused at the tool layer and
the agent reports the refusal rather than inventing a name or implying the
data does not exist.

**Something it does not have.**

> *what did the payments outages cost us in lost revenue?*

Zero tool calls. It states what it does have, says it has no revenue data,
and suggests who would. No fabricated number.

---

## Architecture

```
            question + role
                   │
                   ▼
         ┌───────────────────┐
         │   agent loop      │   decides which tools this question needs,
         │   (src/agent.py)  │   runs them, repeats until it can answer
         └─────────┬─────────┘
                   │  tool calls
                   ▼
         ┌───────────────────┐
         │   tool layer      │   5 read-only tools
         │   (src/tools.py)  │   authorization enforced HERE
         └────┬─────────┬────┘
              │         │
      ┌───────▼──┐   ┌──▼─────────────┐
      │ Chroma   │   │ SQLite         │
      │ 69 chunks│   │ 200 incidents  │
      │ 14 docs  │   │ 8 services     │
      └──────────┘   └────────────────┘
              │         │
              └────┬────┘
                   ▼
              trace record       every call: who, what, args, latency, outcome
```

One request, end to end:

1. The caller supplies a question and a `UserContext` (user id + role). The
   model never sees the context and cannot set it.
2. The loop sends the question and the five tool schemas to the model.
3. The model returns tool calls. The loop executes each against real data,
   passing the context out of band.
4. Each tool checks what the caller may reach, and records the call.
5. Results go back to the model. It asks for more tools, or answers.
6. The loop stops when the model answers, or at six iterations.

Swap Chroma for any vector store and SQLite for any warehouse and nothing
about the shape changes.

---

## The data

**The general point:** when knowledge is split across a database and a pile of
documents, the split is usually depth versus coverage. The database knows
about everything shallowly. The documents know a few things deeply. Questions
that matter tend to need both, which is the entire reason a tool-using agent
earns its place here.

**Here:** 200 incidents across 8 services over 12 months in SQLite, and 14
markdown postmortems in `data/postmortems/`.

Only 14 of the 200 have a postmortem, which is realistic — nobody writes one
for a routine Sev-3 — and it does real work. Any question about *why* needs
the documents. Any question about *how often* needs the table.

`generate_data.py` is seeded, so the incident IDs in this README will match
what you see. Three things are planted deliberately:

- **A recurring failure across five payments incidents**, each with a
  different proximate cause (undersized pool, slow query, slow dependency,
  driver default change, traffic spike). There is a real pattern to find, not
  just five hits.
- **None of those five say "connection pool" in the title or summary.** The
  phrase appears only in root-cause sections, so a latency question has to
  retrieve them semantically rather than lexically. If you are building a
  retrieval demo, plant something your keyword search would miss — otherwise
  you have not demonstrated anything.
- **The same failure mode in a second service** (INC-0117, inventory), so
  cross-service patterns are findable.

---

## 1. Retrieval quality is decided at ingestion, not at query time

By the time a query arrives, the outcome is mostly already determined. Four
decisions in `src/ingest.py` do more for answer quality than anything in the
prompt.

**Chunk on semantic boundaries, not character counts.** A fixed-size splitter
cuts a root cause in half and staples the tail to the front of a timeline.
Postmortems have natural sections — summary, timeline, root cause, resolution,
notes — so each chunk is one section of one document and is about exactly one
thing. 14 documents, 69 chunks.

Whatever your documents are, find the boundary the author already put there.
Markdown headings, API endpoints, ticket fields. It is almost always better
than a character count.

**Prepend context to the chunk before embedding it.** A chunk reading *"Pool
size raised from 20 to 40 per pod"* is ambiguous alone. What gets embedded is:

```
Root cause for INC-0100 (payments, Sev-1, 2026-03-18): Elevated payments
latency and checkout failures

The upstream card processor was experiencing a partial degradation...
```

Cheap, and it measurably improves matching against conversational questions.

**Carry parent metadata on every chunk.** `incident_id`, `service`,
`severity`, `date`, `section`. This is what lets a retrieved chunk be traced
back to a structured record, and it lets retrieval be filtered by a field
rather than hoping the embedding encoded it.

**Decide what not to index.** Follow-up checklists are excluded here —
mostly `[ ] not done` boilerplate that dilutes retrieval without adding
meaning. Exclusion is a retrieval decision and it is rarely discussed.

Inspect retrieval without running the agent or spending a token:

```bash
python src/check_retrieval.py
```

The query *"service is slow but the database is healthy"* returns the chunk
saying, in different words, that the database was fine throughout. Nothing
lexical about that match.

Embeddings are computed locally by the model Chroma ships with. For a demo
that is convenience. Where the documents are the sensitive asset, it is a
governance decision worth making on purpose.

---

## 2. Tool descriptions are documentation with a non-human reader

The model picks tools by reading their descriptions. A vague description does
not produce a confused user who asks a follow-up question — it produces a
wrong tool call and a wrong answer, silently.

Five tools, all read-only:

| Tool | Reaches | Why separate |
|---|---|---|
| `search_postmortems` | Chroma | Semantic search for *why* something happened |
| `list_incidents` | SQLite | Filtered records — which, when, what kind |
| `get_incident` | SQLite | One record by id |
| `incident_stats` | SQLite | Counts, median, mean, breakdowns |
| `get_oncall_contact` | SQLite | Who to call. Access-restricted. |

The useful habit is saying what a tool is **not** for:

> `search_postmortems`: "...Only about 14 of the 200 incidents have a
> postmortem, so this covers depth, not coverage. Do not use this to count
> incidents or to compute statistics; it searches prose and cannot aggregate."

> `incident_stats`: "...This is the only tool that can answer aggregate
> questions; searching documents cannot."

Same discipline as good API documentation, for a reader that will never ask
you to clarify.

**How much the description controls:** raising a Python default parameter did
nothing here, because the model was passing the value explicitly — it had read
the number out of the description text. Descriptions are not commentary. They
are behaviour.

---

## 3. Authorization belongs in the tool, not the prompt

You cannot ask a model nicely to keep a secret. If a tool can return a phone
number, some prompt will eventually get it to return the phone number. Prompt
instructions are a style guide, not a security boundary.

```python
def get_oncall_contact(ctx, service: str) -> dict:
    if not ctx.may_see_contacts:
        raise AccessDenied(
            f"role '{ctx.role}' is not permitted to read contact details")
```

**Put the rule at the data layer, not on the obvious tool.** This is the part
most implementations get wrong. Gate `get_oncall_contact` but leave
`contact_phone` in the rows that `list_incidents` returns, and the restriction
is theatre: the caller asks for the incident instead.

One function, every path through it:

```python
RESTRICTED_FIELDS = {"contact_name", "contact_phone"}

def _redact(row, ctx):
    if ctx.may_see_contacts:
        return row
    return {k: v for k, v in row.items() if k not in RESTRICTED_FIELDS}
```

The tool you gate is not the boundary. The data is.

**Make the boundary per field.** `owning_team` is not restricted — a team name
is not personal data. `contact_phone` is. Gating whole tools is blunt enough
that people route around it.

**Return refusals as events, not as nothing.** `AccessDenied` reaches the
agent as a denial it can report. A denied call that silently returned an empty
result would have the agent confidently stating there is no on-call contact,
which is worse than an error.

**Per-user is not the same as per-agent.** A fixed tool allow-list answers
"what may this agent ever do". It does not answer "what may this person see
right now". Both are useful. Neither substitutes for the other, and most
agent frameworks give you only the first.

---

## 4. Monitoring tells you the service is up. It does not tell you what the agent did.

For a deterministic service those are close enough. For an agent they are not:
it can be entirely healthy and still have reached its answer through the wrong
tools, on the wrong data, for the wrong user.

Every tool call records who asked, which tool, with what arguments, how long
it took, what came back, and whether it was refused:

```
#   TOOL                 USER           OUTCOME        MS  ARGUMENTS
------------------------------------------------------------------
1   search_postmortems   ext.contractor ok          155.3  query='payments latency spike slow response time'
    └─ 5 chunk(s) from 3 postmortem(s)
2   list_incidents       ext.contractor ok            0.4  service='payments'
    └─ 48 incident(s)
3   get_oncall_contact   ext.contractor denied        0.0  service='payments'
    └─ role 'contractor' is not permitted to read contact details
------------------------------------------------------------------
3 tool call(s), 155.6 ms total in tools
```

Three things this buys you that an answer alone does not: you can tell a
wrong answer from a wrong *question*, you can audit an attempted access that
was refused, and you can see when the agent was working from a partial view
of the data.

Capture it at the tool boundary. It is the only place where who-asked,
what-was-asked-for and what-came-back all exist at once.

---

## What it deliberately doesn't do

Every tool you add is another thing the agent can get wrong and another thing
you have to secure. The useful question is not "what else could it do" but
"what is the smallest set of tools that answers the questions people actually
ask".

**No write tools.** No restarting services, updating tickets, or paging
anyone. Read-only end to end.

**No memory between questions.** Each starts clean. For a single question
during an incident that is the right trade — no stale context carried from a
conversation an hour ago. A multi-turn troubleshooting session would need this
to change, and that change is not free.

**No multi-agent anything.** One agent, five tools. These questions do not
need delegation, and a second agent adds failure modes without adding
capability.

**No framework.** LangGraph and similar give you checkpointing,
human-in-the-loop interrupts, branching state, multi-agent handoff. A
single-turn read-only question answerer needs none of it, and the abstraction
would sit between a reader and the thing they are trying to understand. If
this needed durable state across turns or a human approval step, that
calculus changes.

---

## When not to build this

The honest version, because an agent is not automatically an upgrade.

**If you know the question in advance, build a dashboard.** It is cheaper,
faster, deterministic, and it will not hallucinate. Agents earn their place
when the question is unpredictable, not when the data is interesting.

**If your question only touches one source, use that source.** A SQL query or
full-text search beats an agent on latency, cost and reliability. The value
here is crossing the boundary, not the model.

**If a wrong answer is expensive and unverifiable, be careful.** Grounding and
citation reduce this, they do not remove it. Here, every claim carries an
incident ID a reader can check — if your domain has no equivalent of that,
that is a problem to solve before you ship.

**If your data has no access boundaries, you have less to design and more
freedom.** Half the engineering in this repo exists because some fields are
restricted.

Costs, concretely: a few hundred milliseconds to several seconds per question,
a model call per tool round trip, and a non-deterministic execution path that
makes testing harder than testing a query.

---

## What broke

Three real bugs, all found by reading traces rather than by reading answers.

**1. The model did not know what "last quarter" meant.** It returned zero
Sev-1s, confidently. The trace showed why:

```
1   incident_stats   ok   severity='Sev-1', since='2024-10-01', until='2024-12-31'
    └─ n=0, median=Nonemin
```

It resolved a relative date against a year two years off, because nothing told
it what today was. Tool correct, query wrong, answer confidently useless.
Fixed by putting the current date in the system prompt.

The generalisable version: models do not know the current date, and every
relative time expression your users type is an unstated assumption. This was
invisible in the answer and obvious in the trace.

**2. The model chose a bad `limit` and silently saw a partial view.**
`list_incidents` returned 20 rows by date, so the Sev-1 at the centre of the
pattern fell outside the window. The answer was coherent and incomplete, which
is worse than an obvious error. Fix described in the tool-descriptions section
above — the number was coming from the description, not the Python default.

**3. Retrieval returns a subset and nothing says so.** Search consistently
returns chunks from about three of the five relevant postmortems. Nothing in
the result tells the agent it is holding part of the picture. The structured
query compensates here, but that is a property of this design rather than a
solved problem.

**Planning is not deterministic.** The same question run twice produces a
different tool order and occasionally different arguments. Not a bug, but it
means the trace is how you know what happened rather than what you assumed.

---

## What I'd change

**Return totals alongside results.** `list_incidents` should say "20 of 48
matching" so the agent knows it is holding a slice. Most of bug 2 is really
this.

**Push aggregates harder in the descriptions.** The agent occasionally counts
rows itself rather than calling `incident_stats`. The arithmetic is right, but
arithmetic from a language model is a weaker guarantee than arithmetic from
SQL.

**Make the role an identity lookup, not a string.** In a real deployment the
role comes from the identity provider, and the same group membership that
governs every other system governs this one. An agent should not have a
parallel permission model.

**Add retrieval evaluation.** There is inspection here, not measurement. A set
of questions with known-correct incident IDs would turn "retrieval seems to
work" into a number that can regress.

**Persist traces with a correlation id.** One in-process list is fine for a
CLI. Anything real needs traces that outlive the process.

---

## Running it

Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # add your ANTHROPIC_API_KEY

python generate_data.py       # builds data/incidents.db (200 incidents)
python src/ingest.py          # embeds 14 postmortems into data/chroma
```

`ingest.py` downloads an ~80MB embedding model on first run. After that,
everything except the model API call runs locally.

```bash
# spans both sources
python src/agent.py "payments latency is spiking again, has this happened before and who do I talk to?" --trace

# aggregate
python src/agent.py "how many Sev-1 incidents did we have last quarter and what was the median time to resolve?" --trace

# same question, restricted role
python src/agent.py "payments latency is spiking again, has this happened before and who do I talk to?" \
    --user ext.contractor --role contractor --trace

# out of scope
python src/agent.py "what did the payments outages cost us in lost revenue?" --trace
```

`--role` is `engineer`, `incident_commander` or `contractor`. `--trace` prints
the tool call table. `--verbose` prints calls as they happen.

---

## The pattern, without the incidents

Nothing here is about incident response.

The shape is: knowledge split across structured records and written
documents, questions that span both, and different people who should see
different subsets. Wherever that holds, the same four pieces apply —
retrieval with ingestion-time decisions, tools for what retrieval cannot do,
authorization at the tool boundary, and a trace of what was actually called.

Claims history plus policy documents plus adjuster permissions. Patient
records plus clinical notes plus role-based access. Customer accounts plus
support transcripts plus tiered agent visibility.

Change the domain and the data. The engineering does not move.
