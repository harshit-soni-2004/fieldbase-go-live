# 05 — Agent

## Loop

1. Create a `runs` row.
2. Send the model the system prompt, the scenario message, the contract id, the idempotency key, and the tool list.
3. Read one tool call. Execute it as HTTP against the admin API with the agent token and `X-Run-Id`.
4. Append a `run_steps` row with the real status code and body.
5. Give that result back to the model.
6. Stop when the model returns a finish signal, or when 12 steps have been executed.

The loop does not enable modules by itself and does not "fix" a rejected call. The next step is whatever the model asks for.

A finish signal is a response with no tool call and a short text field `final_text`. The fake model finishes by returning `{"stop": true}` after its script.

## Tools

The model may call only these. Names match the implementation exactly.

| Tool | HTTP | Arguments |
|---|---|---|
| `get_contract` | `GET /api/v1/contracts/{contractId}` | `contractId` |
| `create_tenant` | `POST /api/v1/tenants` | `contractId`, and the loop adds `Idempotency-Key` from the scenario |
| `set_region` | `POST /api/v1/tenants/{tenantId}/region` | `tenantId`, `region` |
| `enable_module` | `POST /api/v1/tenants/{tenantId}/modules` | `tenantId`, `module` |
| `invite_admin` | `POST /api/v1/tenants/{tenantId}/invites` | `tenantId`, `email` |
| `create_task` | `POST /api/v1/tenants/{tenantId}/tasks` | `tenantId`, `code` |
| `get_tenant` | `GET /api/v1/tenants/{tenantId}` | `tenantId` |

There is no `go_live`, `send_email`, `delete_tenant`, or `record_sso` tool. If a live model emits an unknown tool name, the loop records a step with HTTP status `400` and code `VALIDATION_ERROR` and continues. It does not invent a route.

`create_tenant` arguments from the model do not include seats or modules. If the model adds them, the loop strips unknown fields before the HTTP call and records the stripped arguments in the step. The API would reject unknown fields; stripping here keeps one bad argument from hiding the rest of the demo. The step stores both the model arguments and the arguments actually sent.

## Fake model scripts

`FakeModel` ignores the prose and returns the next call for that scenario. The calls still hit the API. Tenant ids returned by `create_tenant` are remembered by the fake model for later steps of that run only.

### northwind

1. `get_contract` `ctr_northwind`
2. `create_tenant` `ctr_northwind`
3. `set_region` contract region `ap-south-1`
4. `enable_module` `projects`
5. `enable_module` `time`
6. `invite_admin` `asha@northwind.example`
7. `invite_admin` `dev@northwind.example`
8. `create_task` `collect_sso_metadata`
9. `get_tenant`
10. stop

### contoso

1. `get_contract` `ctr_contoso`
2. `create_tenant` `ctr_contoso`
3. `set_region` `us-east-1`
4. `enable_module` `projects`
5. `enable_module` `billing`
6. `invite_admin` `mia@contoso.example`
7. `get_tenant`
8. stop

Step 5 must be the Billing call. The test asserts that step's `error_code` is `MODULE_NOT_PURCHASED` and that a later `get_tenant` does not list `billing`.

### fabrik

1. `get_contract` `ctr_fabrik`
2. `create_tenant` `ctr_fabrik`
3. `set_region` `eu-west-1`
4. `enable_module` `projects`
5. `enable_module` `time`
6. `invite_admin` `lena@fabrik.example`
7. `get_tenant`
8. stop

### northwind_retry

The same script as Northwind. Assertions are about replay and unchanged counts, not about a different script.

## Live model

`LiveModel` uses an OpenAI-compatible chat completions endpoint.

| Env var | Required for live mode |
|---|---|
| `LLM_BASE_URL` | Yes, origin only, no path guessing beyond `/v1/chat/completions` |
| `LLM_API_KEY` | Yes |
| `LLM_MODEL` | Yes. No default model id in code |

Temperature is `0`. The adapter maps tool calls to the seven tools above. If the provider returns usage tokens, store them on the run. If it does not, store null. Do not price tokens.

If the three variables are missing, live mode fails before any tenant write with `LIVE_MODEL_NOT_CONFIGURED`.

The live system prompt is the following text, verbatim:

```text
You provision a Fieldbase tenant by calling tools. The stored contract is the only source of truth for region, modules, seats, admins, and SSO.

Call get_contract first. Then create_tenant, set_region to the contract region, enable_module for each purchased module only, and invite_admin for each contract admin email only.

If ssoRequired is true and ssoMetadataPresent is false, call create_task with code collect_sso_metadata. Otherwise do not create a task.

If a tool returns an error, leave that request failed and continue with what the contract allows. Do not retry a MODULE_NOT_PURCHASED call with a different story.

Call get_tenant before you finish. Finish when region, modules, and admins match the contract, and the SSO task exists when SSO metadata is still required.

Do not say the account is live. You cannot mark it live, send email, or record SSO metadata.
```

The scenario message and the idempotency key are the user message, plus one line: `contractId: <id>`.

## What the tests are allowed to assume

Tests may assert the fake scripts call the API and leave the rows described in `AGENTS.md`. Tests may not assert that a live model follows the system prompt. A separate test may use a stub transport to show that `LiveModel` sends the system prompt and parses a tool call, with no socket.
