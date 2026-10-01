# Postmortem: Intermittent payments timeouts with healthy dependencies

- **Incident:** INC-0144
- **Service:** payments
- **Severity:** Sev-2
- **Date:** 2026-06-03
- **Duration:** 2h 54m
- **Owning team:** Payments Platform
- **Author:** Dana Whitfield

## Summary

Intermittent timeouts on payments between 16:31 and 19:25 on 3 June. Roughly
2% of requests affected, concentrated on two of the twelve pods. All
dependencies healthy throughout, which made this harder to diagnose than the
previous occurrences.

## Timeline

- **16:31** — Queue depth alert fires on two pods. This is the alert added
  after INC-0100, and it worked.
- **16:38** — On-call confirms the card processor and the database are both
  healthy. No slow queries.
- **16:55** — Confirms pool saturation, but only on the two affected pods. The
  other ten are at normal utilisation.
- **17:20** — Traffic is evenly distributed, so uneven saturation does not make
  sense. Spend some time chasing a load balancer theory, which is wrong.
- **18:10** — Notice the two affected pods were started from a different image
  tag after a partial rollout on 28 May.
- **18:40** — The newer image includes a database driver upgrade. The upgrade
  changed the default idle connection timeout from 60s to 600s, so connections
  were being held far longer before being returned to the pool.
- **19:05** — Roll the two pods back to the previous image.
- **19:25** — Resolved.

## Root cause

A minor version bump of the database driver, picked up in a partial rollout,
changed a default we were relying on implicitly. We never set the idle timeout
explicitly in configuration, so we inherited whatever the driver shipped with.
When that default changed from 60 seconds to 600, idle connections stopped
being recycled and the effective pool size shrank over time.

The uneven impact was the diagnostic clue and also the thing that slowed us
down, because we assumed uneven symptoms meant uneven traffic.

## Resolution

Rolled back the two pods. Then set the idle timeout explicitly in
configuration and rolled the new driver forward everywhere on 5 June.

## Follow-ups

- [x] Set idle connection timeout explicitly rather than relying on the driver
      default. **(done 2026-06-05)**
- [x] Audit other pool settings we are inheriting implicitly. Found three.
      **(done 2026-06-11)**
- [ ] Add image tag to the pod-level dashboard so a partial rollout is visible
      at a glance. **(not done)**

## Notes

Fourth time this service has had a pool-related incident. The pool itself is
sized correctly now. What keeps getting us is the things around it: how long
connections are held, when they are released, what happens when something
downstream is slow. The pool is just where the symptom shows up.

Also worth saying: the queue depth alert did its job here. We knew within
minutes instead of finding out from support.
