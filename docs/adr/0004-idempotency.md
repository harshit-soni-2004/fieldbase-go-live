# ADR 0004 — Retries return the original row

## Status

Accepted

## Decision

`POST /tenants` requires `Idempotency-Key`. The same key and the same `contractId` return the original tenant and `Idempotent-Replayed: true`. The same key and a different `contractId` return `409 IDEMPOTENCY_KEY_REUSED`. A new key for a contract that already has a tenant returns `409 CONTRACT_ALREADY_PROVISIONED`.

Enabling a module that is already enabled, inviting an email that is already invited, and creating a task code that already exists are replays of that row, not duplicates.

Identical contract POSTs replay. The same contract id with different JSON is `IDEMPOTENCY_KEY_REUSED`.

## Why

The failure this project is about includes the double submit: the consultant clicks again after a timeout and gets a second workspace. The Northwind retry scenario is that case.

## Consequences

Uniqueness is in the database (`contract_id`, `idempotency_key`, `(tenant_id, module)`, `(tenant_id, email)`, `(tenant_id, code)`), not only in the agent script. The retry scenario runs the same script again and asserts counts.
