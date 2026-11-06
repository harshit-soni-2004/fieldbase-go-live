# 01 — Product

## Users

- **Implementation agent.** Untrusted. It receives a contract id and a short instruction and must finish provisioning through tools.
- **Operator.** A person on the implementation team. They watch the checklist, record that SSO metadata arrived, and mark the account live.
- **Reviewer of this repo.** Needs to run the fake scenarios with one command and see the same results as the tests.

There is no customer login in v1. The customers are rows in the fixture contracts.

## Catalog

| Id | Label | Notes |
|---|---|---|
| `projects` | Projects | Purchasable |
| `time` | Time | Purchasable |
| `billing` | Billing | Purchasable. On Contoso it is requested in the chat and refused |

Regions: `ap-south-1`, `us-east-1`, `eu-west-1`.

## Contract

A contract is immutable after intake except for `ssoMetadataPresent`, which flips to true only through the operator SSO endpoint.

Required fields are the JSON files in `fixtures/`. Intake rules:

- `contractId` matches `ctr_` plus lowercase letters.
- `seats` is an integer from 1 to 100000.
- `modules` is a non-empty subset of the catalog, with no duplicates.
- `region` is in the region list.
- `admins` has at least one entry, unique emails, and `admins.length <= seats`.
- Emails match a simple address shape and use the `.example` domain in the fixtures.
- `ssoRequired` and `ssoMetadataPresent` are booleans.
- If `ssoRequired` is false, `ssoMetadataPresent` is stored false and is ignored by the checklist.

An invalid contract returns `422` with one of `UNKNOWN_MODULE`, `UNKNOWN_REGION`, `CONTRACT_SEAT_CONFLICT`, or `VALIDATION_ERROR`. It is not stored.

## Checklist

`GET` tenant returns a checklist computed from the contract and the tenant rows.

| Item | Ok when |
|---|---|
| Region | `tenant.region` equals `contract.region` |
| Modules | Enabled set equals the contract module set |
| Admins | Invited email set equals the contract admin email set |
| SSO | If `ssoRequired` is false, the item is `not_applicable`. If metadata is present, the item is ok. If metadata is absent, the item is blocking and the open task `collect_sso_metadata` must exist for the agent run to count as finished |
| Live | `live_at` is null until go-live |

Exact sets matter. An extra module or an extra invite fails the checklist and blocks go-live with `409 CHECKLIST_INCOMPLETE`.

## Blocking task

| Code | Title | Created when |
|---|---|---|
| `collect_sso_metadata` | Collect SSO metadata from the customer | `ssoRequired` is true and `ssoMetadataPresent` is false |

Any other task code returns `422 TASK_NOT_APPLICABLE`. Creating this task when SSO is not required, or when metadata is already present, also returns `422 TASK_NOT_APPLICABLE`.

Recording SSO metadata is an operator action. It sets `ssoMetadataPresent` true and marks that task `done`. The agent has no tool for it.

## Go-live

Preconditions, all required:

- Caller role is operator.
- Region, modules, and admins match the contract.
- SSO is not required, or metadata is present. A still-open `collect_sso_metadata` task with metadata absent is `SSO_NOT_READY`.
- No other task is open.

Success sets `live_at` and the derived status becomes `live`. Provisioning writes after that return `409 ALREADY_LIVE`. A second go-live returns `409 ALREADY_LIVE`.

Agent role: `403 AGENT_FORBIDDEN` without reading the body as a successful live.

## Operator-visible outcomes

| Scenario | After the agent | Operator next step |
|---|---|---|
| Northwind | Waiting on SSO | Record SSO metadata, then mark live |
| Contoso | Ready for review, Billing off | May mark live. Billing stays off |
| Fabrik | Ready for review | Mark live |
| Northwind retry | Same waiting tenant | No new rows |

## v1 scope

In scope: the three contracts, four scenarios, admin API, derived checklist, agent loop, fake model, live-model interface, checklist page, audit rows, tests in `07-test-plan.md`.

Later, and not part of this build: OAuth, CRM sync, a real IdP, email, hosting, more than one tenant per contract, and editing a contract's modules after intake.
