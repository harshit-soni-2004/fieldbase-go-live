# Prompts for Antigravity

Open this `go-live` folder as the Antigravity workspace before the first prompt, so `AGENTS.md` is loaded.

Start a **new agent conversation** for each prompt. Paste only the fenced block. Wait until that prompt's `pytest` run is green before the next one. If it is not green, paste [When a phase fails](#when-a-phase-fails) into the same conversation with the failure output. Do not start the next prompt on a red suite.

There are six build prompts. Prompt 6 does not call a live model.

---

## Prompt 1 — Contracts and the database

```text
You are implementing Go-live, phase 1 of 2 of the admin API. The spec is already in this repo. Do not invent a different product.

Read these files before you write code, and follow them when they are more specific than this prompt:
- AGENTS.md
- docs/01-product.md
- docs/03-data-model.md
- docs/04-admin-api.md (contracts, auth, problem body, error codes)
- docs/adr/0006-stack.md
- The "Contract intake" section of docs/07-test-plan.md

Build only the skeleton, the database, contract intake, and the contract tests.

Create:
- requirements.txt with pinned fastapi, uvicorn, and pytest
- .gitignore for .env, .venv, go-live.db, __pycache__, .pytest_cache, .venv
- app/main.py that builds the FastAPI app and creates the schema on startup
- app/db.py as the only SQLite writer
- app/api/problems.py for the problem JSON in docs/04-admin-api.md
- app/api/auth.py for local bearer tokens
- app/api/contracts.py
- tests/conftest.py with a fresh database per test and APP_ENV=local
- tests/test_contracts.py

Schema tables and checks are docs/03-data-model.md. Create them with CREATE TABLE IF NOT EXISTS. Public ids are text. Booleans are 0 or 1. Timestamps are ISO-8601 UTC with a Z suffix.

Auth, only when APP_ENV=local:
- AGENT_TOKEN defaults to agent-local, role agent
- OPERATOR_TOKEN defaults to operator-local, role operator
- Missing or unknown bearer returns 401
Do not add OAuth, users, or a login page.

POST /api/v1/contracts and GET /api/v1/contracts/{contractId} behave as docs/04-admin-api.md. Load the three files in fixtures/ by path in tests. Do not retype those contracts as Python literals.

Rules that tests will enforce:
- Unknown module id returns 422 UNKNOWN_MODULE and nothing is stored
- Unknown region returns 422 UNKNOWN_REGION
- More admins than seats returns 422 CONTRACT_SEAT_CONFLICT
- Unknown JSON fields return 422 VALIDATION_ERROR
- A second identical POST returns 200 and the header Idempotent-Replayed: true
- The same contractId with different JSON returns 409 IDEMPOTENCY_KEY_REUSED
- GET returns modules in catalog order projects, time, billing, and admins sorted by email

Write every test named in the Contract intake section of docs/07-test-plan.md. Run pytest. Fix failures. Do not delete or weaken a test to make it pass.

Do not build tenant routes, the agent, a model client, or the HTML page. When pytest is green, stop. In your final message, list the test names that passed and say that tenant routes are not started.
```

---

## Prompt 2 — Tenants, checklist, and go-live

```text
Continue Go-live. Contract intake from the previous phase is done. Implement the rest of the admin API. Do not redesign the schema or the contract routes.

Read before writing:
- AGENTS.md
- docs/01-product.md
- docs/03-data-model.md
- docs/04-admin-api.md
- docs/adr/0002-contract-wins.md
- docs/adr/0003-human-go-live.md
- docs/adr/0004-idempotency.md
- The "Tenant rules" section of docs/07-test-plan.md

Build tenant routes, derived status, the checklist, operator SSO and go-live, audit rows, and tests/test_tenants.py.

Status is computed on read. Do not add a status column and do not let any caller set status. The order is in docs/03-data-model.md:
- live_at set means live
- region, modules, and admins match, and SSO is required while metadata is absent, means waiting_on_customer
- region, modules, and admins match, SSO does not block, and no task is open, means ready_for_review
- otherwise provisioning

POST /api/v1/tenants requires Idempotency-Key. The body is only {"contractId": "..."}. Copy customer name and seats from the stored contract. Leave region null. Generate ten_ plus 12 hex chars.

Same key and same contractId returns the original tenant with 200 and Idempotent-Replayed: true.
Same key and a different contractId returns 409 IDEMPOTENCY_KEY_REUSED.
A new key for a contract that already has a tenant returns 409 CONTRACT_ALREADY_PROVISIONED.
Missing key returns 400 IDEMPOTENCY_KEY_MISSING.

set_region accepts only the contract region. The first success stores it. The same region again replays. A different value after one is stored returns 409 REGION_ALREADY_SET. A region that is not the contract region returns 422 REGION_MISMATCH. A region outside the allowlist returns 422 UNKNOWN_REGION.

enable_module: unknown catalog id returns 422 UNKNOWN_MODULE. A catalog module that is not on this contract returns 422 MODULE_NOT_PURCHASED and does not insert a row. Enabling the same module again replays.

invite_admin accepts {"email": "..."} only. Lowercase the email. If it is not a contract admin, return 422 EMAIL_NOT_ON_CONTRACT. Copy the name from the contract. The same email replays. SeatPolicy: when the count of distinct invites already equals seats, another new email returns 422 SEAT_CAP. Cover that with a unit test, as docs/07-test-plan.md describes, because a legal HTTP invite of a second email is rejected earlier as EMAIL_NOT_ON_CONTRACT.

create_task accepts {"code": "collect_sso_metadata"} only. The server sets the title to "Collect SSO metadata from the customer". If SSO is not required, or metadata is already present, return 422 TASK_NOT_APPLICABLE. A second create replays the open task.

GET /api/v1/tenants/{tenantId} returns the checklist object from docs/04-admin-api.md. sso.state is not_applicable, blocking, or ready.

Operator routes, bearer role operator:
- POST /api/v1/tenants/{tenantId}/sso-metadata with body {} sets sso_metadata_present and marks collect_sso_metadata done in one transaction. If the task row is missing, create it as done in that same transaction. SSO not required returns 422 TASK_NOT_APPLICABLE. Already recorded replays.
- POST /api/v1/tenants/{tenantId}/go-live with body {}.

Go-live refusal order after the role check:
1. 409 ALREADY_LIVE if live_at is set
2. 409 CHECKLIST_INCOMPLETE if region, modules, or admins do not match
3. 409 SSO_NOT_READY if SSO is required and metadata is absent, including when the SSO task is still open
4. 409 CHECKLIST_INCOMPLETE if any task is still open after SSO is satisfied

The agent token on either operator route returns 403 AGENT_FORBIDDEN and does not change live_at or metadata.

After live_at is set, region, modules, invites, and tasks return 409 ALREADY_LIVE. GET still works.

Every admin call writes an audit_events row with actor, method, path, http status, error code, request JSON, and response JSON. Honor X-Run-Id when the header is present.

Each mutating statement runs in a SQLite transaction. A failed request leaves no partial contract, tenant, invite, or task.

Write every test in the Tenant rules section of docs/07-test-plan.md. Use the fixture JSON files. Run the full pytest suite, including the contract tests. Do not weaken tests.

Do not build the agent loop, FakeModel, the HTML page, or a live LLM client. When pytest is green, stop and report the test count.
```

---

## Prompt 3 — Scripted agent

```text
The admin API is complete. Implement the scripted agent. The agent must change tenants only by calling the admin HTTP API. Do not import app.db or app.domain from anything under app/agent.

Read:
- AGENTS.md
- docs/02-architecture.md
- docs/05-agent.md
- docs/adr/0001-http-boundary.md
- docs/adr/0005-fake-model-in-ci.md
- fixtures/scenarios.json
- The "Scripted agent" section of docs/07-test-plan.md

Build:
- app/agent/loop.py
- app/agent/fake_model.py
- app/agent/http_tools.py
- POST /api/demo/run for mode fake
- tests that bind the app on 127.0.0.1 with an ephemeral port when the agent needs HTTP

Loop, exactly:
1. Insert a runs row.
2. Ask the model for one tool call.
3. Perform that call over HTTP with the agent token and X-Run-Id.
4. Insert a run_steps row using the real HTTP status and body.
5. Return that result to the model.
6. Stop on {"stop": true} or after 12 tool calls. stopped_reason is model_stop or step_limit.

FakeModel does not talk to a network and does not return a finished tenant. It returns the next tool name and arguments from the script in docs/05-agent.md. After create_tenant, later steps of that same run use the tenantId from the HTTP response.

Tools and no others: get_contract, create_tenant, set_region, enable_module, invite_admin, create_task, get_tenant. There is no go_live tool and no record_sso tool. An unknown tool name records a step with HTTP 400 and code VALIDATION_ERROR and the loop continues. It does not add a route.

create_tenant sends only {"contractId": "..."} plus the scenario Idempotency-Key. If the model also sent seats or modules, store both the model arguments and the stripped arguments on the step, and send only contractId.

Scripts to implement verbatim from docs/05-agent.md:
- northwind, 9 tool calls then stop, including create_task collect_sso_metadata
- contoso, and the fifth tool call is enable_module billing, which must come back as 422 MODULE_NOT_PURCHASED from the API
- fabrik, 7 tool calls then stop
- northwind_retry uses the northwind script again

POST /api/demo/run body is {"scenario": "...", "mode": "fake"}. Ensure the contract from the matching fixture file is stored, then run the loop. Response JSON is:
runId, stoppedReason, message, contract, tenant, steps.
message is the scenario text from fixtures/scenarios.json. Each step includes toolName, httpStatus, errorCode, replayed, and arguments. replayed is true when the API sent Idempotent-Replayed: true.

If scenario is northwind_retry and no Northwind tenant exists yet, return 409 VALIDATION_ERROR and do not create a tenant.

Tests to add, all green with no API key and no public DNS:
- test_northwind_script
- test_contoso_billing_rejected
- test_fabrik_ready, then the operator demo go-live returns live
- test_northwind_retry: one tenant, two invites, one task, same tenant id, create step on the retry has replayed true
- test_retry_without_first_run
- test_agent_package_has_no_db_import, failing if app.agent imports app.db or app.domain

Contoso is wrong if FakeModel itself fabricates MODULE_NOT_PURCHASED without an HTTP call. The 422 has to be the admin API's response.

Do not build the HTML page. Do not implement LiveModel beyond a stub that is unused. Do not call a hosted model. Run pytest and stop. Report which scenario tests passed.
```

---

## Prompt 4 — Checklist page

```text
Add the checklist page for Go-live. The API and the fake agent already work. Do not change their rules to make the page easier.

Read docs/06-ui.md and the Page section of docs/07-test-plan.md.

Serve static/index.html at GET /. No React, no Vite, no build step. One HTML file and a plain style block are enough.

The page shows:
- Title Go-live
- The sentence: Provisions a Fieldbase tenant from the signed contract. An operator marks the account live.
- A scenario select: Northwind, Contoso, Fabrik, Retry Northwind. Default Northwind.
- A mode select: Fake and Live. Default Fake.
- A Run button, disabled while a request is in flight
- After a successful run, Record SSO metadata and Mark live

Record SSO metadata is disabled unless the contract has ssoRequired true and SSO is not ready.
Mark live is disabled unless status is ready_for_review.
Northwind starts as waiting_on_customer, so Mark live is disabled until Record SSO metadata succeeds and the refreshed tenant is ready_for_review.

Three regions, stacked vertically when the viewport is 390px wide:
- Contract: customer, seats, region, module labels Projects, Time, and Billing, admins as name and email, SSO required, metadata present
- Trace: step index, tool name, HTTP status, error code or ok. A MODULE_NOT_PURCHASED row has a light red background. A replayed step shows the word Replayed
- Checklist: status, live yes or no, each item ok or not. Ok items use a light green background. Open tasks show their title. Show final_text when it is non-empty

Show the scenario message as read-only text above the trace. Contoso's message mentions Billing. That text is display only.

The page calls only:
- POST /api/demo/run
- POST /api/demo/tenants/{tenantId}/sso-metadata
- POST /api/demo/tenants/{tenantId}/go-live

Those operator routes already proxy with the operator token on the server. Do not put agent-local, operator-local, or any bearer token in the HTML or in browser script.

On a problem JSON, show code and detail above the columns. Keep the previous tenant on screen if a later click fails.

White background, sans-serif, black text. No chart, no hero section, no accuracy number, no login form, no chat box, no contract editor.

Add the operator demo routes if Prompt 3 did not leave them in place. They attach the operator token on the server and proxy to the admin API.

Tests:
- test_index_has_title: GET / is 200 and the body contains Go-live and Mark live
- test_demo_run_json_matches_northwind: the same tenant assertions as test_northwind_script

Run the full pytest suite. Fix the page or the demo response if a field the page needs is missing. Do not relax the Northwind, Contoso, or retry assertions. Do not call a live model. Stop when pytest is green and name the files you changed.
```

---

## Prompt 5 — Live model adapter

```text
Add the live model adapter. Fake mode and the page already work. Do not change the fake scripts. Do not call a real model while you do this task. Do not put an API key in the repo.

Read the Live model section of docs/05-agent.md, docs/adr/0005-fake-model-in-ci.md, and docs/09-demo-and-resume.md.

Implement app/agent/live_model.py for an OpenAI-compatible POST {LLM_BASE_URL}/v1/chat/completions.

Environment, all required for live mode, with no defaults:
- LLM_BASE_URL
- LLM_API_KEY
- LLM_MODEL

If any one is missing, POST /api/demo/run with mode live returns 400 LIVE_MODEL_NOT_CONFIGURED and writes no tenant and no contract. Check the env before the run starts.

Temperature is 0. The system prompt is the verbatim block in docs/05-agent.md. The user message is the scenario message, then a line contractId: <id>, and include the idempotency key.

Map provider tool calls onto only the seven tools in docs/05-agent.md. The loop from the fake path is the same loop. LiveModel is another implementation of the model interface. Unknown tool names follow the existing VALIDATION_ERROR step behavior.

If the provider returns token usage, store the numbers on the run. If it does not, store null. Do not multiply by a price. Do not hardcode a model id.

Tests, with a stub transport and no socket:
- test_live_mode_missing_env
- test_live_model_parses_tool_call, where the stub returns a get_contract tool call and the adapter returns that name and those arguments

Block outbound network in these tests. A test that resolves a public host is a failure.

Update the root README. Remove the sentence that says the application is not built yet. Add:
- the pytest command
- the uvicorn command bound to 127.0.0.1 and a port
- Fake is the default mode
- the three env vars for live mode, with no sample secrets
- this exact line: Live result: not run yet.

Do not write a pass rate, a model name you did not call, or a filled resume bullet. Do not run Prompt 6. Run pytest and stop.
```

---

## Prompt 6 — Check the finished app against the spec

```text
The Go-live app is feature-complete. Do not add endpoints, tools, pages, or dependencies. Compare the code with the spec and fix only contradictions.

Read AGENTS.md, docs/04-admin-api.md, docs/05-agent.md, and docs/07-test-plan.md.

Check each item. If it is already true, leave it. If it is false, fix it and add or keep a test that would fail the wrong behavior.

1. app.agent does not import app.db or app.domain.
2. Status is derived, not stored.
3. Contoso's billing step is a real HTTP 422 MODULE_NOT_PURCHASED from the admin API.
4. The agent token receives 403 AGENT_FORBIDDEN on sso-metadata and go-live.
5. Northwind retry keeps one tenant id, two invites, and one SSO task.
6. Go-live refusal order matches docs/04-admin-api.md.
7. The browser source has no bearer token.
8. pytest passes with no API key. No test contacts a public model.
9. The README still contains the exact line: Live result: not run yet.

Run pytest. In the final message, list any fixes you made and the pytest summary. Do not claim a live model was evaluated.
```

---

## When a phase fails

Paste this in the **same** conversation, with the traceback under it. Do not switch to the next prompt.

```text
The last phase is not done. pytest failed, or a check in the prompt is unmet.

Fix only that failure. Do not start the next phase. Do not delete a test, skip a test, or loosen an expected status code to get a green run. Do not add a tool or route that the spec does not list.

If the failure is in a spec file under docs/ or AGENTS.md, stop and tell me the contradiction instead of editing the spec.

The failure output is below:

PASTE THE PYTEST OUTPUT HERE
```
