# Postmortem: Slow inventory responses with healthy dependencies

- **Incident:** INC-0117
- **Service:** inventory
- **Severity:** Sev-1
- **Date:** 2026-04-27
- **Duration:** 42m
- **Owning team:** Supply Systems
- **Author:** Aisha Bello

## Summary

Inventory lookups slowed to the point of timing out for about forty minutes on
the evening of 27 April. Stock levels failed to display on product pages.
Database and cache were both healthy throughout.

## Timeline

- **20:56** — Latency alert. Error rate follows shortly after as callers time
  out.
- **21:03** — On-call confirms database CPU, memory and query times are all
  normal.
- **21:11** — Pool saturation confirmed on all pods.
- **21:19** — Pool raised from 15 to 35 per pod, rolling restart.
- **21:38** — Recovered and resolved.

## Root cause

Connection pool sized at 15 per pod, which was set when the service had four
pods and far lower traffic. Evening peak now exceeds what that allows. Same
class of problem the Payments Platform team have written up several times.

## Resolution

Pool raised to 35 per pod.

## Follow-ups

- [x] Add pool utilisation to the inventory dashboard. **(done 2026-05-02)**
- [ ] Review pool sizing across all Supply Systems services. **(not done)**

## Notes

Dana from Payments Platform pointed us at their earlier writeups after the
fact, which would have saved us most of the diagnosis time if we had found
them during the incident. Nothing about this was novel; we just did not know
it had already happened to somebody else.
