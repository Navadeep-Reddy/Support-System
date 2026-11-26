from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.seed_data import seed_demo_data
from support_agent.core.config import get_settings
from support_agent.core.database import get_db_session
from support_agent.core.schema import initialize_schema
from support_agent.main import app
from support_agent.models import Customer


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    seed_demo_data(engine)
    factory = sessionmaker(bind=engine)

    def test_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = test_session
    # Avoid the app lifespan, which connects to the configured demo database.
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def test_login_switch_logout_and_cookie(client: TestClient) -> None:
    assert client.get("/me").status_code == 401
    response = client.get("/customers")
    assert response.status_code == 200
    customers = response.json()["items"]
    assert {customer["handle"] for customer in customers} == {
        "alex",
        "taylor",
        "maya",
        "jordan",
        "riley",
        "morgan",
    }
    response = client.post("/sessions", json={"customer_id": customers[0]["id"]})
    assert response.json() == customers[0]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/me").json() == customers[0]
    switched = client.post("/sessions", json={"customer_id": customers[1]["id"]})
    assert switched.json() == customers[1]
    assert client.get("/me").json() == customers[1]
    assert client.delete("/sessions/current").status_code == 204
    assert client.delete("/sessions/current").status_code == 204
    assert client.get("/me").status_code == 401


def test_any_stored_customer_can_be_selected(client: TestClient) -> None:
    engine = create_engine(get_settings().test_database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with sessionmaker(bind=connection)() as session:
            customer = Customer(id=uuid4(), handle=f"customer-{uuid4()}", display_name="Jordan")
            session.add(customer)
            session.flush()

            def customer_session():
                yield session

            app.dependency_overrides[get_db_session] = customer_session
            response = client.post("/sessions", json={"customer_id": str(customer.id)})
            assert response.status_code == 200
            assert client.get("/me").json()["display_name"] == "Jordan"
        transaction.rollback()
    engine.dispose()


def test_invalid_login_tampered_cookie_and_cors(client: TestClient) -> None:
    assert client.post("/sessions", json={"customer_id": str(uuid4())}).status_code == 404
    invalid = client.post("/sessions", json={"customer_id": str(uuid4()), "admin": True})
    assert invalid.status_code == 422
    client.cookies.set(get_settings().session_cookie_name, "invalid.signature")
    assert client.get("/me").status_code == 401
    response = client.options(
        "/sessions",
        headers={
            "Origin": get_settings().frontend_origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == get_settings().frontend_origin
    assert response.headers["access-control-allow-credentials"] == "true"
    response = client.options(
        "/sessions",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers
