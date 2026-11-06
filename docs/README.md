# Go-live documents

Read in this order when implementing or reviewing.

| Order | Document | Purpose |
|---|---|---|
| 0 | [00-context.md](00-context.md) | Why this exists, the four scenarios, and the boundary between model and API |
| 1 | [01-product.md](01-product.md) | Users, checklist, statuses, and v1 scope |
| 2 | [02-architecture.md](02-architecture.md) | Components, trust boundary, and request flow |
| 3 | [03-data-model.md](03-data-model.md) | SQLite tables and derived status |
| 4 | [04-admin-api.md](04-admin-api.md) | Every route, error code, and idempotent replay |
| 5 | [05-agent.md](05-agent.md) | Tools, fake-model scripts, live system prompt, step limit |
| 6 | [06-ui.md](06-ui.md) | Checklist page and operator controls |
| 7 | [07-test-plan.md](07-test-plan.md) | Test names and assertions |
| 8 | [08-delivery-plan.md](08-delivery-plan.md) | Build phases and exit criteria |
| 9 | [09-demo-and-resume.md](09-demo-and-resume.md) | Demo script and what the resume may say |
| 10 | [../prompts.md](../prompts.md) | Pasteable Antigravity prompts, one at a time |
| 11 | [../interview.md](../interview.md) | In-depth interview explanation |

## Decision records

| ADR | Decision |
|---|---|
| [0001](adr/0001-http-boundary.md) | The agent talks to the admin API over HTTP |
| [0002](adr/0002-contract-wins.md) | The stored contract beats the chat message |
| [0003](adr/0003-human-go-live.md) | Operator-only SSO metadata and go-live |
| [0004](adr/0004-idempotency.md) | Retries return the original row |
| [0005](adr/0005-fake-model-in-ci.md) | CI uses a scripted model and the real API |
| [0006](adr/0006-stack.md) | Python, FastAPI, SQLite, one static page |

## Fixtures

Canonical JSON lives in [`../fixtures`](../fixtures). Docs describe those files. Implementation loads them. Do not fork a second copy of the contract fields inside prose if the JSON can be referenced.
