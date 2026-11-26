# Coding Agent Instructions

## Scope and workflow

- Read `SPEC.md` and `API_CONTRACT.md` before implementing. Use `BUILD_PLAN.md` to select tasks and track progress.
- Build only the agreed scope. Do not implement deferred features or introduce new dependencies, infrastructure or architectural patterns without a clear need.
- Keep frontend and backend aligned with the API contract. Record deliberate changes in the relevant documents.
- Mark build-plan tasks complete only after verifying their acceptance criteria. Report blockers and incomplete work honestly.

## Code quality

- Prefer simple, explicit, human-readable code over clever or overly generic solutions. Follow existing conventions and use descriptive names.
- Keep functions and classes focused. Use object-oriented design where it improves encapsulation, separation of concerns and testability; do not force inheritance or abstractions.
- Preserve the layered architecture: API handlers handle HTTP, services own business logic, repositories handle persistence, and agent tools call services. Avoid duplicating business logic in prompts or UI code.
- Use type hints and Pydantic schemas at boundaries. Handle errors explicitly, return meaningful responses and log failures without exposing secrets.
- Write comments to explain non-obvious decisions, not obvious code. Avoid dead code, speculative extensibility and unnecessary boilerplate.

## Correctness and safety

- Enforce customer ownership, business rules and approval requirements in backend code, never solely in LLM instructions or the frontend.
- Keep state-changing operations idempotent. Confirmation cards must reflect validated backend data. Keep knowledge articles and their embeddings consistent through atomic database updates.
- Never commit credentials or expose them to the frontend. Use fictional demo data and keep tests isolated from the demo database.

## Verification and delivery

- Test critical behavior with focused tests and the agreed agent evaluation cases. Use LangSmith traces to investigate agent failures.
- Prefer a working end-to-end application over extra features or polish. Do not add elaborate testing infrastructure or chase arbitrary coverage targets.
- Keep the README, API documentation, architecture diagram, ER diagram, seed instructions and decision record consistent with the actual implementation.
- Never claim a feature works, a test passes or an evaluation succeeded without verification. Document remaining limitations and deferred improvements clearly.
