# 07 — Test plan

`pytest` must pass with no environment variables, no API key, and no network. Tests that need a server use FastAPI's test client or an in-process ASGI app bound to a local ephemeral port for the agent HTTP client. The agent tests are the ones that bind a port, because the agent is required to use HTTP. They still must not resolve a public host.

Each test gets its own database.

An architecture test scans `app/agent` and fails if that package imports `app.db` or `app.domain`.

## Contract intake

| Test | Assert |
|---|---|
| `test_load_three_fixtures` | POST each fixture file, GET returns the same modules and emails |
| `test_unknown_module_rejected` | `billingg` or `crm` returns `UNKNOWN_MODULE` and GET is 404 |
| `test_unknown_region_rejected` | `UNKNOWN_REGION` |
| `test_too_many_admins_rejected` | Two admins and `seats: 1` returns `CONTRACT_SEAT_CONFLICT` |
| `test_same_contract_replays` | Second identical POST is 200 with `Idempotent-Replayed: true` |
| `test_same_contract_id_different_body` | `409 IDEMPOTENCY_KEY_REUSED` |

## Tenant rules

| Test | Assert |
|---|---|
| `test_create_requires_idempotency_key` | `400 IDEMPOTENCY_KEY_MISSING` |
| `test_create_copies_seats_and_leaves_region_null` | Body seats ignored if sent as an extra field (`VALIDATION_ERROR`). A legal body stores contract seats and null region |
| `test_region_must_match_contract` | Wrong region `REGION_MISMATCH`, then the contract region succeeds |
| `test_region_replay_and_conflict` | Same region replays. A second different region is `REGION_ALREADY_SET` |
| `test_module_not_purchased` | Contoso, enable `billing`, `MODULE_NOT_PURCHASED`, module list does not include it |
| `test_unknown_module_on_tenant` | `UNKNOWN_MODULE` |
| `test_enable_replay` | Second enable of `projects` replays, one row |
| `test_invite_unknown_email` | `EMAIL_NOT_ON_CONTRACT` |
| `test_invite_replay` | Same email once, replay header the second time |
| `test_seat_cap_backstop` | Build a tenant whose contract has `seats` 1 and one admin. Insert is not done by skipping the API. Call invite for that admin (success), then the test uses a domain helper only if the HTTP path cannot represent a second legal email. Preferred HTTP path: not required if `EMAIL_NOT_ON_CONTRACT` is the reachable case. Add a unit test on the seat function: when existing invites equal seats, the next new email is `SEAT_CAP` |
| `test_task_only_when_sso_required` | Contoso `create_task` returns `TASK_NOT_APPLICABLE`. Northwind returns the open task. Second call replays |
| `test_create_idempotent_replay` | Same key and contract returns the same `tenantId` |
| `test_key_reused_for_other_contract` | `IDEMPOTENCY_KEY_REUSED` |
| `test_second_key_same_contract` | `CONTRACT_ALREADY_PROVISIONED` |
| `test_agent_cannot_go_live` | `403 AGENT_FORBIDDEN` and `live` is false |
| `test_agent_cannot_record_sso` | `403 AGENT_FORBIDDEN` |
| `test_go_live_blocked_for_northwind` | After a finished Northwind checklist with SSO open, operator go-live returns `SSO_NOT_READY` |
| `test_sso_then_go_live` | Operator records SSO metadata, task is `done`, go-live returns `live` |
| `test_go_live_incomplete_checklist` | Operator go-live before modules are enabled returns `CHECKLIST_INCOMPLETE` |
| `test_already_live_rejects_module_write` | `ALREADY_LIVE` |
| `test_checklist_exact_modules` | An extra purchased-looking enable that was rejected does not appear. A successful extra is impossible for Contoso. For a contract that includes only `projects`, the checklist `ok` is false if `time` were enabled; time is not purchased so it cannot be enabled. Exact-set is asserted on the happy Northwind GET |

## Scripted agent

These use `POST /api/demo/run` with `mode: fake` unless a test drives the loop directly.

| Test | Assert |
|---|---|
| `test_northwind_script` | Status `waiting_on_customer`, modules exactly `projects` and `time`, both admin emails, one open SSO task, `live` false, 9 tool steps then stop |
| `test_contoso_billing_rejected` | One step with `MODULE_NOT_PURCHASED`, modules exactly `["projects"]`, one invite, no tasks, status `ready_for_review` |
| `test_fabrik_ready` | Status `ready_for_review`, then operator demo go-live returns `live` |
| `test_northwind_retry` | Run Northwind, then `northwind_retry`. One tenant row, two invites, one task. At least the create step on the retry has replay true. Tenant id unchanged |
| `test_retry_without_first_run` | `northwind_retry` on an empty database returns `VALIDATION_ERROR` |
| `test_agent_package_has_no_db_import` | Architecture scan |

## Live adapter, no network

| Test | Assert |
|---|---|
| `test_live_mode_missing_env` | `LIVE_MODEL_NOT_CONFIGURED`, contract may be unread, no tenant row |
| `test_live_model_parses_tool_call` | Stub HTTP returns a tool call for `get_contract`. The adapter returns that name and arguments. No DNS |

## Page

| Test | Assert |
|---|---|
| `test_index_has_title` | `GET /` is 200 and the body contains `Go-live` and `Mark live` |
| `test_demo_run_json_matches_northwind` | Same assertions as `test_northwind_script` through the demo route |

## Explicitly not tested in v1

Pixel layout, a real Gemini or OpenAI account, load, and concurrent double-submits beyond the idempotency cases above. SQLite serializes writers; a concurrency test is not required for v1.
