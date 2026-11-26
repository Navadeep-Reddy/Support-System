from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from support_agent.agent.citations import validate_citations
from support_agent.agent.context import ContextError, prepare_context
from support_agent.schemas.account import PaymentData, SubscriptionData
from support_agent.schemas.conversation import MessageData
from support_agent.schemas.knowledge import RetrievedChunk
from support_agent.services.accounts import AccountError
from support_agent.tools.support import SupportTools, tool_definitions


class Accounts:
    def __init__(self):
        self.seen = []

    def current_subscription(self, customer_id):
        self.seen.append(customer_id)
        return SubscriptionData(
            plan="Pro",
            monthly_price=Decimal("15"),
            currency="USD",
            status="active",
            period_start=None,
            period_end=None,
        )

    def latest_payment(self, customer_id):
        self.seen.append(customer_id)
        return PaymentData(
            amount=Decimal("15"),
            currency="USD",
            date=datetime.now(UTC),
            status="succeeded",
            failure_reason=None,
        )


class Knowledge:
    def search(self, query):
        return [
            RetrievedChunk(
                article_id=uuid4(),
                chunk_id=uuid4(),
                article_title="Policy",
                section="Terms",
                category="billing",
                text=query,
                score=0.9,
            )
        ]


def test_tool_inputs_and_injected_identity():
    customer_id = uuid4()
    accounts = Accounts()
    tools = SupportTools(customer_id, accounts, Knowledge())
    assert tools.execute("get_current_subscription", {}).data.plan == "Pro"
    assert tools.execute("get_payment_status", {}).data.amount == Decimal("15")
    assert accounts.seen == [customer_id, customer_id]
    assert (
        tools.execute("get_payment_status", {"customer_id": str(uuid4())}).error.code
        == "INVALID_TOOL_INPUT"
    )
    assert (
        tools.execute("search_knowledge_base", {"query": "  "}).error.code == "INVALID_TOOL_INPUT"
    )
    assert (
        tools.execute("search_knowledge_base", {"query": "refund"}).data.chunks[0].text == "refund"
    )
    assert tools.execute("request_password_reset", {}).data.status == "approval_required"
    assert tools.execute("unknown", {}).error.code == "UNKNOWN_TOOL"
    schemas = {tool.name: tool.args_schema.model_json_schema() for tool in tool_definitions()}
    assert schemas["get_payment_status"]["properties"] == {}
    assert schemas["request_password_reset"]["additionalProperties"] is False


def test_citations_only_keep_current_retrieval():
    chunk = Knowledge().search("refund")[0]
    text, citations = validate_citations(
        f"Policy [source:{chunk.chunk_id}] fake [source:{uuid4()}] bad [source:nope]", [chunk]
    )
    assert text.count("[source:") == 1
    assert [citation.chunk_id for citation in citations] == [chunk.chunk_id]


def test_citations_show_consulted_sources_when_model_omits_markers():
    chunk = Knowledge().search("refund")[0]
    text, citations = validate_citations("The policy is limited.", [chunk])
    assert "Sources consulted:" in text
    assert [citation.chunk_id for citation in citations] == [chunk.chunk_id]
    text, citations = validate_citations("", [chunk])
    assert text == "" and citations == []


def test_tool_error_is_typed():
    accounts = Accounts()

    def missing(customer_id):
        raise AccountError("PAYMENT_NOT_FOUND", "No payment record was found.")

    accounts.latest_payment = missing
    result = SupportTools(uuid4(), accounts, Knowledge()).execute("get_payment_status", {})
    assert result.success is False
    assert result.error.code == "PAYMENT_NOT_FOUND"


def message(role, content):
    return MessageData(
        id=uuid4(),
        conversation_id=uuid4(),
        run_id=uuid4(),
        role=role,
        content=content,
        created_at=datetime.now(UTC),
        citations=[],
        approval=None,
        feedback=None,
    )


def test_context_keeps_recent_whole_groups_and_validates_current():
    history = [
        message("user", "old " * 100),
        message("assistant", "answer " * 100),
        message("user", "recent"),
        message("assistant", "recent answer"),
    ]
    full = prepare_context(history, "now", 1000)
    assert len(full) == 5
    recent = prepare_context(history, "now", 30)
    assert [m.content for m in recent] == ["recent", "recent answer", "now"]
    assert isinstance(recent[0], HumanMessage) and isinstance(recent[1], AIMessage)
    with pytest.raises(ContextError):
        prepare_context([], " ", 30)
    with pytest.raises(ContextError):
        prepare_context([], "long " * 100, 30)
