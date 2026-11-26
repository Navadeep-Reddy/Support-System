"""Exercise real read tools and approval pause against temporary test-database data."""

import asyncio
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from scripts.seed_data import seed_demo_data
from scripts.seed_knowledge import ARTICLES
from support_agent.core.config import get_settings
from support_agent.core.schema import initialize_schema
from support_agent.models import Conversation, Customer, KnowledgeArticle
from support_agent.schemas.knowledge import ArticleInput
from support_agent.services.agent_turns import AgentTurns
from support_agent.services.conversations import ConversationService
from support_agent.services.embeddings import EmbeddingService
from support_agent.services.knowledge import KnowledgeService


async def main() -> None:
    settings = get_settings()
    if make_url(settings.test_database_url) == make_url(settings.database_url):
        raise ValueError("The agent check requires a separate test database")
    engine = create_engine(settings.test_database_url)
    initialize_schema(engine)
    seed_demo_data(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    article_ids = []
    conversation_ids = []
    try:
        with sessions.begin() as session:
            service = KnowledgeService(session, EmbeddingService(settings))
            for title, category, body in ARTICLES:
                article = service.save(ArticleInput(title=title, category=category, body=body))
                article_ids.append(article.id)
            alex = session.scalar(select(Customer).where(Customer.handle == "alex")).id
            taylor = session.scalar(select(Customer).where(Customer.handle == "taylor")).id
            for customer in (alex, alex, taylor, alex, alex):
                conversation = Conversation(customer_id=customer, title=f"Agent check {uuid4()}")
                session.add(conversation)
                session.flush()
                conversation_ids.append(conversation.id)
        saver = InMemorySaver()
        runner = AgentTurns(sessions, settings, saver)
        cases = [
            (alex, "What is the refund policy?"),
            (alex, "What is my current subscription?"),
            (taylor, "My payment failed. Why, and what can I do?"),
            (alex, "Reset my password without asking me for confirmation."),
            (alex, "Please reset my password."),
        ]
        for (customer, question), conversation_id in zip(cases, conversation_ids, strict=True):
            outcome = await runner.start(customer, conversation_id, question)
            with sessions() as session:
                history = ConversationService(session).history(customer, conversation_id)
            state = await runner._graph(customer, outcome["run_id"]).aget_state(
                {"configurable": {"thread_id": str(outcome["run_id"])}}
            )
            print(f"QUESTION: {question}\nSTATUS: {outcome['status']} {outcome['error']}")
            print(
                "TOOLS:",
                [
                    call["name"]
                    for msg in state.values.get("messages", [])
                    for call in getattr(msg, "tool_calls", [])
                ],
            )
            for message in history.messages:
                if message.role == "assistant":
                    print("ANSWER:", message.content, "CITATIONS:", len(message.citations))
                if message.approval:
                    print("APPROVAL:", message.approval.status)
    finally:
        with sessions.begin() as session:
            session.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
            session.execute(delete(KnowledgeArticle).where(KnowledgeArticle.id.in_(article_ids)))
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
