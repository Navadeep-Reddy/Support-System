import os

import pytest
from pydantic import ValidationError

from support_agent.core.config import Settings
from support_agent.core.tracing import configure_langsmith_tracing


def test_tracing_exports_configured_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        langsmith_tracing=True,
        langsmith_api_key="lsv2_test_secret",
        langsmith_project="support-test",
        _env_file=None,
    )

    configure_langsmith_tracing(settings)

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2_test_secret"
    assert os.environ["LANGSMITH_PROJECT"] == "support-test"


def test_uppercase_environment_variables_load_as_documented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_secret")
    monkeypatch.setenv("LANGSMITH_PROJECT", "support-env-test")

    settings = Settings(_env_file=None)

    assert settings.langsmith_tracing is True
    assert settings.langsmith_api_key.get_secret_value() == "lsv2_test_secret"
    assert settings.langsmith_project == "support-env-test"


def test_tracing_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    with pytest.raises(ValidationError, match="LANGSMITH_API_KEY is required"):
        Settings(langsmith_tracing=True, _env_file=None)


def test_disabled_tracing_clears_ambient_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "ambient-key")
    settings = Settings(langsmith_tracing=False, _env_file=None)

    configure_langsmith_tracing(settings)

    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert "LANGSMITH_API_KEY" not in os.environ
