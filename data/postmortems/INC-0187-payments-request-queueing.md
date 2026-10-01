# Postmortem: Payments request queueing during sustained traffic

- **Incident:** INC-0187
- **Service:** payments
- **Severity:** Sev-2
- **Date:** 2026-08-21
- **Duration:** 2h 22m
- **Owning team:** Payments Platform
- **Author:** Tomas Lindqvist (incident commander, Discovery; covering)

## Summary

Sustained elevated traffic from a promotional campaign drove payments into
connection pool saturation for roughly two hours. Latency rose to about 3
seconds at p99. No outright failures thanks to the circuit breaker added after
INC-0100, but checkout was visibly slow throughout.

## Timeline

- **11:09** — Queue depth alert fires across all pods roughly simultaneously.
- **11:14** — On-call confirms traffic is approximately 3.2x normal for the
  time of day. Marketing campaign launched at 11:00 and was not communicated
  to the platform teams.
- **11:25** — Pool saturated. Circuit breaker is shedding a small amount of
  load, which is keeping error rate near zero but adding latency.
- **11:40** — Scale payments pods from 12 to 24.
- **12:05** — Latency improves but stays above baseline. Database connection
  count is now approaching the server-side maximum, so further pod scaling
  would have started failing connections.
- **12:30** — Add a read replica for the transaction history queries to take
  read load off the primary.
- **13:20** — Latency returns to normal.
- **13:31** — Resolved.

## Root cause

Traffic from an unannounced promotional campaign exceeded what the current
pool and pod configuration could absorb. Nothing was misconfigured. The system
behaved exactly as designed for a load level nobody told us was coming.

The secondary finding is more interesting: scaling pods horizontally multiplies
total connections against a fixed server-side connection limit. We were about
four pods away from hitting a wall where scaling out would have made things
worse rather than better. Nobody had calculated that ceiling before.

## Resolution

Scaled to 24 pods and added a read replica for history queries.

## Follow-ups

- [x] Document the maximum safe pod count given the database connection
      ceiling. It is 31. **(done 2026-08-25)**
- [ ] Get platform teams onto the campaign calendar so load events are known
      in advance. **(in progress, owner Payments Platform)**
- [ ] Evaluate a connection proxy so pod count and database connection count
      stop being coupled. **(not done)**

## Notes

Fifth pool-related incident on this service in ten months. Each one had a
different proximate cause: undersized pool, slow query, slow dependency,
driver default, traffic spike. The common factor is that this service's
capacity is bounded by connections in a way that is invisible until it is
saturated, and every fix so far has raised the ceiling rather than removed the
coupling.

The connection proxy is the thing that would actually change the pattern. It
has been discussed after three of the five incidents and has never been
prioritised.
