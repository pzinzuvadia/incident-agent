# Postmortem: auth 5xx spike traced to third-party API

- **Incident:** INC-0066
- **Service:** auth
- **Severity:** Sev-1
- **Date:** 2026-01-16
- **Duration:** 1h 49m
- **Owning team:** Identity
- **Author:** Priya Raghunathan

## Summary

Login failures for roughly 35% of users between 13:41 and 15:30. Traced to the
external identity provider returning 503s intermittently. Their status page
reported all systems operational for the duration of the incident.

## Timeline

- **13:41** — Error rate alert on auth.
- **13:47** — Confirmed the errors are all on the federated login path.
  Password login is unaffected.
- **14:05** — Provider status page shows green. Opened a support ticket.
- **14:30** — Enabled the fallback path so federated users can fall back to
  password login with a one-time email code.
- **15:12** — Provider acknowledges a regional issue.
- **15:30** — Error rate returns to baseline.

## Root cause

Third-party identity provider degradation in one region. We had no automatic
fallback, so every failed call surfaced to the user as a failed login.

## Resolution

Manually enabled the email fallback path. Provider recovered on their side.

## Follow-ups

- [ ] Automate the fallback so it triggers on elevated provider error rate
      rather than requiring a human decision. **(not done)**
- [x] Alert on provider error rate directly, not just our own. **(done
      2026-01-20)**

## Notes

Provider status pages are not a monitoring strategy. Ours was green for the
entire incident.
