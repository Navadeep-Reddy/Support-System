import os

from support_agent.core.config import Settings


def configure_langsmith_tracing(settings: Settings) -> None:
    """Export centralized settings for LangChain/LangGraph's automatic tracing hooks."""
    os.environ["LANGSMITH_TRACING"] = str(settings.langsmith_tracing).lower()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project

    api_key = settings.langsmith_api_key.get_secret_value()
    if settings.langsmith_tracing:
        # Settings validation guarantees a key is present when tracing is enabled.
        os.environ["LANGSMITH_API_KEY"] = api_key
    else:
        # Never leave an ambient process key able to activate tracing unexpectedly.
        os.environ.pop("LANGSMITH_API_KEY", None)
