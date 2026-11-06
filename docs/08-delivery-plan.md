# 08 — Delivery plan

Build in order. Each phase ends with its tests passing. Do not open a pull request or deploy anywhere as part of this plan. Do not add a phase that is not listed here.

The repo already contains `AGENTS.md`, `docs/`, and `fixtures/`. Later phases add `app/`, `static/`, and `tests/`.

## Phase 1 — Admin API

**Build:** SQLite schema from `03-data-model.md`, contract and tenant routes from `04-admin-api.md`, derived checklist and status, local bearer auth, audit rows on each call.

**Do not build:** the agent loop, the page, or a live model client.

**Exit:** every test in the "Contract intake" and "Tenant rules" sections of `07-test-plan.md` passes. `GET /api/v1/contracts/ctr_northwind` after loading the fixture matches the file.

## Phase 2 — Scripted agent

**Build:** tool loop, fake scripts from `05-agent.md`, HTTP tool client, `POST /api/demo/run` for `mode: fake`, run and step rows.

**Exit:** the "Scripted agent" tests pass, including the import boundary test. Contoso's Billing step is a real `422` from the API, not a stubbed result inside the fake model.

## Phase 3 — Checklist page

**Build:** `static/index.html` and the operator demo routes from `06-ui.md`.

**Exit:** the "Page" tests pass. A person can run Northwind, Contoso, Fabrik, and Retry Northwind in fake mode and mark Fabrik live. Northwind's Mark live stays disabled until SSO metadata is recorded.

## Phase 4 — Live adapter and README run notes

**Build:** `LiveModel` against an OpenAI-compatible URL, missing-env behavior, token usage stored only when the provider returns it.

**Write into the root README**, replacing the "not built yet" sentence with:

- the command that runs the tests
- the command that serves the app locally
- Fake is the default
- the three env vars for live mode
- a line `Live result: not run yet.`

**Exit:** the "Live adapter, no network" tests pass. The README still has `Live result: not run yet.`

## Phase 5 — Demo record

This phase is a person, not an agent.

1. Run the four fake scenarios and confirm they match `00-context.md`.
2. Optionally run one live scenario with a key in the environment, not in the repo.
3. If the live run is kept, write what happened under the headings in `09-demo-and-resume.md`: tools called, whether Billing stayed off, whether the model claimed the account was live, token totals if reported.
4. Only then fill a resume bullet from the template in that doc.

If the live model enables Billing and the API rejects it, that is a successful demo of the API. If the live model claims the account is live, write that down. Do not hide it.

## Risks to watch while building

| Risk | What to do |
|---|---|
| The fake model returns a canned tenant instead of calling the API | Reject the phase. Contoso's rejection has to come from the API |
| Status is stored and updated by the agent | Reject the phase. Status stays derived |
| The page holds `agent-local` | Reject the phase. Tokens stay on the server |
| Tests call a public model | Reject the phase |
| A second copy of the contracts is typed into Python | Load `fixtures/*.json` |

## Suggested package tasks

Phase 1 can be one implementation session. Phase 2 a second. Phase 3 a third. Phase 4 is small once the loop exists. Stopping after phase 3 is a complete local demo. Phase 4 is what makes a live run possible. Phase 5 is what makes the resume line true.
