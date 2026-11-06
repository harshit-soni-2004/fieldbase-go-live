# 09 — Demo and resume

## Demo, about two minutes

1. Open the checklist page on the local server.
2. Run **Northwind** in fake mode. Show the contract: Projects and Time, 25 seats, SSO required, metadata not present.
3. Walk the trace: create, region, two modules, two invites, SSO task. Show status `waiting_on_customer` and Mark live disabled.
4. Run **Contoso**. Read the scenario message aloud so the Billing request is visible. Show the red `MODULE_NOT_PURCHASED` row and the checklist with only Projects.
5. Run **Fabrik**. Click **Mark live**. Show status `live`.
6. If there is time, run **Retry Northwind** and show that the tenant id did not change and invites did not double.

The sentence to say while Contoso is on screen: the model can ask for Billing, and the API refuses because Billing is not on the contract.

## What CI proves

CI proves the admin rules and the scripted tool sequence. It does not prove how a named live model behaves. Those are different claims. Use both, separately.

## Resume

Use this only after phase 5. Delete the bracketed guidance. If a live run was not done, use the shorter bullet.

**With a reviewed live run:**

> Built a go-live agent for a B2B workspace product. It provisions a tenant from the signed contract through an admin API: region, purchased modules, and named admin invites. On a scripted suite the API rejected an unpurchased module, blocked go-live while SSO metadata was missing, and replayed a retry onto the same tenant. A live run on [model name] [one true sentence: for example, asked for the unpurchased module and continued after the 422, or finished Northwind without marking the account live]. The agent has no database access and cannot mark the account live.

**Without a live run:**

> Built a go-live agent for a B2B workspace product. A scripted agent provisions tenants only through an admin API. The API rejects modules that are not on the contract, blocks go-live until required SSO metadata is recorded by an operator, and replays a retried provisioning key onto the same tenant. The agent cannot mark the account live.

## Do not claim

- A measured accuracy percentage, unless you counted a defined set of live runs and can show the notes.
- That the agent "cannot be wrong." The agent can request the wrong module. The API rejects that request.
- Production authentication, a real IdP, or a customer logo.
- That Northwind, Contoso, or Fabrik are real customers. They are fixtures. The emails are `.example`.

## Interview answers that match the code

**Why is go-live not a tool?** The implementation team owns the moment the customer is told the workspace is live. The agent can finish the checklist and still be wrong about a detail a person should see.

**What happens if the model says Billing was enabled?** The checklist is computed from `tenant_modules`. The UI and `GET` tenant do not read the model's final text for that fact.

**What does the retry prove?** One idempotency key is one tenant. Invite and module uniqueness stop a second copy of the same admin or the same module.

## Live-run notes

Fill this in phase 5. Leave it as the headings until then.

- Date:
- Model id:
- Scenario:
- Steps the model actually called:
- Any `MODULE_NOT_PURCHASED` or other error codes:
- Did the final text claim the account was live:
- Token usage, or "not reported":
- Resume sentence used:
