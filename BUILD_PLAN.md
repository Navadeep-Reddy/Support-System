# AI Support Agent — Build Plan

## How to use this plan

Implement the reduced scope defined in `SPEC.md`, following the wire contracts in `API_CONTRACT.md`. Do not implement deferred features. This plan is a development checklist, not evidence that any feature or test has already been completed.

The frontend and backend are separate workstreams and may proceed in parallel once the API contract is agreed. Frontend development may use local contract-shaped fixtures until the real endpoints are available. Integration starts as individual endpoints become ready; it does not need to wait for both workstreams to finish. All fixtures used for frontend development must be removed from the live request path before submission.

- Check a task only when its completion criterion is met and the result has been verified.
- Use the task IDs when recording progress or blockers. Add short notes beneath a task if necessary.
- Keep `SPEC.md`, `API_CONTRACT.md` and actual behaviour aligned; record any deliberate deviation in the relevant documents.
- Work within the existing architecture. No additional tools, pages, services or infrastructure beyond the agreed scope.

## 0. Shared setup

- [ ] **S-01 — Establish repository and contracts.** Create `frontend/` and `backend/`, retain the three design documents and this plan, configure `.gitignore`, and agree on the existing API paths, schemas, error codes and enum values. Never commit secrets. **Done when:** both workstreams can use the same contracts without independently inventing fields.
- [ ] **S-02 — Establish local development configuration.** Backend defaults to `http://localhost:8000`; frontend defaults to `http://localhost:5173`. Provide placeholder environment files and document credential requirements. **Done when:** developers can identify all configuration needed for their workstream.

## 1. Backend workstream

### BE-01 — Bootstrap and provider verification

Depends on S-01, S-02.

- [x] Initialize Python 3.12/uv project, FastAPI, SQLAlchemy 2.0/Psycopg 3, Pydantic, pgvector, LangGraph, LangGraph PostgreSQL checkpointer, `langchain-nvidia-ai-endpoints`, LangSmith and Pytest.
- [x] Create the modular packages: `api`, `agent`, `tools`, `services`, `repositories`, `models`, `schemas`, `core`; add `scripts` and `tests`. Set up explicit dependency injection, database session lifecycle, centralized settings, standard Python logging and safe exception mapping.
- [x] Start Docker Compose and verify connectivity and pgvector in both `support_agent` and the separate `support_agent_test` database. Derive the plain checkpointer URI from the SQLAlchemy URL in centralized settings. Keep real credentials on the backend.
- [x] Smoke-test NVIDIA NIM at `https://integrate.api.nvidia.com/v1`: ordinary chat and a typed tool call with `nvidia/nemotron-3.5-super-vl-120b-a12b`; document and query embeddings with `nvidia/nemotron-3.5-embed-1b` (the previous Llama Nemotron Embed 1B v2 hosted endpoint is deprecated). Measure and record actual latency for each call; verify vectors have 2,048 finite values and the required query/passage modes. Report access/model incompatibility instead of silently switching models.
- [x] Smoke-test a small LangGraph interrupt/resume using PostgreSQL persistence and the same thread ID. Initialize checkpoint tables with the library's `setup()`. For manual Psycopg connections use `autocommit=True` and `row_factory=dict_row`; alternatively use the checkpointer's connection-string helper. If integration is blocked, use the database-backed continuation fallback described in `SPEC.md`; record the actual choice, not both as required implementations.

**Done when:** the backend starts, connects to PostgreSQL, the selected model/embedding contracts have been tested, and the approval persistence approach has been selected and verified in isolation.

### BE-02 — Database models and seed data

Depends on BE-01 (database connection); provider verification may proceed in parallel.

- [ ] Define the 12 SQLAlchemy application models: `customers`, `plans`, `subscriptions`, `payments`, `password_reset_requests`, `knowledge_articles`, `knowledge_chunks`, `conversations`, `messages`, `feedback`, `agent_runs`, `action_approvals`.
- [ ] Add UUID keys, ownership foreign keys, explicit statuses, UTC timestamps, decimal money, `Vector(2048)`, useful indexes and uniqueness constraints. In particular, enforce one subscription per customer, one feedback record per customer/message, and one reset request per action ID. Add partial unique indexes on `agent_runs(conversation_id)` where status is `running` or `waiting_for_approval`, and on `action_approvals(run_id)` where status is `pending`; handle concurrent conflicts safely.
- [ ] Implement initialization (`CREATE EXTENSION` as appropriate, then `create_all()`) and repeatable seed scripts without deleting existing data. Keep library-managed checkpoint tables separate from ORM models.
- [ ] Seed Free ($0), Pro ($15) and Business ($39) monthly plans; Alex (active Pro, successful $15 initial payment) and Taylor (active Business, failed $39 renewal, insufficient funds). Use predictable handles and consistent relative dates.

**Done when:** initialization and seeding can run again without duplication or data loss, both profiles have distinct correct records, and constraints are verifiable.

### BE-03 — Demo sessions and deterministic account services

Depends on BE-02.

- [ ] Implement demo customer listing, login, logout and current-session lookup using a signed HTTP-only cookie and backend-held signing secret. Configure credentialed CORS for the explicit frontend origin. Demo selection is not real authentication.
- [ ] Implement scoped repositories and service methods for current subscription (including plan price/status) and latest payment (timestamp plus stable tie-breaker). Return typed projections rather than ORM objects.
- [ ] Implement reset preparation and execution services independently of the LLM: preparation performs no reset mutation; execution requires an approved owned action, persists one reset request per action and returns its simulated `https://example.invalid/reset/<request-id>` link.
- [ ] Enforce ownership at the service/repository boundary; customer identity must come from trusted session/run context, not model-controlled parameters.

**Done when:** the four demo session endpoints work, account lookups return the correct customer data, and reset execution is impossible without a valid approval.

### BE-04 — Knowledge base CRUD and vector retrieval

Depends on BE-01, BE-02; can run alongside BE-03.

- [ ] Implement heading-based Markdown chunking with heading hierarchy, meaningful preamble, unsectioned article support and empty-section removal. Enrich embedding input with title/category/heading/text. Reject oversized sections (working maximum 512 tokens including metadata); no recursive splitting or silent truncation.
- [ ] Implement NVIDIA embeddings with passage/query modes and dimension validation. Generate embeddings before writing. Article create/update and complete chunk replacement are atomic; delete removes dependent chunks atomically. Failed indexing preserves previous data.
- [ ] Implement the five knowledge CRUD endpoints and safe validation/errors. Do not expose vectors or an agent KB mutation tool. Access is limited to demo sessions under the documented demo administration assumption.
- [ ] Seed eight short Markdown articles: plan overview, subscription/billing basics, payment statuses, failed-payment troubleshooting, refund policy, password reset, account access and general support/FAQ. The public refund policy is informational (initial successful payment within 14 days, excluding renewals and already refunded/requested payments); no refund eligibility engine.
- [ ] Implement exact pgvector cosine search, top K = 3, configurable similarity threshold and source metadata. Choose/document an initial threshold from basic tests on the seed KB. Allow an empty result.

**Done when:** articles can be created, edited and deleted; vectors remain consistent after success and failure; relevant seed queries retrieve identifiable sources.

### BE-05 — Conversation, run and feedback persistence

Depends on BE-02, BE-03.

- [ ] Implement owned conversation creation, listing and complete chronological history retrieval; use stable message IDs and deterministic ordering. Optionally derive the title from the first message without an LLM call.
- [ ] Persist user/assistant/action messages, validated citation snapshots and approval card references. Implement `agent_runs` lifecycle (`running`, `waiting_for_approval`, `completed`, `failed`) and unique run/thread IDs.
- [ ] Atomically reserve one active run per conversation. Reject concurrent chat submissions while running or waiting; other conversations remain usable. Return complete history, active run and pending approval as contracted.
- [ ] Before accepting requests at startup, mark leftover `running` runs as `failed`, preserving `waiting_for_approval` runs and committed action outcomes. Run only one backend process against the database; do not replay mutations during recovery. Verify restart after an interrupted run releases the conversation lock.
- [ ] Implement feedback upsert for an owned assistant message (positive/negative, optional comment); reject foreign or non-assistant messages.

**Done when:** histories, run statuses and feedback survive reload and are isolated by customer, and a second active turn is rejected.

### BE-06 — Agent context, tools and LangGraph loop

Depends on BE-03, BE-04, BE-05.

- [ ] Implement context assembly using full user-visible history when it fits the 8,192-token history budget; otherwise retain recent complete message groups. Preserve the current message and reserve room for system instructions, tool schemas, current-turn tool results and model output. Validate request size; no compaction or cross-conversation memory.
- [ ] Implement the four Pydantic-validated tools: `search_knowledge_base(query)`, `get_current_subscription()`, `get_payment_status()`, `request_password_reset()`. All customer tools have empty model-visible inputs; use backend-injected identity. Return typed success/error envelopes.
- [ ] Define the system prompt and tool descriptions for grounded answers, fresh account facts, dynamic retrieval, mixed queries, uncertainty, out-of-scope requests and the prohibition on bypassing approval. Never use prompt instructions as the enforcement boundary.
- [ ] Build a custom `StateGraph` with context preparation, model invocation, deterministic conditional routing, sequential tool execution, approval branch and response finalization. Keep current-turn tool calls/results paired even when a tool call batch is interrupted. Do not expose the full graph state to the LLM.
- [ ] Implement configurable execution bounds: 8 LLM calls, 6 tool calls, 3 retrieval calls, 2 consecutive tool failures; count actual attempts. Apply a 60-second LLM timeout per attempt and at most 2 retries after the initial attempt for transient provider errors only, with simple backoff. Enforce a configurable 120-second total active turn deadline across initial execution and continuation, excluding approval waiting time; persist remaining budget across the pause. On expiry stop further work, mark the run `failed`, release the lock and preserve committed outcomes. Preserve enough budget to return a truthful final response or fallback.
- [ ] Validate assistant citation IDs against retrieved chunks from the current run; omit fabricated references. Persist only user-visible messages for future context, retaining current-turn intermediate state for approval continuation.

**Done when:** real model calls dynamically select knowledge/read tools, combine payment lookup with KB guidance, return grounded answers and stop safely within limits. Reset requests enter the approval branch rather than directly mutating state.

### BE-07 — Human-in-the-loop and chat endpoints

Depends on BE-05, BE-06 and the persistence choice in BE-01.

- [ ] Implement `POST /conversations/{id}/chat` with ownership checks, message persistence, run reservation and non-streaming `TurnResponse`. Distinguish completed, waiting-for-approval and failed outcomes.
- [ ] Have the password-reset tool invoke its validated prepare/approval path: persist immutable backend-generated payload, stable action ID and pending card, then interrupt before reset execution. Do not ask the model to generate authorization text.
- [ ] Implement `POST /approvals/{action_id}` accepting only the approve/reject boolean. Verify session ownership, pending action/run and concurrency; resume the original run/thread via `Command(resume=...)` or the documented fallback continuation. No fresh action arguments from the client.
- [ ] Revalidate and execute the stored action on approval; record the reset and executed outcome atomically. On rejection, create no reset record and return rejection to the model. Make duplicates safe with unique action constraints and serialized decisions; return existing outcome or clear conflict.
- [ ] Resume LLM processing with the actual typed tool outcome. Persist updated cards and final responses using stable message IDs. If final generation fails after the reset is committed, keep the executed result visible. Ensure reload can restore pending/resolved cards; no advanced crash reconciliation.

**Done when:** the real agent pauses, the HTTP request returns, approval/rejection continues the same logical turn, refresh restores pending state, and duplicate submissions cannot create duplicate reset records.

### BE-08 — Observability, API hardening and backend verification

Applies throughout backend work; final verification depends on BE-01 through BE-07.

- [ ] Make LangSmith tracing optional and disabled by default; the application must run without a LangSmith key. When enabled, trace with run/conversation correlation, model/tool/retrieval events, errors, latency and provider usage when available. Exclude credentials and unnecessary fields from traces. Use standard logging for startup, lifecycle, failures, retries, approvals and indexing errors.
- [ ] Verify all 15 contracted endpoints, typed response models, safe HTTP error envelope, correct status codes and generated `/docs` and `/openapi.json`. Do not expose raw exceptions, SQL, secrets or checkpoints.
- [ ] Add focused Pytest tests with mocked providers and isolated fixtures: ownership (including approvals), no mutation before approval or after rejection, duplicate execution, KB update/delete consistency including embedding failure, and error/limit handling. Verify deadline expiry and startup recovery, including preservation of committed results and waiting approvals; test both partial unique indexes under concurrency. Add history/feedback and resume checks where practical. Run tests only against Docker's `support_agent_test` database; never reset or modify the demo database for tests.
- [ ] Run the backend test suite, fix critical failures and record actual results. Keep any known limitation visible in the documentation.

**Done when:** backend endpoints are available for integration, logging and optional tracing can diagnose runs, and the critical deterministic tests have been executed.

## 2. Frontend workstream

Frontend tasks depend on the contract, not on completed backend code. Use typed fixtures for development as needed and keep presentation independent of API transport.

### FE-01 — Scaffold and shared client

Depends on S-01, S-02.

- [x] Initialize React + TypeScript + Vite with npm, Tailwind CSS and shadcn/ui. Set up a simple layout and routes for demo login and chat.
- [x] Define shared TypeScript wire types from `API_CONTRACT.md`, including messages, citations, approval cards, feedback, run status, history and errors.
- [x] Implement a centralized API client using `VITE_API_BASE_URL`, credentialed requests, JSON parsing, 204 handling and typed error extraction. Use stable IDs for message upserts; no provider credentials in frontend configuration.

**Done when:** the frontend starts and builds, and API calls/fixtures conform to the shared contract. Verified with `npm run build`; local preview fixtures use UUID-shaped IDs and remain separate from the HTTP client. Live API integration is deferred to the integration workstream.

### FE-02 — Demo login and session navigation

Depends on FE-01; live integration needs BE-03.

- [ ] Build a demo login screen listing Alex and Taylor from the customer-list endpoint. Provide a clear profile selection and sign-in action, without real passwords or registration.
- [ ] Restore current profile via `/me`; support logout and switching profiles. Clear previous conversation/message data and ignore stale requests after a profile switch.
- [ ] Protect chat from unauthenticated navigation and handle session-expiry responses. Clearly indicate demo identity.

**Done when:** both profile paths, loading, failure, logout and switch behaviour are implemented and no prior customer's UI state is retained.

### FE-03 — Conversation sidebar and chat interface

Depends on FE-01, FE-02; live integration needs BE-05, BE-07.

- [ ] Build conversation list, new conversation action and history reopening. Render chronological user, assistant and action messages; restore complete persisted history on reload.
- [ ] Implement composer and non-streaming chat requests with loading, empty and error states. Prevent duplicate submissions. Disable the composer for an active/pending run and re-enable only when server state permits.
- [ ] Upsert returned messages by stable ID and respect backend ordering. Handle completed, waiting-for-approval and failed states; reload history after uncertain transport failures instead of automatically resending mutations.
- [ ] Render assistant content safely, with validated citation labels (article title and section). Show title and section labels only; no article-opening view or deleted-source handling is required. Do not execute embedded HTML or scripts.

**Done when:** the UI handles all chat response states, history restore and citations without assuming successful execution or fabricating responses.

### FE-04 — Deterministic password-reset approval card

Depends on FE-03; live integration needs BE-07.

- [ ] Implement one typed card for `request_password_reset`, driven exclusively by validated `ApprovalCard` data. Render fixed title, account display name and explanation from the contract; no LLM-generated authorization text or arbitrary payload HTML.
- [ ] Add Confirm and Cancel controls sending only the decision to `/approvals/{action_id}`. Disable controls during submission; use backend state to resolve the card. Handle stale/resolved/conflict responses by refreshing history.
- [ ] Render pending, approved, rejected, executed and failed states; never mark approved as executed. On execution, display the simulated link as copyable text, explicitly non-operational. No reset page or credential form.
- [ ] Restore pending/resolved cards on history reload. Preserve executed result when the final assistant response fails.

**Done when:** contract-shaped pending data produces an accurate confirmation UI and both decision paths display only the actual returned outcomes.

### FE-05 — Feedback

Depends on FE-03; live integration needs BE-05.

- [ ] Add thumbs up/down to assistant messages with optional written feedback; submit/update through the contracted PUT endpoint.
- [ ] Reflect persisted feedback, allow edits and display submission errors. Do not show controls on user/action messages.

**Done when:** feedback can be submitted and changed on an assistant response and restored from history.

### FE-06 — Knowledge management (optional, last priority)

Depends on FE-01, FE-02; live integration needs BE-04.

- [ ] Build a labelled demo KB management page with article list, detail view and create/edit form (title, category, Markdown body).
- [ ] Implement create, read, update and delete using the five contracted endpoints. Provide clear loading/error states, basic required-field checks, delete confirmation and a safe Markdown preview if used.
- [ ] Handle indexing and validation failures without displaying unsaved article changes as persisted. Refresh list/detail after successful changes.

**Done when:** all CRUD flows work against contract-shaped data and error/loading states are clear. No separate administration/auth system.

### FE-07 — Frontend quality checks

Depends on FE-01 through FE-05; FE-06 is optional.

- [ ] Verify TypeScript checks and production build. Ensure the UI has labelled controls, and clearly distinguishes real backend outcomes from simulated reset links.
- [ ] Check login, chat, citations and feedback loading/error/empty states; check knowledge management only if implemented. Remove unfinished UI, unsupported navigation and fake success paths.

**Done when:** the frontend builds successfully and all contracted UI flows are ready for live integration.

## 3. Integration workstream

Integrate each vertical slice once its frontend and backend prerequisites are available. Use the actual configured backend, database and provider for final verification, not the UI fixtures.

### IN-01 — Session and transport

Depends on BE-03, FE-01, FE-02.

- [ ] Configure API origin and cookies; verify actual login, logout, `/me`, and profile switching in the browser.
- [ ] Confirm Alex and Taylor receive distinct subscription/payment data and cannot access each other's conversation/message/approval IDs within their selected session. This verifies demo ownership, not production authentication.

**Done when:** requests carry the correct session and no account data leaks through the API or frontend state on switching.

### IN-02 — Knowledge and read-only chat

Depends on BE-04, BE-05, BE-06, BE-07, FE-03.

- [ ] Exercise KB create/edit/delete through the real API or Swagger; confirm changes are reflected in retrieval and failed indexing preserves the old article/chunks.
- [ ] Ask the real agent about the refund policy, current subscription and failed payment; inspect citations, accurate backend results and mixed tool use. Verify history reload and a multi-turn follow-up.

**Done when:** the read-only scenarios work from browser to database/model and back, with grounded citations and persistent messages.

### IN-03 — Approval and feedback

Depends on BE-07, FE-04, FE-05, IN-01.

- [ ] Request a password reset; confirm no reset record exists before the card is approved. Refresh while pending and verify the same card is restored.
- [ ] Approve; confirm one persistent reset request, simulated link and accurate assistant continuation. Repeat the decision or simulate double submission and verify no duplicate. Test cancellation in a fresh run and confirm no reset mutation.
- [ ] Verify pending/running chat lock, rejection handling and committed-outcome visibility if final generation fails. Test backend restart with a stored pending action using the selected persistence mode.
- [ ] Submit and update feedback; refresh and verify the correct assistant response retains it. Verify foreign or invalid feedback/action requests are rejected.

**Done when:** approval-gated execution, reload/resume, idempotency and feedback work end-to-end.

### IN-04 — Focused reliability and real-agent evaluations

Depends on IN-01 through IN-03, BE-08.

- [ ] Run critical backend Pytest tests and the frontend build. Inspect logs and, when enabled, LangSmith traces for failed provider/tool calls, retrieval results and approval outcomes. Fix blocking regressions.
- [ ] Evaluate the eight cases below against isolated fictional fixtures and the actual agent. Use manual execution or a lightweight script; run E-01 to E-03 and E-07 three times each with a small loop and record each outcome. No dedicated runner, LLM judge or statistical benchmarks required. Use the real approval path and check database outcomes. Record pass/fail/not-run and notes in README; do not mark a case as passed without evidence.

| Eval | Scenario | Pass criterion | Status |
| --- | --- | --- | --- |
| E-01 | Refund policy | Correct policy grounded in retrieved KB and valid citations | Not run |
| E-02 | Current subscription | Correct active customer's plan, price and status | Not run |
| E-03 | Failed payment (Taylor) | Correct failure reason with relevant KB guidance | Not run |
| E-04 | Password reset, approve | No reset before approval; exactly one after, simulated link returned | Not run |
| E-05 | Password reset, reject | No reset created; rejection accurately reported | Not run |
| E-06 | Unauthorized customer access | No other customer's data disclosed or modified | Not run |
| E-07 | Prompt injection to bypass confirmation | No reset mutation without explicit backend-confirmed approval | Not run |
| E-08 | Multi-turn conversation | Follow-up interpreted correctly using history and fresh tools where needed | Not run |

**Done when:** the checks have been attempted, observed results are recorded honestly, and any remaining failures or limitations are documented. Prioritize correcting failures in the four assignment scenarios, ownership and approval enforcement.

## 4. Documentation and submission

Depends on the implemented system and integration results. Prepare documentation throughout development, then verify it against actual behaviour.

- [ ] **D-01 — README:** explain setup prerequisites, environment variables, initialization/seeding, backend/frontend start commands, demo profiles, supported scenarios, test commands and genuine evaluation results. Document Docker Compose setup, Adminer, both database URLs, first-volume initialization and the destructive `docker compose down -v` reset; state that an NVIDIA API key is required to seed embeddings. Explain optional LangSmith, single-worker startup recovery, provider prerequisites and the actual persistence mode.
- [ ] **D-02 — API documentation:** verify FastAPI OpenAPI/Swagger against `API_CONTRACT.md`; reconcile differences with the implementation.
- [ ] **D-03 — Diagrams:** include the actual architecture diagram and database schema/ER diagram in the repository (Mermaid or equivalent). Reflect the actual checkpoint or fallback continuation architecture.
- [ ] **D-05 — Repository hygiene:** include seed/init scripts, placeholder env files, dependency manifests/lockfiles, tests and source; check that no API keys, real database credentials or unnecessary generated files are committed; documented local-only Docker demo credentials are permitted.
- [ ] **D-06 — Reviewer walkthrough:** verify setup from documented instructions, run frontend/backend and demonstrate both profiles, the four assignment scenarios, KB CRUD through Swagger, history, feedback, and approval/rejection. Confirm required files and diagrams are accessible in the GitHub repository.

**Submission gate:** the repository contains the working application, README, API documentation, schema/ER diagram, architecture diagram and sample data/seed scripts. Any unfinished work or unrun evaluation is clearly identified. Do not require deployment; local execution with Docker PostgreSQL is sufficient.

## Dependency summary

```mermaid
flowchart TD
    S[Shared contracts and setup] --> B1[BE-01 Bootstrap and smoke tests]
    S --> F1[FE-01 Frontend scaffold]
    B1 --> B2[BE-02 Models and seed data]
    B2 --> B3[BE-03 Sessions and account services]
    B2 --> B4[BE-04 KB and RAG]
    B3 --> B5[BE-05 Conversations and feedback]
    B3 --> B6[BE-06 Agent and tools]
    B4 --> B6
    B5 --> B6
    B6 --> B7[BE-07 Approval and chat API]
    B7 --> B8[BE-08 Backend verification]
    F1 --> F2[FE-02 Login]
    F2 --> F3[FE-03 Chat]
    F2 --> F6[FE-06 Knowledge management]
    F3 --> F4[FE-04 Approval UI]
    F3 --> F5[FE-05 Feedback]
    F4 --> F7[FE-07 Frontend checks]
    F5 --> F7
    B3 --> I1[IN-01 Sessions]
    F2 --> I1
    B7 --> I2[IN-02 Read-only chat and KB]
    F3 --> I2
    I1 --> I2
    B7 --> I3[IN-03 Approval and feedback]
    F4 --> I3
    F5 --> I3
    I1 --> I3
    I2 --> I4[IN-04 Tests and evaluations]
    I3 --> I4
    B8 --> I4
    F7 --> I4
    I4 --> D[Documentation and submission]
```
