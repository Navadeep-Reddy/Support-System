"""Seed knowledge articles without replacing existing records."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from support_agent.core.database import get_engine
from support_agent.core.schema import initialize_schema
from support_agent.models import KnowledgeArticle
from support_agent.schemas.knowledge import ArticleInput
from support_agent.services.embeddings import EmbeddingService
from support_agent.services.knowledge import KnowledgeService

ARTICLES = (
    (
        "Plan overview",
        "plans",
        "## Monthly plans\nFree costs $0, Pro costs $15, and Business costs $39 per month.",
    ),
    (
        "Subscription and billing",
        "billing",
        "## Billing\nSubscriptions are billed monthly. Your account shows the current plan, "
        "status and billing period.",
    ),
    (
        "Payment statuses",
        "billing",
        "## Statuses\nA payment may be successful, failed, refunded, or have a refund requested.",
    ),
    (
        "Failed payment troubleshooting",
        "billing",
        "## Next steps\nCheck your balance and payment method, then contact your bank or "
        "payment provider. Support cannot retry payments or change payment details.",
    ),
    (
        "Refund policy",
        "billing",
        "## Eligibility\nA successful initial payment may qualify for a refund within 14 days. "
        "Renewals and payments already refunded or requested are excluded.",
    ),
    (
        "Password reset",
        "account",
        "## Reset request\nSupport can prepare a simulated password-reset request. "
        "It requires your confirmation and does not change your password or send an email.",
    ),
    (
        "Account access",
        "account",
        "## Access help\nFor account access issues, request a simulated reset or contact "
        "support for further guidance.",
    ),
    (
        "General support FAQ",
        "support",
        "## Getting help\nAsk support about plans, billing, payment status, refunds, and "
        "account access. Support cannot change your plan or payment method.",
    ),
    ("Free plan", "plans", "## Monthly price\nThe Free plan costs $0 per month."),
    ("Pro plan", "plans", "## Monthly price\nThe Pro plan costs $15 per month."),
    ("Business plan", "plans", "## Monthly price\nThe Business plan costs $39 per month."),
    (
        "Billing period",
        "billing",
        "## Current period\nAsk support for your current subscription billing period.",
    ),
    (
        "Latest payment",
        "billing",
        "## Payment information\nSupport can look up the latest payment and its recorded status.",
    ),
    (
        "Renewal payments",
        "billing",
        "## Renewals\nSubscriptions are billed monthly. "
        "Renewal payments are excluded from the demo refund policy.",
    ),
    (
        "Refund request status",
        "billing",
        "## Existing requests\nPayments already refunded or with a refund requested "
        "are excluded from the demo refund policy.",
    ),
    (
        "Demo account safety",
        "account",
        "## Simulated actions\nThe demo reset link is non-operational. "
        "No password is changed and no email is sent.",
    ),
)


def seed_knowledge(session: Session, embeddings: EmbeddingService) -> None:
    service = KnowledgeService(session, embeddings)
    for title, category, body in ARTICLES:
        if session.scalar(select(KnowledgeArticle.id).where(KnowledgeArticle.title == title)):
            continue
        service.save(ArticleInput(title=title, category=category, body=body))


def main() -> None:
    engine = get_engine()
    initialize_schema(engine)
    with Session(engine) as session:
        seed_knowledge(session, EmbeddingService())
        session.commit()


if __name__ == "__main__":
    main()
