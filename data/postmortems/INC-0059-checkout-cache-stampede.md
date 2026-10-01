# Postmortem: checkout origin overload after cache eviction

- **Incident:** INC-0059
- **Service:** checkout
- **Severity:** Sev-1
- **Date:** 2026-01-09
- **Duration:** 1h 24m
- **Owning team:** Storefront
- **Author:** Marcus Reyes

## Summary

A cache node was replaced during routine maintenance. Every key it held expired
at once, and the resulting simultaneous cache misses overwhelmed the origin
service for about an hour and a half.

## Timeline

- **12:54** — Maintenance replaces cache node 3. Alerts fire within ninety
  seconds.
- **13:02** — Origin service CPU at 100%, request queue growing.
- **13:20** — Attempted to scale origin. Scaling helped marginally; the
  fundamental problem is every request missing simultaneously.
- **13:45** — Enabled request coalescing so concurrent identical misses share
  one origin call.
- **14:18** — Cache warm, traffic normal, resolved.

## Root cause

No jitter on cache expiry and no request coalescing. When a node is replaced,
its entire keyspace misses at the same instant and every miss becomes an
independent origin call.

## Resolution

Request coalescing enabled. Expiry jitter added the following week.

## Follow-ups

- [x] Add jitter to cache TTLs. **(done 2026-01-16)**
- [x] Keep request coalescing permanently enabled. **(done)**
- [ ] Warm the cache before taking a node out of rotation during maintenance.
      **(not done)**
