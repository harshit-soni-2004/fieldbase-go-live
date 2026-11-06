# Go-live — interview explanation

Use this after the app matches the spec in `docs/`. Until `pytest` is green, say you designed it and are building it. After the suite is green, say you built the scripted path. Mention a live model only if you filled the notes at the bottom of `docs/09-demo-and-resume.md`.

Northwind, Contoso, and Fabrik are fixture customers. The addresses are `.example`. Fieldbase is a fictional B2B workspace product. Local tokens are not production authentication. SSO metadata in v1 is a boolean an operator records, not a parsed SAML file.

Resume wording lives in `docs/09-demo-and-resume.md`. This file is how you defend that wording.

## 30 seconds

I built a go-live agent for a B2B workspace product. When a customer signs, someone has to create the tenant in the right region, turn on only the modules they bought, invite the named admins, and hold the account if SSO metadata has not arrived. The agent does that by calling an admin API. The contract row is the source of truth. If the model asks for a module that was not purchased, the API rejects that call and the rest of the setup still finishes. The agent cannot mark the account live. An operator does that from a checklist, after looking at the trace.

## Two minutes

The expensive mistakes in implementation are specific. A module gets enabled that the order form did not include. A retry after a timeout creates a second workspace. Someone tells the customer the account is live while SSO was promised and the metadata never showed up.

I split that job into three pieces.

The admin API stores the contract and the tenant in SQLite. It copies seats and the customer name from the contract. It will not enable a module that is not on the contract, invite an email that is not a named admin, or set a region other than the contracted region. Status is not a column the agent can write. It is derived from those rows. `live` appears only after an operator calls go-live and the checklist matches.

The agent is a loop. It asks a model for one tool call, performs that call over HTTP with an agent token, stores the real status code, and shows the result back to the model. It has seven tools: read the contract, create the tenant, set the region, enable a module, invite an admin, open the SSO task, and read the tenant back. There is no go-live tool and no send-email tool. The agent package is not allowed to import the database. A test fails the build if it does.

The page shows the contract, the tool trace, and the checklist. Tokens stay on the server. The browser cannot call go-live with the agent credential.

I demo four cases. Northwind needs SSO, so the agent finishes provisioning and the account stays `waiting_on_customer`. Contoso's instruction also asks for Billing, which is not on the contract. The trace shows `422 MODULE_NOT_PURCHASED`, and Billing stays off. Fabrik's checklist is clean, and an operator marks it live. The agent token gets `403` on that route. Running Northwind again with the same idempotency key returns the same tenant. Invites do not double.

The CI suite drives a scripted model through those calls against the real API. That proves the rules and the orchestration. It does not prove how a named hosted model behaves. I keep those sentences separate.

## What you draw

```text
checklist page
    |  start scenario, record SSO, mark live
    v
demo routes  (tokens stay here)
    |                \
    v                 v
agent loop        admin API ------ SQLite
    |
    v
fake model or live model
```

Say this while you draw: the model never points at SQLite. Every mutation is an HTTP call the API can reject. The page's operator buttons use a different token than the agent, and that token is attached on the server.

## The four cases, and the question each one answers

### Northwind — "What if the work is not actually finished?"

Contract: 25 seats, Projects and Time, `ap-south-1`, two admins, SSO required, no metadata.

The scripted run creates the tenant, sets the region, enables the two purchased modules, invites Asha Rao and Dev Patel, and opens a task titled "Collect SSO metadata from the customer." Status is `waiting_on_customer`. Mark live stays disabled.

If they ask why the task exists: the customer still owes us something. The agent can see that from the contract and open the chase. It cannot pretend the metadata arrived. Recording metadata is an operator action. It flips a boolean and marks that task done in one transaction. Only then is the status `ready_for_review`, and only then can a person mark the account live.

### Contoso — "What if the model is talked into the wrong module?"

Contract: 10 seats, Projects only, `us-east-1`, one admin, SSO not required.

The user message says the customer also emailed asking to turn Billing on. That sentence is shown to the model. It is not written onto the contract. The scripted model calls `enable_module` for `billing`. The API returns `422 MODULE_NOT_PURCHASED` and inserts nothing. The loop does not stop and does not "correct" the contract. It invites Mia Chen and reads the tenant back. Modules are exactly `["projects"]`. Status is `ready_for_review`.

The line to say with the red row on screen: the model can ask for Billing. The API refuses because Billing is not on the contract. The checklist is computed from `tenant_modules`, not from the model's closing text. If the model says Billing was enabled, the page still shows it off.

### Fabrik — "Who is allowed to say the customer is live?"

Contract: 5 seats, Projects and Time, `eu-west-1`, one admin, SSO not required.

The run ends `ready_for_review`. The operator clicks Mark live. `live_at` is set. A second go-live returns `409 ALREADY_LIVE`. Provisioning writes after that also return `409 ALREADY_LIVE`. The agent token on go-live returns `403 AGENT_FORBIDDEN` and does not set `live_at`.

Why this is not a tool: "you are live" is the message the customer hears. The implementation owner should see the checklist before that message goes out. The agent can be finished and still be wrong about a detail.

### Northwind retry — "What if the consultant clicks twice?"

Same contract, same key `provision-northwind-001`. The script runs again. `POST /tenants` returns the original tenant id and `Idempotent-Replayed: true`. The same module, the same email, and the same task code replay the existing rows. One tenant, two invites, one SSO task.

Say: one idempotency key is one tenant. Uniqueness on `(tenant, module)`, `(tenant, email)`, and `(tenant, code)` is in the database, so a second copy is not only a polite agent.

## How a single step works

1. The loop has a run id.
2. The model returns one tool name and arguments.
3. The HTTP client calls the admin API with the agent bearer token and `X-Run-Id`.
4. The API checks the role, the contract, and idempotency inside a SQLite transaction.
5. The step row stores the real status code, the error code if any, and whether the response was a replay.
6. That body goes back to the model.
7. A rejected call is a normal step. The run is not crashed. The model is expected to continue with what the contract allows.
8. The loop stops when the model returns no tool call, or at 12 steps. The fake scripts finish inside that limit. Hitting the limit returns the tenant as it actually is, with `stopped_reason: step_limit`. It does not invent the missing invites.

`create_tenant` sends only `contractId` plus the idempotency key. If a model also sends seats or a module list, those fields are stripped before the HTTP call, and the step stores both the original arguments and the arguments that were sent. The API would reject unknown fields. Stripping keeps one bad argument from hiding the rest of the demo. Seats still come from the contract row, not from the model.

## Status

There is no status column. A caller cannot `PATCH` a tenant to `live`.

| Derived status | Condition |
|---|---|
| `live` | `live_at` is set |
| `waiting_on_customer` | Region, modules, and admins match, and SSO is required while metadata is absent |
| `ready_for_review` | Those match, SSO does not block, and no task is open |
| `provisioning` | Anything else |

Go-live does not trust the derived status alone. Inside the same transaction it rechecks, in this order: already live, then region and modules and admins, then SSO, then any task still open. A half-built Northwind fails with `CHECKLIST_INCOMPLETE` even though SSO is also missing, because the region or the modules are unfinished. A finished Northwind with metadata absent fails with `SSO_NOT_READY`. Fabrik passes.

That order matters in the interview. If you only say "go-live checks the checklist," they may ask which error the caller sees when two things are wrong. The unfinished workspace is `CHECKLIST_INCOMPLETE`. The finished workspace that is waiting on SSO is `SSO_NOT_READY`.

## Idempotency, said precisely

| Situation | Result |
|---|---|
| `POST /tenants` with no key | `400 IDEMPOTENCY_KEY_MISSING` |
| Same key, same contract | Original tenant, header `Idempotent-Replayed: true` |
| Same key, different contract | `409 IDEMPOTENCY_KEY_REUSED` |
| New key, contract already has a tenant | `409 CONTRACT_ALREADY_PROVISIONED` |
| Enable a module that is already on | Replay, one row |
| Invite an email that is already invited | Replay, one row |
| Create the SSO task code again | Replay, one open task |
| Identical contract POST | Replay |
| Same contract id, different JSON | `409 IDEMPOTENCY_KEY_REUSED` |

v1 allows one tenant per contract. The key and the unique `contract_id` are both required. The key covers the double click. The unique contract id covers a second key for a customer who was already provisioned.

## Roles

Two bearer tokens, used when `APP_ENV=local`. Defaults are `agent-local` and `operator-local`. Missing or unknown bearer is `401`. The agent token on an operator route is `403 AGENT_FORBIDDEN`.

Say this before they ask: this is a role split for the demo, not production authentication. There is no OAuth, no user directory, and no rotation story. What the split demonstrates is that the credential which can call tools cannot mark the account live, and the browser is not given either token.

The operator routes the page uses are demo proxies. The server attaches the operator token. View source does not contain it.

## What the tests prove, and what they do not

`pytest` uses a fresh database per test, no API key, and no public network.

The contract and tenant tests hit the API directly. They cover unknown modules, too many admins for the seat count, region mismatch, unpurchased modules, unknown invite emails, replays, the agent `403`, SSO blocking go-live, and writes after live.

The scenario tests start the app and let the agent call it over HTTP on localhost. Contoso's `MODULE_NOT_PURCHASED` has to be the API's response. A fake model that returns that error as a canned string without the HTTP call would be a broken test, and I would not defend it.

The live adapter test stubs the provider and checks that a tool call is parsed. It does not score a hosted model.

If they ask "what is your accuracy?": on the scripted suite, the assertions are exact, so the suite is green or red. I do not turn that into a percentage about a live model. If I have run one live model, I describe that run: which tools it called, whether any call was rejected, and whether its final text claimed the account was live. One run is an anecdote. I label it as one run.

## Questions they will ask

**Why an agent at all, if the API already knows the contract?**
The contract is structured, and a script could provision the happy path with no model. I still want the model in the path because the real instruction is messy. Contoso is the case: a side email asks for Billing. A script that only reads the JSON would ignore that sentence. A model may obey the sentence. The product decision is that obeying it must fail closed at the API, and the trace must show the failure. The agent is the untrusted planner. The API is the policy.

**Why not let the model write SQL if you trust the prompt?**
The prompt is not a security boundary. The next run can say "also turn on Billing." Direct SQL would make that a successful write. The HTTP API is the same door an operator uses, with the same checks and the same audit row.

**Why HTTP inside one process? Why not call a Python function?**
A function call can reach into the repository and skip a check "just for the agent." HTTP makes the agent a client. The import test locks that in: `app.agent` cannot import `app.db` or `app.domain`. One process keeps v1 to one command. Splitting later means changing the base URL, not the tools.

**Why is the fake model scripted if you claim this is an agent?**
The scripted model is how I test the system around the model. It chooses the next tool, including a bad one, and the API and the audit log have to respond. That is the part I can rerun in CI. The live adapter is a second implementation of the same interface. I do not pretend the script is a measurement of GPT or Gemini.

**What if the live model marks the account live in its reply?**
It can say that. It cannot do that. There is no tool for it. `GET` tenant and the checklist read `live_at` and the module rows. I would treat a confident wrong final sentence as a finding, and I would write it down. I would not hide it to make the demo cleaner.

**What if it loops, or calls Billing ten times?**
The step cap is 12. The run ends with the tenant as stored and `stopped_reason: step_limit`. A repeated Billing call keeps returning `422` and does not insert a row. The cap is there so a bad planner cannot run forever.

**What if it invites someone who is not on the contract?**
`422 EMAIL_NOT_ON_CONTRACT`. The checklist wants the invited set to equal the contract admin set, so an extra successful invite would also block go-live. In v1 the extra invite never succeeds, because unknown emails are rejected before the seat cap.

**Where does the seat cap live, then?**
Contract intake rejects `admins.length > seats` with `CONTRACT_SEAT_CONFLICT`, so a stored contract cannot already be over the cap. `SEAT_CAP` is still enforced in the invite path as a backstop if the number of distinct invites would exceed seats. I unit-test that helper. I say that plainly. I do not claim an HTTP demo where a second legal email trips the cap, because a second email that is not on the contract is `EMAIL_NOT_ON_CONTRACT` first.

**Why derive status instead of storing it?**
A stored status drifts. The agent, a retry, and a rejected module would each need to remember to update it. Deriving it from region, module rows, invite rows, SSO metadata, open tasks, and `live_at` means the page and go-live see the same facts. Go-live still rechecks those facts in the write transaction so a check-then-act gap does not mark a bad tenant live.

**Why SQLite and one static page?**
v1 is a local demo with a strict boundary. SQLite gives me transactions and uniqueness without a second service. The page has no build step. I would not describe this as the production topology. Production would separate the worker from the API, put real authentication in front, and keep the same tool contract.

**Is this RAG?**
No. Nothing is retrieved from a vector index. The contract is a row, fetched by id with `get_contract`. The model is choosing tools against that JSON. If I bolt a document store on later, the contract row still wins over any passage.

**What did you intentionally leave out?**
OAuth, a CRM, a real IdP, SAML parsing, outbound email, payments, and a second deployable. SSO "metadata received" is an operator boolean. I can say what a real IdP integration would add. I do not claim it is in this repo.

**How would you productionize it?**
Keep the tool list and the error codes. Replace the local bearers with a real identity provider and short-lived credentials for the agent. Run the API and the worker as two processes. Store the audit log where an implementer can search it. Add a human approval on any tool that expands what the customer paid for, which this version already refuses automatically. Evaluate live runs as traces against the same assertions the fake suite uses: exact module set, exact admins, not live until the operator route. I would not fine-tune a model for v1. The failures I care about are rejected or accepted by the API, and that signal is already structured.

## How this sits next to the rest of your work

You can connect it to work you have actually done, without calling Fieldbase a work project.

If they know the ledger or the invoice platform: the same habits show up here. The write is transactional. A retry returns the original result instead of a second effect. The interesting state is derived or constrained, not updated from a client's word. Go-live is the agent-shaped version of that idea: an untrusted caller proposes a change, and the API either replays, rejects, or commits.

If they are hiring for implementation, support, or a B2B product team: the user is the implementation consultant, the source of truth is the signed contract, and the failure you demo is a commercial one, a module the customer did not buy.

If they are hiring for agents or a platform team: the design is a tool loop, a role split, an audit row per call, a step limit, and a CI suite that does not need a model key. The hosted model is swappable behind one interface.

## Phrases that get you in trouble

| Leave this out | Say this instead |
|---|---|
| "The agent cannot be wrong." | "The agent can request the wrong module. The API rejects it, and the trace keeps the 422." |
| "It uses AI to decide when the customer is live." | "A person marks the account live. The agent has no tool for that." |
| "I evaluated the model at N percent." | "The scripted suite asserts exact rows. A live run, if I did one, I describe as a single trace." |
| "Production SSO and OAuth." | "Local role tokens, and SSO metadata is a boolean the operator records." |
| "Northwind is a customer I onboarded." | "Northwind is a fixture. The emails are .example." |
| "The model writes the database." | "The model picks a tool. The admin API writes SQLite." |

## If you have not finished a piece yet

Say which prompt in `prompts.md` is done. A finished admin API plus a scripted Contoso trace is already a coherent interview. Do not describe the page, the live adapter, or a model score you have not run.

## After a live run

Fill `docs/09-demo-and-resume.md` first. Then you can add two sentences to the two-minute answer:

I pointed the same loop at [model id] for [scenario]. It called [tools]. The API returned [codes, or none]. The closing text [did or did not] claim the account was live. Token usage was [numbers or not reported].

Stop there. Do not generalize one trace into "the model is reliable."
