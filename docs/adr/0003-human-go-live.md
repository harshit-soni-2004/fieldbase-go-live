# ADR 0003 — A person marks the account live

## Status

Accepted

## Decision

`go-live` and `sso-metadata` are operator routes. They are not tools. The agent token receives `403 AGENT_FORBIDDEN`.

Go-live also requires a matching region, an exact module set, an exact admin set, and SSO metadata when SSO is required. Status is derived from those rows and from `live_at`. The model cannot set status.

Recording SSO metadata stores a boolean. v1 does not parse SAML or OIDC XML.

## Why

"The workspace is live" is the message a customer hears. That decision stays with the implementation owner, who can see the checklist. SSO metadata is a fact about the customer, supplied by a person, not inferred by the model.

## Consequences

Northwind cannot be marked live until an operator records SSO metadata, even if the agent created the task and wrote a confident final message. The page disables Mark live until `status` is `ready_for_review`.
