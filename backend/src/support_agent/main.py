from fastapi import FastAPI

app = FastAPI(
    title="Aatra Support Agent API",
    description="Backend API for the fictional Aatra subscription support demo.",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
