"""Verify PostgreSQL-backed LangGraph interrupt/resume using the isolated test DB."""

from typing import NotRequired, TypedDict
from uuid import uuid4

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy.engine import make_url

from support_agent.core.config import get_settings


class ApprovalState(TypedDict):
    outcome: NotRequired[str]


def build_graph(checkpointer: PostgresSaver, executed: list[str]):
    def approval_node(_state: ApprovalState) -> dict[str, str]:
        decision = interrupt(
            {
                "action_type": "smoke_test",
                "message": "Approve the checkpointer persistence smoke test?",
            }
        )
        outcome = "approved" if decision["approved"] else "rejected"
        if decision["approved"]:
            executed.append(outcome)
        return {"outcome": outcome}

    builder = StateGraph(ApprovalState)
    builder.add_node("approval", approval_node)
    builder.add_edge(START, "approval")
    builder.add_edge("approval", END)
    return builder.compile(checkpointer=checkpointer)


def test_resume(decision: bool) -> None:
    settings = get_settings()
    # Use the dedicated test database; do not create LangGraph tables in the demo DB.
    checkpoint_url = make_url(settings.test_database_url).set(drivername="postgresql")
    checkpoint_uri = checkpoint_url.render_as_string(hide_password=False)
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    executed: list[str] = []

    with PostgresSaver.from_conn_string(checkpoint_uri) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer, executed)
        paused = graph.invoke({}, config)
        interrupts = paused.get("__interrupt__", ())
        assert interrupts, "Graph did not pause at the approval interrupt"
        assert interrupts[0].value["action_type"] == "smoke_test"
        assert not executed, "Operation ran before the approval decision"
        assert checkpointer.get_tuple(config) is not None, "Paused checkpoint was not persisted"

    # Reconnect so resume proves the interrupt state was stored in PostgreSQL.
    with PostgresSaver.from_conn_string(checkpoint_uri) as checkpointer:
        graph = build_graph(checkpointer, executed)
        resumed = graph.invoke(Command(resume={"approved": decision}), config)
        expected = "approved" if decision else "rejected"
        assert resumed["outcome"] == expected
        assert executed == (["approved"] if decision else []), (
            "The approval-gated operation ran at the wrong time or more than once"
        )


def main() -> None:
    test_resume(decision=True)
    test_resume(decision=False)
    print("PostgreSQL LangGraph interrupt/resume passed for approve and reject.")


if __name__ == "__main__":
    main()
