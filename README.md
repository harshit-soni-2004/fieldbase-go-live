# Go-live

A local B2B implementation agent for a fictional workspace product, Fieldbase. It provisions a tenant from a signed contract. The contract is the source of truth. A person marks the account live.

The application is **not built yet**. This folder is the spec and the fixtures. Implementation follows `docs/08-delivery-plan.md`.

## Read this first

| Document | What it decides |
|---|---|
| [AGENTS.md](AGENTS.md) | Rules Antigravity keeps in context |
| [docs/00-context.md](docs/00-context.md) | The problem, the demo, and what "done" means |
| [docs/README.md](docs/README.md) | Full document index |
| [prompts.md](prompts.md) | Paste these into Antigravity, one at a time |
| [interview.md](interview.md) | How to explain the project in an interview |

## Fixtures

- [fixtures/northwind.json](fixtures/northwind.json) — SSO still missing
- [fixtures/contoso.json](fixtures/contoso.json) — Billing was not purchased
- [fixtures/fabrik.json](fixtures/fabrik.json) — checklist can go live
- [fixtures/scenarios.json](fixtures/scenarios.json) — user messages and idempotency keys

## Resume

Do not add Go-live to a resume until a live model run has been reviewed and the numbers in `docs/09-demo-and-resume.md` are filled from that run. The CI suite proves the scripted path, not a live model.
