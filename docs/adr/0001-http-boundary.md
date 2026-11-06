# ADR 0001 — The agent reaches state only through HTTP

## Status

Accepted

## Decision

The agent loop calls the admin API with an HTTP client and a base URL. It does not import `app.db` or `app.domain`. An architecture test enforces that import boundary.

The API and the agent still ship in one process so v1 stays one command. The boundary is the import and the HTTP call, not a second deployable.

## Why

The demo claim is that a wrong tool call is refused by the same API an operator would call. If the agent writes SQLite itself, a rejected module can be "fixed" in the model and never appear in the audit log.

A later split into two processes can keep this client unchanged.

## Consequences

Agent tests start the app and call it over HTTP, or they drive the loop against a base URL. They do not call domain functions to provision a tenant and then describe that as an agent run.
