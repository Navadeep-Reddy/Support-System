from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from support_agent.api.errors import register_exception_handlers


def create_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/items/{item_id}")
    def get_item(item_id: int) -> dict[str, int]:
        if item_id == 404:
            raise HTTPException(status_code=404, detail="Item was not found.")
        return {"item_id": item_id}

    @app.get("/unexpected")
    def unexpected() -> None:
        raise RuntimeError("private implementation detail")

    return app


def test_validation_error_uses_contract_envelope() -> None:
    with TestClient(create_test_app()) as client:
        response = client.get("/items/not-an-int")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["retryable"] is False
    assert "input" not in response.json()["details"][0]


def test_unexpected_error_does_not_leak_internal_message() -> None:
    with TestClient(create_test_app(), raise_server_exceptions=False) as client:
        response = client.get("/unexpected")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private implementation detail" not in response.text
