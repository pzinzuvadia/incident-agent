# Postmortem: Slow payments responses during morning peak

- **Incident:** INC-0020
- **Service:** payments
- **Severity:** Sev-3
- **Date:** 2025-11-14
- **Duration:** 2h 36m
- **Owning team:** Payments Platform
- **Author:** Dana Whitfield

## Summary

Between roughly 09:20 and 12:00 on 14 November, the payments service returned
noticeably slower responses than usual. p95 went from about 180ms to a little
over 2 seconds. No requests failed outright, so no alerts fired on error rate.
We found out because a support engineer noticed checkout complaints piling up
and asked in the channel whether anything was going on.

## Timeline

- **09:22** — First slow responses visible in the latency dashboard. No alert.
- **09:50** — Support flags customer complaints about slow checkout.
- **10:05** — On-call begins investigating. Downstream card processor is healthy.
  Database CPU is normal. Nothing obviously wrong.
- **10:40** — We notice request queue depth on the payments pods is climbing
  steadily while CPU stays flat. Requests are waiting for something, not
  working hard.
- **11:15** — Thread dump shows most worker threads blocked waiting to acquire
  a database connection.
- **11:30** — Pool size raised from 20 to 40 per pod and the pods restarted.
- **11:58** — Latency back to normal. Monitoring for an hour, then resolved.

## Root cause

The database connection pool was sized for traffic levels from about eighteen
months ago. Morning peak volume has grown roughly 60% since then and we never
revisited the setting. Once every connection in the pool was checked out,
incoming requests queued waiting for one to be released. That wait shows up as
latency, not as errors, which is why nothing alerted.

Worth being clear: the database was fine the whole time. This was a client-side
resource limit, not a database problem. That distinction cost us about forty
minutes because we kept looking at the database.

## Resolution

Raised the pool size from 20 to 40 per pod and restarted. Latency recovered
immediately.

## Follow-ups

- [ ] Add an alert on request queue depth, not just error rate and latency. A
      saturation signal would have caught this an hour earlier. **(not done)**
- [ ] Export pool utilisation as a metric so we can see how close to the limit
      we are running on a normal day. **(not done)**
- [ ] Review pool sizing against current traffic for all services in the
      Payments Platform estate, not just this one. **(not done)**

## Notes

Raising the pool size is a band-aid. It buys headroom until traffic grows into
it again. The real question is whether the pool should be sized dynamically or
whether we should be holding connections for as long as we do. Filed as a tech
debt item; nobody is working on it yet.
