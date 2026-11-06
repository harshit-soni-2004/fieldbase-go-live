# ADR 0002 — The stored contract wins

## Status

Accepted

## Decision

Seats, modules, region, named admins, and the SSO requirement come from the contract row. The scenario message is shown to the model and is not an input to those checks.

`enable_module` allows a module only when that module is on the contract. `set_region` allows only the contract region. `invite_admin` allows only contract admin emails. `create_tenant` copies seats and customer name from the contract. The body cannot override them.

Contoso's message asks for Billing. The Contoso file does not include `billing`. The API returns `MODULE_NOT_PURCHASED`.

## Why

Implementation work already fails this way in practice: a side email asks for something the order form did not buy. The interesting behavior is the refusal, recorded on the trace, while the purchased setup still finishes.

## Consequences

Changing what a customer bought means a new contract fixture, not a sentence in the chat. Tests load `fixtures/*.json` rather than a paraphrased dict that can drift.
