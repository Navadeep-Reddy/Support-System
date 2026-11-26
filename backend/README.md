# Backend

Python 3.12 backend managed with uv. Copy `.env.example` to `.env` in this directory, set `NVIDIA_API_KEY` and replace `SESSION_SECRET`, then install dependencies with `uv sync`. Start the API with `uv run uvicorn support_agent.main:app --reload --app-dir src`.

PostgreSQL checkpointing is the selected approval-resume approach. `scripts/checkpointer_smoke.py` verifies persisted interrupt/resume for approve and reject using `TEST_DATABASE_URL` only. Run it with `PYTHONPATH=src uv run python scripts/checkpointer_smoke.py`. Docker Compose maps container port 5432 to `POSTGRES_PORT` (5432 by default). If another local PostgreSQL service occupies that port, choose a free `POSTGRES_PORT` in the root `.env` and use the same port in both backend database URLs.

The configured NVIDIA chat model is `nvidia/nemotron-3.5-super-vl-120b-a12b` ([NVIDIA model page](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b)); NVIDIA documents tool calling for this model. The configured embedding model is `nvidia/nemotron-3.5-embed-1b`. Its hosted endpoint requires `input_type="passage"` for indexing and `input_type="query"` for retrieval, and returns native 2,048-dimensional vectors. The embedding service validates vector size and finite values and rejects oversized inputs rather than silently truncating them. Stored vectors must be rebuilt if the embedding model changes. NVIDIA marks the previous `nvidia/llama-nemotron-embed-1b-v2` hosted endpoint deprecated. See the model and API links in the root `SPEC.md`.

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

The focused backend suite currently passes 9 tests; Ruff and Python compilation checks pass. These are provider/bootstrap checks, not the eight application evaluation cases. The observed API timings are a single local smoke run, not performance benchmarks.
