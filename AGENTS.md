# Go-live

You are building **Go-live**, a local demo of a B2B implementation agent. A signed contract is the source of truth. The agent provisions a tenant only by calling the admin HTTP API. A person marks the account live.

The application is not built yet. The spec is this file plus `docs/`. When asked to implement, follow `docs/08-delivery-plan.md` one phase at a time. Do not start a later phase because an earlier one is "almost" done.

## Product in one paragraph

Fieldbase is a fictional B2B workspace product with three modules: Projects, Time, and Billing. After a customer signs, an implementation agent must create the tenant in the contracted region, enable only the purchased modules, invite only the named admins, and open a task when SSO is required and metadata has not arrived. The agent cannot send email, delete a tenant, record SSO metadata, or mark the account live.

## Non-negotiables

- The agent process reaches tenant state only through the admin HTTP API. It does not import the database layer, open SQLite, or write a tenant row.
- The stored contract wins over the model and over the user message. A message that says "also turn on Billing" does not put Billing on the contract.
- `enable_module` for a module that is not on the contract returns `422 MODULE_NOT_PURCHASED`. The other steps of that run still proceed.
- Emails that are not on the contract return `422 EMAIL_NOT_ON_CONTRACT`.
- Contract intake rejects `admins.length > seats` with `422 CONTRACT_SEAT_CONFLICT`. `SEAT_CAP` remains a backstop inside invite.
- Creating a tenant, enabling a module, inviting an email, and creating a task are idempotent. A retry returns the original row and sets `Idempotent-Replayed: true`. It does not create a second tenant, module, invite, or task.
- Same idempotency key with a different `contractId` returns `409 IDEMPOTENCY_KEY_REUSED`.
- Only the operator role can call `sso-metadata` and `go-live`. The agent role receives `403 AGENT_FORBIDDEN`.
- `go-live` stays refused while the checklist is incomplete (`409 CHECKLIST_INCOMPLETE`) or SSO is required and metadata is absent (`409 SSO_NOT_READY`).
- Status is derived. Nothing in the agent tool list writes `live`.
- CI runs the scripted fake model against the real API. CI does not call a live model and does not need an API key.
- Do not invent a measured model pass rate, a token price, or a claim that a live model was evaluated.
- v1 is local. No OAuth, CRM, real IdP, SAML parser, email delivery, Docker requirement, second service, or cloud deploy.
- Seed people use `@*.example` addresses only.

## Canonical fixtures

| Scenario | Contract | What must be true after the scripted run |
|---|---|---|
| `northwind` | `fixtures/northwind.json` | Region `ap-south-1`, modules `projects` and `time`, both admins invited, open task `collect_sso_metadata`, status `waiting_on_customer`, not live |
| `contoso` | `fixtures/contoso.json` | Region `us-east-1`, module `projects` only, Billing absent, one admin invited, no SSO task, status `ready_for_review`. The scripted model also calls Billing and receives `MODULE_NOT_PURCHASED` |
| `fabrik` | `fixtures/fabrik.json` | Region `eu-west-1`, modules `projects` and `time`, one admin invited, status `ready_for_review`. Operator can then mark live |
| `northwind_retry` | same as Northwind, same idempotency key `provision-northwind-001` | Same tenant id, same two invites, one SSO task. Replay headers on the retried writes |

User messages and keys are in `fixtures/scenarios.json`.

## Stack

Python 3.12, FastAPI, SQLite, one static page, pytest. Locked in `docs/adr/0006-stack.md`.

## Before writing code

Read, in order: `docs/00-context.md`, `docs/01-product.md`, `docs/02-architecture.md`, `docs/03-data-model.md`, `docs/04-admin-api.md`, `docs/05-agent.md`, `docs/06-ui.md`, `docs/07-test-plan.md`, `docs/08-delivery-plan.md`.

Implement only the phase the user names. The prompts to paste are in `prompts.md`, one at a time.

## Done for a phase

The exit tests named in that phase of `docs/08-delivery-plan.md` exist and pass with no network. Do not weaken a test to make it pass. Do not add a tool, endpoint, module, or status that the admin API doc does not list.
