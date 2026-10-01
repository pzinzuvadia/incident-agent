# Postmortem: Gradual memory growth in media-upload workers

- **Incident:** INC-0174
- **Service:** media-upload
- **Severity:** Sev-1
- **Date:** 2026-08-03
- **Duration:** 3h 27m
- **Owning team:** Content Infrastructure
- **Author:** Jonah Krantz

## Summary

Upload workers accumulated memory until the orchestrator began killing them,
causing upload failures for roughly three and a half hours.

## Timeline

- **17:30** — Restart alerts on upload workers.
- **17:52** — Restarts confirmed as OOM kills.
- **18:40** — Growth correlates with large file uploads specifically, not
  request volume.
- **19:50** — Found that image transform buffers were being retained after the
  transform completed when the upload was later aborted by the client.
- **20:30** — Patch deployed releasing buffers in the abort path.
- **20:57** — Resolved.

## Root cause

The abort path did not release transform buffers. Clients aborting large
uploads, which is common on mobile connections, left multi-hundred-megabyte
buffers held until the worker was killed.

## Resolution

Buffers released explicitly in the abort handler.

## Follow-ups

- [x] Release buffers on abort. **(done during incident)**
- [ ] Add a memory-per-request metric so retention is visible before it
      becomes a kill. **(not done)**

## Notes

Similar shape to the search memory incident in December, in that the growth
was invisible until something removed the thing that had been masking it. In
that case it was frequent deploys. Here it was that mobile abort rates went up
after an app release.
