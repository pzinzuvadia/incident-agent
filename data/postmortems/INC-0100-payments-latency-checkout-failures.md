# Postmortem: Elevated payments latency and checkout failures

- **Incident:** INC-0100
- **Service:** payments
- **Severity:** Sev-1
- **Date:** 2026-03-18
- **Duration:** 1h 28m
- **Owning team:** Payments Platform
- **Author:** Dana Whitfield

## Summary

At 02:47 on 18 March, payments latency rose sharply and checkout began failing
for a majority of customers. Roughly 4,100 checkout attempts failed over the
course of the incident. This is the third occurrence of the same underlying
failure mode, after INC-0020 in November and INC-0076 in January, and the first
one to reach Sev-1.

## Timeline

- **02:47** — Latency alert fires. Error rate alert follows two minutes later
  as checkout begins timing out against payments.
- **02:51** — On-call paged and acknowledges.
- **02:58** — Checks the card processor. Processor response times are elevated,
  around 1.8 seconds against a normal 200ms. Processor status page shows
  nothing.
- **03:05** — Pool is fully saturated on all pods. Recognised as the same shape
  as the two previous incidents.
- **03:14** — Rolling restart with pool raised to 90 per pod. Partial recovery,
  then saturation again within ten minutes.
- **03:30** — Realise raising the pool is making it worse, not better, because
  every additional connection is also sitting waiting on the slow processor.
- **03:41** — Reduce the per-request timeout against the processor from 30s to
  4s, so connections are released rather than held.
- **04:02** — Latency recovers. Error rate returns to baseline.
- **04:15** — Resolved. Processor confirms a degradation on their side by email
  the following morning.

## Root cause

The upstream card processor was experiencing a partial degradation. Our
per-request timeout against them was 30 seconds, which meant every slow call
held a database connection for the entire time it waited.

Under normal processor latency this was invisible. Under degraded processor
latency, the pool drained within minutes and the whole service queued behind
it.

The trigger was external. The reason it became a Sev-1 rather than an
inconvenience was our own configuration: a pool with no headroom and a timeout
long enough to exhaust it. Both of those had been flagged as follow-ups in the
two previous incidents and neither had been done.

## Resolution

Dropped the processor timeout from 30s to 4s. Connections are now released
quickly enough that a slow dependency degrades throughput instead of stopping
it. Pool left at 90 per pod.

## Follow-ups

- [x] Reduce processor timeout to 4s. **(done during incident)**
- [x] Queue depth alert, finally. **(done 2026-03-20)**
- [x] Circuit breaker on the processor client so repeated slow calls shed load
      rather than queueing. **(done 2026-04-02)**
- [ ] Pool sizing review across the Payments Platform estate. Still open from
      November. **(not done)**

## Notes

The honest lesson is not technical. We had two earlier incidents that told us
exactly what would happen, and a follow-up list that said what to do about it,
and we did not do it because nothing was on fire. The third one happened at
2:47 in the morning during a period when the on-call engineer had no context
on the previous two, because they were on a different team when those
happened. The knowledge existed. It was not reachable by the person who needed
it.

Holding a connection while waiting on a third party is the actual anti-pattern
here. If you take one thing from this: the timeout you set on an external call
is also, implicitly, a decision about how long you are willing to hold every
resource behind it.
