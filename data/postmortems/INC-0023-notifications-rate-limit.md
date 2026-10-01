# Postmortem: notifications clients receiving 429 responses

- **Incident:** INC-0023
- **Service:** notifications
- **Severity:** Sev-2
- **Date:** 2025-11-21
- **Duration:** 5h 11m
- **Owning team:** Messaging
- **Author:** Ellis Farrow

## Summary

A retry storm from a misbehaving client drove notification API traffic past
the rate limiter, which then rejected legitimate traffic from other clients.
Notifications were delayed or dropped for about five hours overnight.

## Timeline

- **03:21** — Rate limit rejection alert.
- **03:35** — On-call identifies a single client account responsible for about
  85% of requests.
- **04:10** — That client is retrying failed requests immediately with no
  backoff, so every failure generates more load.
- **05:00** — Applied a per-client limit to isolate them.
- **07:40** — Contacted the client team. Retry logic fixed on their side.
- **08:32** — Resolved.

## Root cause

The rate limiter was global rather than per-client, so one client could consume
the entire budget. That client's retry logic had no backoff and no cap, which
turned a transient failure into a sustained load event.

## Resolution

Per-client rate limits introduced.

## Follow-ups

- [x] Per-client rate limiting. **(done during incident)**
- [x] Alert when one client exceeds 40% of total request volume. **(done
      2025-11-24)**
- [ ] Publish retry guidance in the notifications API docs, including required
      backoff. **(not done)**

## Notes

A global rate limit protects your service from total load but does nothing to
protect your clients from each other. Worth remembering when the shared
resource is the thing being defended.
