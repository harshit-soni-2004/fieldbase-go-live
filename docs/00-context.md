# 00 — Context

This is the context document for Go-live. Antigravity should treat `AGENTS.md` as the short rule list and this file as the explanation of the work.

## The B2B problem

A company buys a B2B workspace product. An implementation consultant then creates the workspace, turns modules on, invites the first admins, and chases single sign-on metadata. The mistakes that cost money are specific:

- A module the customer did not buy gets enabled.
- People are invited who are not on the contract, or the seat count is ignored.
- The account is called live while SSO was promised and the metadata never arrived.
- A retry after a timeout creates a second workspace or a second set of invites.

Go-live is a local, end-to-end slice of that job. The buyer, the product, and the customers are fictional. The workflow is the one implementation teams already run by hand.

## What we are building

One local application:

1. An **admin API** that stores contracts and tenant state in SQLite and enforces the contract.
2. An **agent loop** that can read a contract and change a tenant only by calling that API.
3. A **checklist page** where a person watches the tool trace and, when the checklist is clean, records SSO metadata or marks the account live.

Fieldbase, the fictional product, has three modules: `projects`, `time`, and `billing`. Regions in v1 are `ap-south-1`, `us-east-1`, and `eu-west-1`.

## What "done" means

v1 is done when all of the following are true:

- The three fixture contracts load, and the four scenarios in `fixtures/scenarios.json` run on the real API.
- Northwind ends `waiting_on_customer` with an open SSO task and is not live.
- Contoso ends `ready_for_review` with Projects on and Billing off, after a rejected Billing call.
- Fabrik ends `ready_for_review`, and the operator role can mark it live. The agent role cannot.
- Northwind run a second time with `provision-northwind-001` keeps one tenant, two invites, and one SSO task.
- `pytest` passes with no API key and no network.
- The page can run each scenario in fake mode and can mark Fabrik live.
- The README does not contain a made-up model score.

A live model adapter is part of v1, behind an interface, and it is optional at demo time. The resume line that mentions a live run stays blank until a person watches one.

## The four scenarios

### Northwind

Contract: 25 seats, Projects and Time, region `ap-south-1`, admins Asha Rao and Dev Patel, SSO required, metadata absent.

The agent creates the tenant, sets the region, enables Projects and Time, invites both admins, and opens task `collect_sso_metadata` titled "Collect SSO metadata from the customer." Status is `waiting_on_customer`. Mark live stays disabled until an operator records that SSO metadata was received.

### Contoso

Contract: 10 seats, Projects only, region `us-east-1`, admin Mia Chen, SSO not required.

The user message also says the customer emailed asking for Billing. Billing is not on the contract. The scripted model calls `enable_module` for `billing`, the API returns `422 MODULE_NOT_PURCHASED`, and the run continues. Projects is on. Billing is absent. No SSO task. Status is `ready_for_review`.

### Fabrik

Contract: 5 seats, Projects and Time, region `eu-west-1`, admin Lena Ortiz, SSO not required.

The scripted run finishes with a clean checklist and status `ready_for_review`. An operator marks the account live. A second call returns `409 ALREADY_LIVE`. The agent token receives `403 AGENT_FORBIDDEN` on go-live.

### Northwind retry

The same contract and the same idempotency key as the first Northwind run. Writes replay. Counts do not increase. The tenant id does not change.

## Who does what

| Actor | Can do | Cannot do |
|---|---|---|
| Agent role | Read the contract, create the tenant, set the region, enable a purchased module, invite a named admin, create the SSO task when it applies, read the tenant | Mark live, record SSO metadata, delete, send email, write SQL |
| Operator role | Everything the agent can do, plus record SSO metadata and mark live | Bypass a failed checklist |
| Live or fake model | Choose the next tool call from the conversation | Touch the database or decide that a rejected call succeeded |
| Checklist page | Start a scenario, show the trace, expose the two operator actions | Embed the agent token in the browser |

## Status

Status is computed. Callers do not set it.

| Status | When |
|---|---|
| `provisioning` | Region, modules, or required admins do not match the contract yet |
| `waiting_on_customer` | Region, modules, and admins match, and SSO is required while metadata is absent |
| `ready_for_review` | Region, modules, and admins match, SSO does not block, and no task is open |
| `live` | An operator has successfully called go-live |

Northwind after the agent: `waiting_on_customer`. After the operator records SSO metadata: `ready_for_review`. After go-live: `live`.

Contoso and Fabrik after the agent: `ready_for_review`. Contoso is never given a Billing module by the rejection path.

## Out of scope for v1

OAuth, a CRM, a real IdP, SAML or OIDC metadata parsing, outbound email, payments, more modules, more regions, multi-tenant hosting, Docker as a requirement, a second deployable, and any resume metric that was not produced by a command in this repo.

## How to talk about it later

The interview sentence is: the model proposes tool calls, and the admin API accepts only what the contract allows. CI proves that sequence with a fake model. A live model is a separate, optional run. Wording for the resume is in `09-demo-and-resume.md`.
