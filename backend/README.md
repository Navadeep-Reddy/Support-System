# Backend

Python 3.12 backend managed with uv. Copy `.env.example` to `.env` in this directory, set `NVIDIA_API_KEY` and replace `SESSION_SECRET`, then install dependencies with `uv sync`. Start the API with `uv run uvicorn support_agent.main:app --reload --app-dir src`.

PostgreSQL checkpointing is the selected approval-resume approach. `scripts/checkpointer_smoke.py` verifies persisted interrupt/resume for approve and reject using `TEST_DATABASE_URL` only. Run it with `PYTHONPATH=src uv run python scripts/checkpointer_smoke.py`. Docker Compose maps container port 5432 to `POSTGRES_PORT` (5432 by default). If another local PostgreSQL service occupies that port, choose a free `POSTGRES_PORT` in the root `.env` and use the same port in both backend database URLs.

The configured NVIDIA chat model is `nvidia/nemotron-3.5-super-vl-120b-a12b` ([NVIDIA model page](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b)); NVIDIA documents tool calling for this model. The configured embedding model is `nvidia/nemotron-3.5-embed-1b`. Its hosted endpoint requires `input_type="passage"` for indexing and `input_type="query"` for retrieval, and returns native 2,048-dimensional vectors. The embedding service validates vector size and finite values and rejects oversized inputs rather than silently truncating them. Stored vectors must be rebuilt if the embedding model changes. NVIDIA marks the previous `nvidia/llama-nemotron-embed-1b-v2` hosted endpoint deprecated. See the model and API links in the root `SPEC.md`.

Initialize the configured application database and seed the fictional plans, demo customers, subscriptions, and payments (both commands are repeatable and do not drop data):

```bash
cd backend
uv run python -m scripts.init_db
uv run python -m scripts.seed_data
```

Seed knowledge articles and their embeddings with `uv run python -m scripts.seed_knowledge` (requires `NVIDIA_API_KEY`). Seed commands use `DATABASE_URL`; tests use `TEST_DATABASE_URL` only. Article sections have a conservative 512-byte UTF-8 limit including embedding metadata.

The NVIDIA API key is required for real model and embedding calls. Automatic LangSmith tracing is wired into FastAPI startup: when `LANGSMITH_TRACING=true` and a LangSmith API key is configured, supported LangChain/LangGraph runs are traced without per-call setup. The embedding service is explicitly traced as well. Tracing remains disabled in the example configuration until opted in; enabling it without `LANGSMITH_API_KEY` is a configuration error.

## Bootstrap smoke-check results

Verified with the configured NVIDIA and LangSmith accounts:

| Check | Result | Observed latency |
| --- | --- | ---: |
| Nemotron 3.5 Super VL chat response | Passed | 4.03 s |
| Typed `get_current_subscription` tool-call proposal | Passed | 0.75 s |
| Nemotron 3.5 Embed passage mode (2,048 finite floats) | Passed | 0.84 s |
| Nemotron 3.5 Embed query mode (2,048 finite floats) | Passed | 0.47 s |
| LangSmith visibility | Two successful model-call traces observed in `aatra-support-agent` | — |
| PostgreSQL/pgvector app and test DB connectivity | Passed; pgvector 0.8.7 in both | — |
| PostgreSQL checkpoint interrupt/resume | Passed for approve and reject, resuming via a new saver connection | — |
| FastAPI startup, PostgreSQL startup probe, and `/health` | Passed | — |
| Safe request-validation and unexpected-error envelopes | Passed | — |

The customer and session endpoints (`GET /customers`, `POST /sessions`, `DELETE /sessions/current`, and `GET /me`) use signed HTTP-only cookies and permit credentialed requests from the configured `FRONTEND_ORIGIN`. Profile selection is not real authentication. Set a unique `SESSION_SECRET` outside source control and enable `SESSION_COOKIE_SECURE` when using HTTPS.

Knowledge search uses exact cosine similarity with an initial threshold of 0.35. A real NVIDIA embedding check against the eight seed articles returned the expected refund, failed-payment, password-reset and plan sources; the plan overview scored 0.367, so this threshold remains provisional.

The account service provides customer-scoped subscription and latest-payment projections. Reset preparation creates no reset request; execution requires an approved action owned by the customer and writes the simulated request and approval result in the caller's transaction. The approval API and its decision integration remain for BE-07.

Conversation history, feedback and run reservation are persisted. Startup marks interrupted running turns as failed while preserving waiting approvals and recorded outcomes; run only one backend process against the database. Chat and approval endpoints remain for BE-07.

The bounded LangGraph agent and typed tools are implemented behind `AgentTurns`; the chat and approval HTTP endpoints remain BE-07. `open_agent_turns()` opens an async PostgreSQL checkpointer and should be retained for the application lifespan. The approval endpoint must validate and record a decision, execute an approved reset transactionally, then call `resume` with the monotonic time at which decision processing began. The graph never trusts a resume command as authorization. The estimated model context budget defaults to 32,768 tokens, including a 4,096-token tool-result reserve and 1,024-token output reserve; `MODEL_CONTEXT_TOKEN_BUDGET` can be adjusted for the deployed endpoint.

A real-model internal service check against temporary test-database data selected knowledge retrieval, subscription lookup, and combined payment/knowledge tools, produced valid citations, and paused normal and adversarial reset requests for approval. Run it with `uv run python -m scripts.check_agent`; it uses NVIDIA calls, seeds test-database account fixtures, and removes its own temporary knowledge articles and conversations. It is not an HTTP or browser end-to-end evaluation. Model output remains nondeterministic: successful grounded mixed-query trials were observed, but a later trial also made an unsupported prediction about a future billing attempt despite the prompt. Further evaluation and mitigation are needed in IN-04. If the model omits citation markers after retrieval, the response labels the retrieved chunks as sources consulted; fabricated IDs are discarded. The eight application evaluation cases remain for IN-04.

The focused backend suite currently passes 56 tests and Ruff checks pass. The observed API timings are a single local smoke run, not performance benchmarks.
