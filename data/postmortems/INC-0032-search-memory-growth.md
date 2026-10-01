# Postmortem: Gradual memory growth in search workers

- **Incident:** INC-0032
- **Service:** search
- **Severity:** Sev-1
- **Date:** 2025-12-07
- **Duration:** 2h 54m
- **Owning team:** Discovery
- **Author:** Tomas Lindqvist

## Summary

Search workers were restarted repeatedly by the orchestrator after exceeding
memory limits, causing intermittent search failures over roughly three hours.

## Timeline

- **16:59** — Pod restart alerts. Search error rate climbing.
- **17:15** — Confirmed the restarts are memory limit kills, not crashes.
- **17:40** — Memory growth is linear with uptime, roughly 400MB per hour per
  worker, independent of query volume.
- **18:30** — Heap analysis points at a query result cache with no eviction
  policy.
- **19:15** — Deployed with an LRU bound on the cache.
- **19:53** — Memory flat. Resolved.

## Root cause

A result cache added three months earlier had no size limit and no eviction.
It grew until the pod hit its memory ceiling. Growth was slow enough that it
took weeks to become visible, and restarts during deployments kept resetting
it, which is why it only surfaced during an unusually long period without a
release.

## Resolution

LRU eviction with a hard size bound.

## Follow-ups

- [x] Bound the result cache. **(done during incident)**
- [ ] Add a memory growth trend alert rather than only alerting on the limit
      being hit. **(not done)**

## Notes

Deployments were hiding this. Every release restarted the pods and reset the
memory. It only became an incident because we had a two-week freeze over the
holidays.
