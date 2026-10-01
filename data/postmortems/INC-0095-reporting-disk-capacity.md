# Postmortem: reporting write failures from disk capacity

- **Incident:** INC-0095
- **Service:** reporting
- **Severity:** Sev-2
- **Date:** 2026-02-25
- **Duration:** 9h 50m
- **Owning team:** Data Platform
- **Author:** Nadia Osei

## Summary

The reporting service ran out of disk on its primary volume and was unable to
write new report output for most of a working day. Scheduled reports failed
silently; users discovered it when reports did not arrive.

## Timeline

- **17:07** — First write failures logged. No alert configured on disk usage.
- **21:30** — Overnight batch fails entirely.
- **07:15** (next day) — Users report missing reports.
- **08:40** — On-call identifies the volume at 100%.
- **09:50** — Cleared 400GB of orphaned temporary files.
- **02:57** — Volume expanded and service recovered.

## Root cause

Temporary files from failed report generations were never cleaned up. Each
failure left behind its partial output. Over about fourteen months this
accumulated to roughly 400GB.

No alert existed on disk utilisation for this volume, so nothing surfaced
until writes began failing, and even then the failures were logged rather
than alerted.

## Resolution

Manual cleanup, volume expanded from 500GB to 1TB, and a cleanup job added for
orphaned temporary files.

## Follow-ups

- [x] Disk utilisation alert at 75% and 90%. **(done 2026-02-26)**
- [x] Cleanup job for orphaned temp files. **(done 2026-03-04)**
- [ ] Audit every service for volumes without a utilisation alert. **(not
      done)**

## Notes

Nearly ten hours to resolve, and most of that was time before anybody knew.
The failure was logged from the first minute. We were writing the evidence to
a file nobody reads.
