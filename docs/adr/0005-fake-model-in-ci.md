# ADR 0005 — CI uses a fake model and the real API

## Status

Accepted

## Decision

`pytest` runs `FakeModel`, which returns the scripts in `docs/05-agent.md`. Those calls are executed by the admin API. Tests do not call a hosted model and do not need an API key.

`LiveModel` is a separate adapter. Its unit test uses a stub HTTP transport. A live run is a manual phase 5 step and is recorded in `docs/09-demo-and-resume.md` only if it happened.

## Why

A scripted suite is reproducible and cheap. It is also easy to over-claim. Separating the claims keeps the resume accurate: CI proves the API and the orchestration, and a named model result appears only after a person saw it.

## Consequences

The fake model must not return a finished tenant object in place of tool calls. If it did, Contoso's red row would be theater. Phase 2 is not done until the Billing `422` is produced by the API.
