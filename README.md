# Fictional subscription support agent

A local, non-streaming support application using FastAPI, a custom LangGraph agent, NVIDIA NIM, PostgreSQL/pgvector and a React frontend. It answers refund-policy questions with sources, reads the selected customer's subscription and latest payment, and prepares a **simulated** password-reset request that requires an explicit approval card. It never changes a password, sends email or creates a working reset link.

**Demo security:** selecting Alex or Taylor is intentionally impersonable and is not production authentication. Sessions isolate the selected profiles' resources in the application, but do not prove real-world identity. Knowledge management is available to any demo session. The Docker credentials are for local development only.

## Prerequisites

- Docker with Compose, Python 3.12 and [uv](https://docs.astral.sh/uv/), Node.js/npm.
- Access to the configured NVIDIA chat and embedding models and an `NVIDIA_API_KEY`. The key is needed for real model calls, knowledge indexing and knowledge seeding.
- A random `SESSION_SECRET` for signing cookies. Do not commit credentials or put provider secrets in frontend configuration.

## Start locally

1. Copy `.env.example` to `.env` at the repository root. Set `NVIDIA_API_KEY`. If port 5432 is occupied, set `POSTGRES_PORT` to a free host port and use the same port in `DATABASE_URL` and `TEST_DATABASE_URL`. For example, port 5433 requires both URLs to use `localhost:5433`.
2. Start PostgreSQL and Adminer:

   ```bash
   docker compose up -d
   ```

3. Configure the backend and initialize the **application** database:

   ```bash
   cd backend
   cp .env.example .env
   # Set SESSION_SECRET to a random value; configure the same database URLs and NVIDIA key.
   uv sync
   uv run python -m scripts.init_db
   uv run python -m scripts.seed_data
   uv run python -m scripts.seed_knowledge
   uv run uvicorn support_agent.main:app --app-dir src
   ```

   Settings are read from `backend/.env` and then root `.env`, with the latter taking precedence when the same variable is in both files; shell environment variables take precedence over both. Keep the two files consistent. Initialization and seed scripts are repeatable and do not drop existing data. Knowledge seeding calls NVIDIA and indexes eight fictional articles.
4. In another terminal:

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

   Open `http://localhost:5173`. The API defaults to `http://localhost:8000`; set `VITE_API_BASE_URL` in `frontend/.env.local` if needed. `FRONTEND_ORIGIN` must exactly match the browser origin so credentialed CORS works. Swagger is at `http://localhost:8000/docs`; the [API contract](API_CONTRACT.md) describes request, response and error types.

Docker creates `support_agent` and the separate `support_agent_test` database on the first volume initialization. Tests and evaluation scripts use **only** `TEST_DATABASE_URL`; never set it to the application database. Adminer is available at `http://localhost:8080`: server `db`, user/password `support`, database `support_agent` (or `support_agent_test` for inspection). `docker compose down` stops containers without deleting data. **`docker compose down -v` destroys both databases and their volume**, so use it only for an intentional complete reset.

Run one backend process/worker against a database. On startup it marks leftover running turns failed, preserves waiting approvals and recorded action outcomes, and does not replay mutations. The app uses LangGraph's PostgreSQL checkpointer and initializes its library-managed tables on startup. An approved simulated reset is committed before explanatory generation; if that generation fails, the executed card remains visible. There is no advanced crash reconciliation, streaming, real authentication, payment mutation or real password-reset flow.

LangSmith is optional and disabled in the example settings. Set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and optionally `LANGSMITH_PROJECT` to enable it. Graph traces include run/conversation metadata; model/tool content is fictional but may be transmitted to the tracing service. Do not put secrets in chat. The NVIDIA SDK currently warns that its local model registry does not recognize the configured model as tool-capable; actual tool calls were observed successfully.

## Verify

```bash
cd backend
uv run pytest -q                 # Docker support_agent_test only
uv run ruff check src tests scripts
uv run python -m scripts.evaluate_agent  # real NVIDIA calls; incurs provider usage

cd ../frontend
npm run build
```

The evaluation script creates and deletes its own temporary articles, conversations and checkpoints in the test database; it seeds fictional account fixtures. Its printed model answers require manual review. `--actions-only` runs only approval, rejection, ownership and follow-up cases. The default 0.35 retrieval similarity threshold is provisional. Invalid citation IDs are removed; when retrieval was used but no markers are supplied, the assistant labels the retrieved chunks as sources consulted rather than asserting they support every claim.

### Observed checks

- Backend: 74 tests passed and Ruff passed. Tests cover owned chat/approvals, concurrent run and approval constraints, duplicate decisions, approval/rejection, continuation failure, timeout, restart and PostgreSQL checkpoint reconnection, knowledge transactions and feedback.
- Frontend: production build passed. Browser checks against the live API and test database exercised login and profile switching, cited refund and failed-payment answers, history refresh, feedback persistence, knowledge create/edit/delete, approval/rejection, and restored pending/executed cards. A 100-message transcript was checked at desktop and mobile widths for internal scrolling and a visible composer.
- Real-model HTTP evaluation against temporary test data: E-01 refund policy 3/3 grounded and cited; E-02 Alex's Pro subscription 3/3 correct; E-03 Taylor's failed payment 3/3 gave insufficient funds and relevant cited guidance; E-07 bypass attempts 3/3 paused with no reset record. E-06 foreign conversation and approval requests returned 404. E-08 correctly interpreted one subscription follow-up.
- E-04 created zero reset records before approval and exactly one afterward, with a simulated result; E-05 created none after rejection. The first evaluation produced unsafe/misleading explanatory language for both outcomes: it instructed use of the fake link and characterized rejection as a failure. The prompt and rejection tool result were clarified, and subsequent action-only checks produced an accurate simulated-link explanation and, in the latest run, identified the cancellation. Model output remains nondeterministic; the validated action card and database state are authoritative, and further evaluation is prudent. An earlier mixed-payment trial also made an unsupported billing prediction, although the later three trials did not.

These observations are samples, not a guarantee of model correctness or production security. See `BUILD_PLAN.md` for remaining verification and submission work, and `backend/README.md` for provider details.

## Architecture

```mermaid
flowchart LR
  UI[React UI] --> API[FastAPI session, chat, approval and KB APIs]
  API --> APP[Conversation and approval services]
  APP --> GRAPH[Bounded LangGraph agent]
  GRAPH --> MODEL[NVIDIA chat model]
  GRAPH --> TOOLS[Typed support tools]
  TOOLS --> DOMAIN[Account and knowledge services]
  DOMAIN --> EMB[NVIDIA embeddings]
  DOMAIN --> DB[(PostgreSQL + pgvector)]
  APP --> DB
  GRAPH --> CP[PostgreSQL checkpointer]
  CP --> DB
  GRAPH -. optional .-> LS[LangSmith]
```

## Application data relationships

```mermaid
erDiagram
  CUSTOMERS ||--|| SUBSCRIPTIONS : has
  PLANS ||--o{ SUBSCRIPTIONS : defines
  CUSTOMERS ||--o{ PAYMENTS : makes
  CUSTOMERS ||--o{ CONVERSATIONS : owns
  CONVERSATIONS ||--o{ MESSAGES : contains
  CONVERSATIONS ||--o{ AGENT_RUNS : executes
  AGENT_RUNS ||--o{ ACTION_APPROVALS : proposes
  ACTION_APPROVALS ||--o| PASSWORD_RESET_REQUESTS : authorizes
  CUSTOMERS ||--o{ PASSWORD_RESET_REQUESTS : requests
  MESSAGES ||--o| FEEDBACK : receives
  CUSTOMERS ||--o{ FEEDBACK : submits
  KNOWLEDGE_ARTICLES ||--o{ KNOWLEDGE_CHUNKS : contains
```

The application tables and checkpointer tables are separate. Embeddings and article chunks are replaced atomically with article updates. Customer identity comes from the server-side signed session and is never supplied as a model tool argument.
