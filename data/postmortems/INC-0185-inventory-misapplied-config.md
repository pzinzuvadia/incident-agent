# Postmortem: Misapplied configuration affecting inventory

- **Incident:** INC-0185
- **Service:** inventory
- **Severity:** Sev-1
- **Date:** 2026-08-19
- **Duration:** 56m
- **Owning team:** Supply Systems
- **Author:** Aisha Bello

## Summary

Staging configuration was applied to production during an automated deployment
at 01:14, pointing inventory at the staging database. Stock levels displayed
incorrectly for approximately an hour overnight.

## Timeline

- **01:14** — Deployment completes. No alerts, because the service is healthy;
  it is simply reading the wrong data.
- **01:38** — Automated stock reconciliation job flags a large discrepancy.
- **01:47** — On-call paged by the reconciliation alert.
- **01:58** — Configuration error identified from the deployment diff.
- **02:10** — Rolled back to the previous configuration.

## Root cause

The deployment pipeline selects a config file by environment name. A rename in
the config repository left the production file matching the staging pattern
first. Nothing in the pipeline validates that the config it loaded is the one
it intended.

## Resolution

Rolled back. Added an assertion in the pipeline that the loaded config
declares the environment it was deployed to.

## Follow-ups

- [x] Config files declare their own environment and the pipeline verifies it.
      **(done 2026-08-21)**
- [ ] Block automated production deployments between 00:00 and 06:00 unless
      explicitly overridden. **(under discussion)**

## Notes

No health check would have caught this. The service was working perfectly. It
was answering correctly from the wrong database. The only thing that found it
was a data-level reconciliation job, which we nearly decommissioned last year
as redundant.
