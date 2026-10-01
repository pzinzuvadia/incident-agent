# Postmortem: Payments p99 latency degradation under load

- **Incident:** INC-0076
- **Service:** payments
- **Severity:** Sev-2
- **Date:** 2026-01-29
- **Duration:** 3h 23m
- **Owning team:** Payments Platform
- **Author:** Marcus Reyes (covering on-call for Payments Platform)

## Summary

Payments p99 latency degraded sharply during the afternoon of 29 January,
peaking around 6 seconds against a normal baseline of under 400ms. A small
number of client requests timed out on the caller side. This is the same
failure mode as INC-0020 in November.

## Timeline

- **14:05** — Latency alert fires (we added a p99 threshold after November).
- **14:12** — On-call acknowledges. Checks the card processor, which is healthy.
- **14:20** — Checks pool saturation directly, because of the November
  incident. Pool is fully checked out on every pod.
- **14:35** — Raise pool size from 40 to 60 per pod, rolling restart.
- **15:10** — Latency improves but does not fully recover. Still elevated.
- **16:00** — Discover a slow query on the transaction history table added in
  a release two weeks ago. It holds connections roughly four times longer than
  the queries around it.
- **17:05** — Query fixed with an index. Latency returns to baseline.
- **17:28** — Resolved.

## Root cause

Two causes stacked. The pool was again running close to its limit at peak,
which we knew about and had not addressed. On top of that, a new query
introduced in the 15 January release held connections far longer than
necessary because it was doing a full scan on a table that had grown past the
point where that was acceptable.

The pool was the amplifier, not the cause. A slow query on its own would have
been survivable. A tight pool on its own would have been survivable. Together
they took the service down to a crawl.

## Resolution

Pool raised to 60 per pod. Index added to the transaction history table, which
brought the offending query from about 900ms down to 12ms.

## Follow-ups

- [ ] The queue depth alert from INC-0020 still has not been built. It would
      have caught this before the latency alert. **(not done)**
- [x] Add pool utilisation to the payments dashboard. **(done 2026-02-04)**
- [ ] Add a check in CI that flags queries without an index on the filtered
      column. **(not done)**

## Notes

This is the second time in three months. We keep raising the pool ceiling and
calling it fixed. The pattern is that we only find out when it is already
hurting customers, because we are alerting on symptoms rather than on
saturation. The queue depth alert has now been on the follow-up list twice.
