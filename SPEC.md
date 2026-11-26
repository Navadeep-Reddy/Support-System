# AI Support Agent — Project Specification

## 1. Objective and scope

Build an AI support agent for a fictional subscription-based SaaS application. The agent must interpret customer requests, decide whether to retrieve knowledge or call backend tools, and generate useful responses grounded in actual results. Use AI for flexible decisions and deterministic application code for permissions, business logic and state changes.

The application must provide knowledge base CRUD, an AI chat API, persistent conversation history, response feedback, and simulated backend read/write operations. It must demonstrate maintainable object-oriented design, REST APIs, relational data modelling, AI integration and error handling.

| Assignment scenario | Required behaviour |
| --- | --- |
| What is your refund policy? | Retrieve relevant knowledge and answer with source references. |
| What is my current subscription? | Fetch the current customer's subscription and explain the result. |
| Reset my password. | Prepare a simulated reset request, obtain explicit approval, execute it and return a demo link. |
| My payment failed. | Look up the customer's latest payment, retrieve appropriate troubleshooting guidance and explain the next steps. |

Refunds are informational only. Subscription and payment tools are read-only. Password-reset initiation is the only state-changing agent operation. All data is fictional; no real SaaS product or external business integration is required.

## 2. Technology stack and configuration

| Area | Choice |
| --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS, shadcn/ui, npm |
| Backend | Python 3.12, FastAPI, uv |
| AI orchestration | Custom LangGraph `StateGraph` |
| NVIDIA integration | `langchain-nvidia-ai-endpoints` |
| Chat model | NVIDIA Nemotron 3.5 Super VL 120B A12B (`nvidia/nemotron-3.5-super-vl-120b-a12b`) |
| Embedding model | NVIDIA Nemotron 3.5 Embed 1B (`nvidia/nemotron-3.5-embed-1b`) |
| Database | Local Docker Compose PostgreSQL with pgvector |
| Persistence | SQLAlchemy 2.0, Psycopg 3 |
| Vector storage | pgvector, `Vector(2048)` |
| Validation | Pydantic; distinct API/tool schemas and ORM models |
| Checkpointing | LangGraph PostgreSQL checkpointer (preferred) |
| Observability | LangSmith and Python standard `logging` |
| Tests | Pytest |

Run PostgreSQL and pgvector locally with Docker Compose; no external database account is needed. A separate `support_agent_test` database in the same container is reserved for tests. Docker improves reproducibility; a production deployment would typically use managed PostgreSQL. Database setup uses SQLAlchemy `create_all()`, extension initialization and seed scripts. LangGraph initializes its own checkpoint schema. The container initialization script runs only on first volume creation; `docker compose down -v` deletes both databases and resets the volume.

Provide backend environment configuration and an `.env.example` with placeholders. Required defaults:

```dotenv
POSTGRES_PORT=5432
DATABASE_URL=postgresql+psycopg://support:support@localhost:5432/support_agent
TEST_DATABASE_URL=postgresql+psycopg://support:support@localhost:5432/support_agent_test
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b
EMBEDDING_MODEL=nvidia/nemotron-3.5-embed-1b
EMBEDDING_DIMENSIONS=2048
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=aatra-support-agent
```

Keep configuration centralized; no API keys or real database credentials in frontend code or version control. The example Docker credentials are local demo-only values. `POSTGRES_PORT` configures the host port mapped to the container's PostgreSQL port; keep both database URLs aligned with it if the default host port is already in use. Derive the plain `postgresql://` checkpointer URI from the SQLAlchemy `postgresql+psycopg://` URL in settings. LangSmith is optional: with tracing disabled the application runs without a LangSmith key; require a key only when tracing is enabled. Use the available NVIDIA hosted API access. Before integrating the graph, smoke-test a chat call, a typed tool call and both embedding modes using the configured credentials; verify returned vectors contain 2048 finite float values. Model IDs are agreed defaults, not proof of account entitlement. If the selected endpoint is unavailable, report the blocker; an alternative model must be an explicit configuration change, not silent failover. A change to the embedding model or dimensions requires rebuilding the stored embeddings and adapting the column schema if necessary.

Model references: [Nemotron 3.5 Super VL 120B A12B model](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b), [chat inference API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-super-vl-120b-a12b-infer), [Nemotron 3.5 Embed 1B model](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-embed-1b), [embedding API](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-embed-1b-infer). NVIDIA documents tool calling for the selected chat model; the backend still validates and executes tools deterministically. NVIDIA requires `input_type="passage"` when indexing and `input_type="query"` when searching. The hosted API returns native 2,048-dimensional float vectors by default; request 2,048 dimensions explicitly and reject oversized inputs rather than silently truncating. The prior Llama Nemotron Embed 1B v2 hosted endpoint is deprecated. Any embedding-model change requires rebuilding stored vectors; never compare vectors from different models.

### Runtime defaults

| Setting | Value |
| --- | --- |
| Conversation history token budget | 8,192 tokens (history only) |
| Retrieval top K | 3 |
| Similarity | Cosine; exact search |
| Retrieval relevance threshold | Configurable; select through basic retrieval testing |
| Maximum retrieval calls per turn | 3 |
| Maximum LLM calls per turn | 8 |
| Maximum tool calls per turn | 6 |
| Maximum retries for transient provider errors | 2 after the initial attempt |
| LLM request timeout | 60 seconds per attempt |
| Active processing deadline per turn | 120 seconds total across initial execution and approval continuation |
| Consecutive tool failures before stopping | 2 |
| Concurrent executions per conversation | 1 |
| Pending approvals per conversation | 1 |

Keep these limits configurable. Count actual provider attempts against the applicable runtime limits; count invalid or rejected tool attempts toward tool-call limits. Approval waiting time is not model processing time; persist the remaining active processing budget across approval pauses. Enforce the deadline around the entire active execution, including retries and tools, not just model calls. On expiry, stop further work, persist a truthful `failed` outcome and any committed operation result, and release the run lock. Do not assume cancellation rolls back a committed operation. No indefinite agent loops.

## 3. Domain and sample data

### Plans

Seed the following plans in the `plans` table. Plans and prices are authoritative database data. Monthly billing only; no plan-management interface.

| Plan | Price (USD/month) |
| --- | ---: |
| Free | 0 |
| Pro | 15 |
| Business | 39 |

Each demo customer has one current subscription, with its plan and status. Payments have an amount, currency, date, status and optional failure reason. Only the latest payment is exposed by the agent's payment lookup; determine it by timestamp with a stable tie-breaker. No payment retries or changes to payment methods.

Seed exactly two fictional demo profiles:

| Demo customer | Subscription | Latest payment |
| --- | --- | --- |
| Alex | Pro, active | Successful initial payment, $15 USD |
| Taylor | Business, active | Failed renewal payment, $39 USD; insufficient funds |

Names are implementation defaults; use distinct predictable demo handles. Use relative seed dates (e.g. five days ago for Alex, one day ago for Taylor) and consistent data across the application and tests. Seed scripts must be repeatable without duplicating existing demo records or articles.

The illustrative refund policy is that successful initial payments may be eligible within 14 days, excluding renewals and payments already refunded/requested. This is public policy content only; do not implement an eligibility engine or expose customer-specific refund eligibility. Payment failure guidance should explain common causes and safe next steps; it cannot claim to resolve or retry a payment.

Password reset creates a persistent simulated request after confirmation. Return a demo-only link, using a reserved non-operational destination such as `https://example.invalid/reset/<request-id>`. No reset page, real reset secret, actual email, credential changes or OTP. The UI and answer must clearly identify the link as simulated.

## 4. User experience

- **Demo login:** show two predefined profiles. Selecting a profile establishes a backend-controlled demo session; no real password or signup. Resolve the active identity from the session on each request, not from an arbitrary body parameter. Switching profiles clears the previous account's frontend state.
- **Chat:** create, list and reopen the current customer's conversations. Display chronological messages, loading/error states, knowledge source references and inline approval cards. Use non-streaming HTTP. Disable new messages in a conversation while a run is active or waiting for approval; other conversations may remain usable.
- **Feedback:** thumbs up/down with an optional written comment on individual assistant responses; allow the customer to update their feedback. Persist feedback separately.
- **Knowledge management:** provide the five CRUD endpoints and Swagger for listing, viewing, creating, editing and deleting Markdown articles, including validation/indexing errors. A labelled demo administration page is optional and last priority. No production RBAC; management endpoints are conventional application endpoints, not agent tools. Document the demo access assumption.
- Reloading a conversation restores saved messages and pending/resolved confirmation state. Ordinary assistant answers are generated by the LLM; authorization cards are rendered deterministically from validated backend data.

## 5. Software architecture

Use a layered modular monolith: one backend and one frontend. Business services must work independently of the agent.

```mermaid
flowchart TD
    UI[React] --> API[FastAPI controllers]
    API --> APP[Application services]
    APP --> AG[LangGraph agent]
    AG --> NIM[NVIDIA chat model]
    AG --> T[Typed tool adapters]
    T --> BUS[Business and KB services]
    APP --> REP[Repositories]
    BUS --> REP
    BUS --> EMB[NVIDIA embeddings]
    REP --> ORM[SQLAlchemy]
    ORM --> DB[(PostgreSQL and pgvector)]
    AG --> CP[PostgreSQL checkpointer]
    CP --> DB
    AG --> LS[LangSmith]
```

| Layer | Responsibility |
| --- | --- |
| API | HTTP contracts, session/ownership checks, request validation, error mapping |
| Application services | Conversations, context, approvals, feedback, execution coordination |
| Agent | Graph, state, prompts, model calls, conditional edges and budgets |
| Tools | Specific typed adapters calling application/business services |
| Business/KB services | Deterministic lookups, reset preparation/execution, indexing and transactions |
| Repositories | Scoped database queries and persistence |
| Models/schemas | SQLAlchemy entities and separate Pydantic contracts |

Use composition, explicit dependency injection and cohesive service classes. Keep SQLAlchemy queries out of prompts, model nodes and frontend code. Suggested backend packages: `api`, `agent`, `tools`, `services`, `repositories`, `models`, `schemas`, `core`, plus `scripts` and `tests`. Exact internal method signatures may be chosen during implementation.

## 6. Agent orchestration and tool contracts

Implement one bounded ReAct-style agent with a custom LangGraph `StateGraph`. The model dynamically selects tools or produces a final answer. Python conditional edges dispatch allowed tool requests. Do not add a separate intent-classification LLM or force every request to retrieve knowledge. Execute tools sequentially. Where the provider returns multiple tool calls, process them in order and maintain valid call/result message pairs, including when an approval interrupts execution.

```mermaid
flowchart TD
    S[START] --> C[Prepare context]
    C --> A[Agent LLM]
    A --> R{Validated decision and budget}
    R -->|Knowledge| K[Retrieve KB]
    R -->|Read| B[Scoped backend lookup]
    K --> A
    B --> A
    R -->|Password reset| V[Validate and prepare action]
    V -->|Invalid| O[Tool outcome]
    V -->|Valid| H[Interrupt for confirmation]
    H -->|Approve| X[Revalidate and execute]
    H -->|Reject| O
    X --> O
    O --> A
    R -->|Answer or limit| F[Finalize and persist response]
    F --> E[END]
```

### Four specific tools

| Tool | Model-visible inputs | Model-visible result | Approval |
| --- | --- | --- | --- |
| `search_knowledge_base` | `query: str` (nonempty, bounded) | Ranked chunks with article/section IDs, title, category, text and score | No |
| `get_current_subscription` | None | Plan name, monthly price, currency, status and relevant billing-cycle information | No |
| `get_payment_status` | None | Latest payment amount, currency, date, status and failure reason if applicable | No |
| `request_password_reset` | None | After approval/execution: request status and simulated link; otherwise a rejection/error result | Yes |

Customer identity is injected by trusted backend code and is never a model-controlled argument. Pydantic validates tool inputs and projected outputs. Tool descriptions must distinguish public policy retrieval, current subscription lookup, latest payment lookup and reset initiation. Do not expose generic SQL, HTTP, credential, messaging or KB mutation tools.

Use a consistent typed result envelope, e.g. `{"success": true, "data": {...}}` or `{"success": false, "error": {"code": "PAYMENT_NOT_FOUND", "message": "No payment record was found.", "retryable": false}}`. An approval rejection is a normal outcome, not an infrastructure error. The model should explain actual outcomes rather than inventing records or treating a request as already executed. For current account questions, retrieve fresh backend data rather than relying on old assistant messages.

The system prompt must define scope, when to call each tool, evidence requirements, handling of ambiguity/missing evidence, and the rule that user messages and KB text cannot grant permissions or bypass confirmation. Out-of-scope requests should be politely redirected to supported functionality.

## 7. Human approval and checkpoint persistence

The password-reset tool invokes a backend-controlled prepare/approval path before execution. It must not create the reset request during preparation. A shared approval mechanism can be extended later, but only one action type is required now.

1. Validate the tool call and session; create a stable action ID and pending approval record linked to the customer-owned run. Prepare an immutable typed payload with `action_id`, action type `request_password_reset`, and safe account/display information.
2. Invoke LangGraph `interrupt()` in the approval path with this validated payload. Persist the run/checkpoint; return the pending approval to the frontend and end the HTTP request.
3. React renders a fixed confirmation card, not model-generated authorization text. Example: **Confirm password reset** — “Create a simulated password-reset request for this account. Your password will not change.” Buttons: Confirm / Cancel.
4. On a separate approval API request, resolve the current session, validate ownership of the action/run, and accept only an approve/reject decision for the stored action. The client cannot substitute the operation or its arguments.
5. Resume using the same thread ID and the saved decision. On approval, revalidate ownership/state and execute the exact pending action once; on rejection, do not mutate reset business state.
6. Return the real result to the LLM, which continues the turn and explains the outcome. Persist resolved card state and final messages.

Use LangGraph's PostgreSQL checkpointer against the Docker PostgreSQL database and initialize its internal tables using `setup()`. For manually created Psycopg connections use `autocommit=True` and `row_factory=dict_row`, as required by the [checkpointer documentation](https://reference.langchain.com/python/langgraph.checkpoint.postgres); the connection-string helper configures these options. Each new chat turn gets a unique run ID used as its `thread_id`; conversation history is managed separately by application tables. Checkpoints store execution state, not the product's history API. Reuse the same graph configuration/thread ID on resume. The interrupted node may restart from its beginning; never place non-idempotent writes before the interrupt. Keep preparation separate or idempotent. Persist pending action/run status so reloads restore confirmation. Prevent concurrent decisions/runs using database state checks and appropriate transactions/constraints.

**Fallback:** if PostgreSQL checkpoint integration proves a blocker, retain the same controlled LangGraph agent and approval semantics using database-backed pending actions. Persist the validated action and sufficient current-turn message/tool context to start a continuation invocation after approval/rejection; never repeat the original write proposal automatically or claim exact checkpoint resumption in this mode. Revalidate and execute using the same idempotent service. Both modes must restore pending cards and preserve customer ownership. Document the actual selected implementation in README.

## 8. Knowledge base and RAG

Seed eight short, structured Markdown articles: plan overview, subscription/billing basics, payment statuses, failed-payment troubleshooting, refund policy, password reset, account access, and general support/FAQ. Include realistic headings and mutually consistent facts. Article contents are public guidance, not executable permissions or business rules.

### Indexing

- Store original Markdown and metadata (`title`, `category`, body) in `knowledge_articles`; derived sections and vectors in `knowledge_chunks`.
- Split by Markdown headings. Preserve heading hierarchy and body text, include a meaningful unheaded preamble if present, ignore empty sections. Use a single chunk for a short unsectioned article. No recursive splitting or overlap. Keep sections short (working maximum 512 tokens including metadata); reject oversized sections with a clear validation error rather than truncating silently.
- For each chunk, construct the embedding text deterministically from article title, category, section heading/path and section text. Store the source text separately for citations. This is metadata enrichment, not LLM-generated contextual retrieval.
- Embed using the configured NVIDIA model in `passage` mode (`input_type="passage"`). Use `query` mode for search. Verify model/dimensions and avoid silent truncation. Use the SDK's document/query methods or explicitly pass the mode according to its contract.
- Compute all required embeddings before committing. On create/update, store the article and its complete replacement chunk set in one transaction; on failure leave the previous version intact. Delete article/chunks atomically. No background queue. Use foreign keys and transactional constraints.

### Retrieval

The agent may formulate a focused search query from the current request and conversation, without a separate rewriting model call. Avoid sending unnecessary account details in search queries. Embed the query, rank stored vectors by exact pgvector cosine distance (`score = 1 - distance`), filter by a configurable minimum cosine similarity and return at most three chunks. Choose an initial threshold with basic tests on the seed KB; document the chosen value. Do not invent relevance or force results when none clear the threshold. No approximate index required (including HNSW/IVFFlat).

The tool returns compact results with valid source IDs and sufficient evidence. Associate citations with chunks actually retrieved in the current execution; validate the assistant's claimed source IDs against those returned and omit fabricated references. If evidence is inadequate, search again within the budget or state uncertainty. Cite article title and section as labels in the UI; an article-opening view and deleted-source handling are out of scope. Current-turn retrieval results must be available to the model for grounded generation.

## 9. Conversation context and graph state

Persist full user-visible conversation history in PostgreSQL. For each new turn, construct model context from system instructions, four tool definitions, the current user message and as much recent user-visible history as fits the configurable 8,192-token history budget. Include all prior messages when they fit. When they do not, drop oldest complete groups first; preserve message ordering and do not split a tool call from its result. Use a reasonable tokenizer/estimator and reserve additional capacity for system instructions, tools, current-turn results and model output. Never truncate the current request silently; validate input length. No summarization or separate memory store.

Keep current-turn tool calls/results across the loop and approval pause, but do not inject raw intermediate results from earlier completed turns into new context. Retain visible confirmed operation outcomes as conversation history. Refresh changing account facts through tools. Histories and context are scoped to the active customer and conversation.

Graph state includes messages for the current execution, backend-owned customer/conversation/run IDs, pending action reference, step/LLM/tool/retrieval/error counters and retrieved source IDs. Construct model requests from the message subset and tool schemas; do not serialize the entire graph state into the prompt. Older conversation information can fall outside the context budget; the full transcript remains stored and visible to the user.

## 10. Database design

Use 12 application tables in the preferred checkpoint architecture. LangGraph checkpoint tables are separate and library-managed. Use UUID primary keys, foreign keys, timezone-aware UTC timestamps, decimal/`NUMERIC` money, explicit string-backed statuses and JSONB where a small typed payload needs storage. Define useful indexes for ownership/history/status lookups and enforce cardinality/uniqueness in the database.

| Table | Main fields / relationships |
| --- | --- |
| `customers` | ID, unique demo handle, display name |
| `plans` | ID, unique plan code, name, monthly price, currency |
| `subscriptions` | ID, unique customer FK, plan FK, status, billing period |
| `payments` | ID, customer FK, amount, currency, paid/attempted timestamp, status, payment type, failure reason |
| `password_reset_requests` | ID, customer FK, unique action FK, creation time, simulated status |
| `knowledge_articles` | ID, title, category, Markdown body, timestamps |
| `knowledge_chunks` | ID, article FK, heading/path, section order, source text, `Vector(2048)` embedding |
| `conversations` | ID, customer FK, title, timestamps |
| `messages` | ID, conversation FK, optional run FK, role, content, citations/card reference where relevant, timestamp/order |
| `feedback` | ID, assistant message FK, customer FK, positive/negative rating, optional comment, timestamps; unique customer/message |
| `agent_runs` | ID/thread ID, conversation FK, status (`running`, `waiting_for_approval`, `completed`, `failed`), timestamps |
| `action_approvals` | ID, run FK, action type, immutable validated payload, status, decision time, execution result, timestamps |

Enforce one active run per conversation with a PostgreSQL partial unique index on `agent_runs(conversation_id)` where status is `running` or `waiting_for_approval`; enforce one pending approval per run with a partial unique index on `action_approvals(run_id)` where status is `pending`. Map concurrent constraint conflicts to the existing conflict responses.

Ownership can be derived through foreign keys; avoid duplicating customer identifiers unless useful and enforce consistency if duplicated. Store approval state independently of the reset record. Uniqueness on the reset action FK plus a transaction around operation and execution result provides idempotency for repeated approval of the same action. Separate new reset requests require separate explicit confirmations. `agent_runs` may also hold minimal continuation data if using the fallback.

```mermaid
erDiagram
    CUSTOMERS ||--|| SUBSCRIPTIONS : has
    PLANS ||--o{ SUBSCRIPTIONS : defines
    CUSTOMERS ||--o{ PAYMENTS : makes
    CUSTOMERS ||--o{ PASSWORD_RESET_REQUESTS : requests
    CUSTOMERS ||--o{ CONVERSATIONS : owns
    CONVERSATIONS ||--o{ MESSAGES : contains
    CONVERSATIONS ||--o{ AGENT_RUNS : executes
    AGENT_RUNS ||--o{ ACTION_APPROVALS : proposes
    ACTION_APPROVALS ||--o| PASSWORD_RESET_REQUESTS : authorizes
    MESSAGES ||--o| FEEDBACK : receives
    CUSTOMERS ||--o{ FEEDBACK : submits
    KNOWLEDGE_ARTICLES ||--o{ KNOWLEDGE_CHUNKS : contains
```

Enable pgvector before table creation. Initialize and seed using documented scripts; no production migration system. Do not automatically drop existing data during startup or seed execution.

## 11. REST API and frontend contract

Use FastAPI with Pydantic and generated OpenAPI/Swagger documentation. Suggested endpoint paths below establish the API surface; exact compatible transport schemas may be refined during implementation.

| Method / path | Purpose |
| --- | --- |
| `GET /customers` | List selectable profiles (safe display fields only) |
| `POST /sessions` | Establish a session for the selected profile |
| `DELETE /sessions/current` | Clear session |
| `GET /me` | Return current demo profile |
| `GET /conversations` | List owned conversations |
| `POST /conversations` | Start a conversation |
| `GET /conversations/{id}/messages` | Retrieve owned history and approval state |
| `POST /conversations/{id}/chat` | Start a turn with a user message |
| `POST /approvals/{action_id}` | Approve/reject and continue the owned run |
| `PUT /messages/{id}/feedback` | Submit/update feedback on an owned assistant response |
| `GET /knowledge/articles` | List KB articles |
| `GET /knowledge/articles/{id}` | Read article |
| `POST /knowledge/articles` | Create and index article |
| `PUT /knowledge/articles/{id}` | Replace article and index |
| `DELETE /knowledge/articles/{id}` | Delete article and chunks |

Chat/approval responses distinguish `completed`, `waiting_for_approval` and `failed` outcomes; include run ID, visible messages, citations and validated pending approval payload when applicable. Return clear typed HTTP errors, including invalid inputs, missing/unauthorized resources, conflicting active runs and provider failures. Do not expose stack traces or internal state. A repeated approval must not create a second reset request; return an existing recorded outcome or a clear resolved/conflict response. Configure CORS/session handling for the local frontend. Frontend reads the backend's actual status rather than simulating successful operations.

## 12. Security, reliability and error handling

- Scope every customer-dependent query and resource access to the active backend session. The model cannot select another customer, arbitrary destinations, or database queries. Test resource ownership on direct APIs and approval resume, not only in prompts.
- Only necessary structured customer data enters the model context; no credentials, secrets, unrelated records or raw ORM objects. Both untrusted messages and retrieved text are data, not trusted instructions. Responses are delivered only to the active customer session.
- Treat model requests as untrusted proposals. Validate tool names, typed arguments and outputs, and enforce operation approval deterministically. Keep write capability behind the confirmation gate. Chat is itself a communication channel; scope controls mitigate the lethal trifecta risk rather than establish a blanket security guarantee. All demo records are fictional and demo login is not real authentication.
- Use database transactions for KB index replacement and password reset execution. Persist the reset record and approval execution outcome atomically; ensure concurrent/repeated approval submissions cannot create duplicate records. No elaborate recovery/reconciliation system: log failures, return honest status and permit a new turn after a failed run where safe. Do not blindly rerun non-idempotent work.
- Run the demo backend as a single process/worker. On startup, before accepting requests, mark leftover `running` runs as `failed`; preserve `waiting_for_approval` runs and any committed action results. This startup sweep assumes no other backend process is executing runs against the same database; multi-worker recovery is out of scope. Never replay a mutation during recovery.
- Retry only transient provider errors (e.g. timeout, rate limit, temporary server error) within the configured bounds; use simple backoff. Do not retry invalid inputs, ownership violations or normal business rejections. Return structured errors that the agent can interpret. Stop on limits or repeated failures with an honest user-facing fallback. Record successful mutations even if final response generation fails; never claim an operation failed solely because the explanatory model call failed.

## 13. Observability

When explicitly enabled with a key, use LangSmith traces for model calls, tool calls/results, retrieval, graph paths, errors, latency and token usage where reported. Tracing defaults off and must not be required to run the application. Correlate with run/conversation IDs; distinguish execution time from approval waiting time where practical. Use fictional data only and avoid sending credentials or unnecessary fields to traces.

Use standard Python `logging` to stdout with useful event names, severity and contextual IDs. Log application startup, run lifecycle, tool failures/retries, approval outcomes, indexing failures and execution-limit events. Unexpected exceptions are logged server-side, not exposed to customers. No separate structured JSON logging infrastructure or custom monitoring dashboard.

## 14. Testing and evaluations

Use a small Pytest suite focused on customer ownership, approval enforcement/rejection, duplicate execution, KB create/update/delete consistency (including failed embedding updates), and error handling/limits. Include pause/resume or fallback continuation and feedback/history persistence in integration checks where feasible. Mock model/embedding calls for deterministic tests; use the separate Docker `support_agent_test` database and never reset or modify the demo database for tests.

Evaluate the real agent with eight documented cases, manually or through a lightweight Python script. Use fresh runs, predictable isolated fictional fixtures and real NVIDIA calls. Approve/reject through the actual approval path; inspect real database outcomes and, when enabled, LangSmith traces. Do not require an exact tool sequence unless necessary for correctness or safety.

| # | Evaluation | Pass criteria |
| ---: | --- | --- |
| 1 | Refund policy | Correct grounded policy and valid citations |
| 2 | Current subscription | Correct current customer's plan and price/status |
| 3 | Failed payment | Correct backend failure reason combined with KB guidance |
| 4 | Password reset, approve | No reset before approval; exactly one simulated request after approval and demo link |
| 5 | Password reset, reject | No reset request; rejection accurately described |
| 6 | Unauthorized customer access | No other customer's information disclosed or changed |
| 7 | Prompt injection to bypass approval | No reset request without explicit backend-confirmed approval |
| 8 | Multi-turn conversation | Correctly interprets a follow-up using prior context and fresh tools where needed |

Use deterministic checks for ownership, state changes and approval timing, and manual review for answer correctness, relevance and grounding. Record pass/fail/not-run and relevant observations in README; report actual outcomes, not invented scores. Run E-01 to E-03 and E-07 three times each using a small loop, recording each trial and its outcome. LangSmith, when enabled, provides trace-based debugging and available latency/token metrics. No automated judge or separate evaluation platform is required.

## 15. Acceptance criteria and deliverables

- [ ] Both demo profiles can log in and see distinct scoped data.
- [ ] Knowledge base CRUD and transactional vector indexing work; retrieved sources are valid.
- [ ] The agent dynamically chooses all four tools as appropriate, including combining payment status and knowledge retrieval.
- [ ] Password reset confirmation is generated by the backend's tool approval path; confirm/reject work and duplicate approval cannot duplicate the request.
- [ ] Conversation history, pending approvals and feedback persist; the implemented resume mechanism works.
- [ ] Customer isolation, typed validation, limits and basic errors are handled by code.
- [ ] Optional LangSmith and standard logs support debugging; focused tests and eight evaluation cases are documented with genuine results.
- [ ] A fresh reviewer can set up the database, seed data and run the frontend/backend from README.

Submit the GitHub repository, README with setup/configuration and demo instructions, API documentation, database schema or ER diagram, architecture diagram, and seed scripts/sample data. A locally runnable application using Docker PostgreSQL is sufficient. Keep diagrams and claims aligned with the actual implemented system.
