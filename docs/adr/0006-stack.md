# ADR 0006 — Stack

## Status

Accepted

## Decision

- Python 3.12
- FastAPI for the admin API, demo routes, and static page
- SQLite for the database file
- One HTML page, no frontend build
- pytest
- Live model access through an OpenAI-compatible `POST /v1/chat/completions` client, configured only by `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`

Dependencies stay in one manifest (`requirements.txt` or `pyproject.toml`, chosen in phase 1 and then kept). Pin direct dependencies.

## Why

v1 is one local demo with a strict HTTP boundary inside the process. A second language would add a second runtime without changing the design. The live adapter uses a common HTTP shape so a Gemini, OpenAI, or other compatible gateway can be pointed at later without a code change.

SQLite is enough for one local database and for per-test databases. There is no migration framework requirement beyond creating the schema on startup with `CREATE TABLE IF NOT EXISTS`. If a later phase needs to change a table, delete the local `go-live.db` and start again. Tests already use their own databases.

## Consequences

This repo does not add Java, Angular, Redis, or a vector database. Those are separate projects. Do not introduce them in v1.
