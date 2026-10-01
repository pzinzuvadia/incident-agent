# Postmortem: checkout failures following configuration rollout

- **Incident:** INC-0168
- **Service:** checkout
- **Severity:** Sev-1
- **Date:** 2026-07-26
- **Duration:** 1h 30m
- **Owning team:** Storefront
- **Author:** Marcus Reyes

## Summary

A feature flag rollout intended for 5% of traffic was applied to 100% due to a
configuration error. The new code path had a bug that failed checkout for
customers with saved addresses in certain formats.

## Timeline

- **16:14** — Flag rolled out. Error rate begins climbing within two minutes.
- **16:22** — On-call paged.
- **16:31** — Correlated with the flag change in the audit log.
- **16:38** — Flag disabled. Error rate drops immediately.
- **17:44** — Root cause on the underlying bug confirmed, incident closed.

## Root cause

Two failures. The percentage field in the rollout config was set in the wrong
unit, so 5 was interpreted as 5 out of 5 rather than 5%. And the code path
behind the flag had not been tested against addresses with non-ASCII
characters in the postcode field.

## Resolution

Flag disabled. Bug fixed and re-rolled the following week at an actual 5%.

## Follow-ups

- [x] Validate rollout percentage at config load time. **(done 2026-07-28)**
- [x] Alert on any flag change that affects more than 25% of traffic. **(done
      2026-07-30)**

## Notes

Time to detection was two minutes and time to mitigation was twenty-four,
which is the fastest we have handled a Sev-1. The audit log correlation is
what made that possible.
