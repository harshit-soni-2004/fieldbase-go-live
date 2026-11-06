# 04 — Admin API

Base path `/api/v1`. JSON. Unknown JSON fields on write bodies return `422 VALIDATION_ERROR` and change nothing.

## Auth

`Authorization: Bearer <token>`. Role comes from the token. `APP_ENV=local` accepts the two local tokens from `02-architecture.md`. Any other environment refuses to start with the local default tokens still set.

## Problem body

Errors use this shape:

```json
{
  "type": "about:blank",
  "title": "Module not purchased",
  "status": 422,
  "code": "MODULE_NOT_PURCHASED",
  "detail": "billing is not on contract ctr_contoso"
}
```

`code` is stable. Tests assert `code`, not `detail` wording.

## Error codes

| Code | HTTP | When |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Malformed JSON, unknown field, bad id shape, empty module list |
| `UNKNOWN_MODULE` | 422 | Module id is not in the catalog, including at contract intake |
| `UNKNOWN_REGION` | 422 | Region is not in the allowlist |
| `CONTRACT_SEAT_CONFLICT` | 422 | `admins.length > seats` at intake |
| `CONTRACT_NOT_FOUND` | 404 | |
| `TENANT_NOT_FOUND` | 404 | |
| `MODULE_NOT_PURCHASED` | 422 | Module is in the catalog and not on this contract |
| `REGION_MISMATCH` | 422 | Region is allowed globally and is not this contract's region |
| `REGION_ALREADY_SET` | 409 | Tenant already has a different region |
| `EMAIL_NOT_ON_CONTRACT` | 422 | Email is not one of the contract admins |
| `SEAT_CAP` | 422 | A new distinct invite would exceed `seats` |
| `CONTRACT_ALREADY_PROVISIONED` | 409 | Contract already has a tenant and the idempotency key is different |
| `IDEMPOTENCY_KEY_MISSING` | 400 | `POST /tenants` without the header |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Same key, different `contractId` |
| `TASK_NOT_APPLICABLE` | 422 | Task code is not `collect_sso_metadata`, or SSO does not need it |
| `AGENT_FORBIDDEN` | 403 | Agent token called an operator route |
| `SSO_NOT_READY` | 409 | Go-live while SSO is required and metadata is absent |
| `CHECKLIST_INCOMPLETE` | 409 | Go-live while region, modules, or admins do not match |
| `ALREADY_LIVE` | 409 | Go-live again, or a provisioning write after `live_at` is set |
| `LIVE_MODEL_NOT_CONFIGURED` | 400 | Demo live mode without provider env vars. Not an admin-API code; see demo routes below |

Successful replay of an existing write returns the original resource with header `Idempotent-Replayed: true`.

## Contracts

### `POST /api/v1/contracts`

Role: agent or operator. Body is a fixture object (`contractId`, `customerName`, `seats`, `modules`, `region`, `admins`, `ssoRequired`, `ssoMetadataPresent`).

`201` returns the stored contract. Posting the same `contractId` with the same canonical JSON returns `200` and `Idempotent-Replayed: true`. The same id with different JSON returns `409 IDEMPOTENCY_KEY_REUSED`.

### `GET /api/v1/contracts/{contractId}`

Role: agent or operator. `200` is the stored contract, modules in catalog order `projects`, `time`, `billing`, admins in email order.

## Tenants

### `POST /api/v1/tenants`

Role: agent or operator. Header `Idempotency-Key` required. Header `X-Run-Id` optional.

Body:

```json
{ "contractId": "ctr_northwind" }
```

The server copies `customerName` and `seats` from the contract. `region` stays null. `201` body:

```json
{
  "tenantId": "ten_0123456789ab",
  "contractId": "ctr_northwind",
  "customerName": "Northwind",
  "seats": 25,
  "region": null,
  "status": "provisioning",
  "live": false
}
```

Replay with the same key and contract id returns that same body, `200`, `Idempotent-Replayed: true`.

### `POST /api/v1/tenants/{tenantId}/region`

Body: `{ "region": "ap-south-1" }`.

The region must be the contract region. First success returns `200` and the tenant. The same region again replays. A different region returns `409 REGION_ALREADY_SET` if one is already stored, otherwise `422 REGION_MISMATCH` when it is not the contract region.

### `POST /api/v1/tenants/{tenantId}/modules`

Body: `{ "module": "projects" }`.

Catalog miss: `422 UNKNOWN_MODULE`. Not on the contract: `422 MODULE_NOT_PURCHASED`. Success and replay: `200` with the enabled module list.

### `POST /api/v1/tenants/{tenantId}/invites`

Body: `{ "email": "asha@northwind.example" }`.

The server lowercases the email, checks it is on the contract, copies the name from the contract, and enforces the seat backstop. Success and replay return the invite. The name in the body is not accepted; unknown field rules reject it if a client sends `name`.

### `POST /api/v1/tenants/{tenantId}/tasks`

Body: `{ "code": "collect_sso_metadata" }`.

The server sets the title. Clients do not send a title. Success and replay return the task with `status: "open"`.

### `GET /api/v1/tenants/{tenantId}`

`200`:

```json
{
  "tenantId": "ten_0123456789ab",
  "contractId": "ctr_northwind",
  "customerName": "Northwind",
  "seats": 25,
  "region": "ap-south-1",
  "status": "waiting_on_customer",
  "live": false,
  "modules": ["projects", "time"],
  "invites": [
    {"email": "asha@northwind.example", "name": "Asha Rao"}
  ],
  "tasks": [
    {
      "code": "collect_sso_metadata",
      "title": "Collect SSO metadata from the customer",
      "status": "open"
    }
  ],
  "checklist": {
    "region": {"expected": "ap-south-1", "actual": "ap-south-1", "ok": true},
    "modules": {"expected": ["projects", "time"], "actual": ["projects", "time"], "ok": true},
    "admins": {
      "expected": ["asha@northwind.example", "dev@northwind.example"],
      "actual": ["asha@northwind.example"],
      "ok": false
    },
    "sso": {"state": "blocking", "ok": false},
    "live": {"ok": false}
  }
}
```

`sso.state` is `not_applicable`, `blocking`, or `ready`. `admins.actual` is sorted by email. Module arrays follow catalog order.

## Operator routes

### `POST /api/v1/tenants/{tenantId}/sso-metadata`

Role: operator. Body `{}`.

Requires `ssoRequired` true. Sets metadata present and the SSO task to `done`. If the task does not exist yet, create it as `done` in the same transaction so the operator action is enough. Agent token: `403 AGENT_FORBIDDEN`. SSO not required: `422 TASK_NOT_APPLICABLE`. Replay when metadata is already present: `200` and `Idempotent-Replayed: true`.

### `POST /api/v1/tenants/{tenantId}/go-live`

Role: operator. Body `{}`.

Returns the tenant with `live: true` and `status: "live"`.

Refusal order after the role check (`403 AGENT_FORBIDDEN` for the agent token):

1. `ALREADY_LIVE` if `live_at` is set.
2. `CHECKLIST_INCOMPLETE` if region, modules, or admins do not match.
3. `SSO_NOT_READY` if SSO is required and metadata is absent. An open `collect_sso_metadata` task is part of this case.
4. `CHECKLIST_INCOMPLETE` if any task is still `open` after SSO is satisfied.

A finished Northwind tenant returns `SSO_NOT_READY`. A tenant with the region or modules unfinished returns `CHECKLIST_INCOMPLETE` even when SSO metadata is also absent. Fabrik, with a clean checklist, passes.

## Demo routes

These are not agent tools.

### `POST /api/demo/run`

Body: `{ "scenario": "northwind", "mode": "fake" }`.

`mode` is `fake` or `live`. The server loads the scenario, ensures the contract is stored, creates the run, and executes the agent loop with the agent token. `200` returns `{ "runId", "stoppedReason", "message", "contract", "tenant", "steps" }`. `message` is the scenario text. `contract` is the stored contract. Each step includes `toolName`, `httpStatus`, `errorCode`, `replayed`, and `arguments`.

`mode: "live"` without `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` returns `400 LIVE_MODEL_NOT_CONFIGURED` and does not create a tenant.

`northwind_retry` returns `409` with code `VALIDATION_ERROR` if Northwind has never been run in this database. Detail can say the first scenario is required. Tests run Northwind first.

### `POST /api/demo/tenants/{tenantId}/sso-metadata`

### `POST /api/demo/tenants/{tenantId}/go-live`

The page calls these. The server attaches the operator token and proxies to the admin API. The browser does not send a bearer token.

### `GET /api/demo/runs/{runId}`

Returns the run, its steps, and the current tenant.

## Provisioning lock after go-live

`region`, `modules`, `invites`, and `tasks` return `409 ALREADY_LIVE` once `live_at` is set. `GET` still works.
