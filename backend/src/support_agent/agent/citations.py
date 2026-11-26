import re
from uuid import UUID

from support_agent.schemas.conversation import Citation
from support_agent.schemas.knowledge import RetrievedChunk

SOURCE_REFERENCE = re.compile(r"\[source:([^\]]+)\]")


def validate_citations(text: str, retrieved: list[RetrievedChunk]) -> tuple[str, list[Citation]]:
    """Remove unsupported references and return snapshots of cited retrieved chunks."""
    sources = {chunk.chunk_id: chunk for chunk in retrieved}
    cited: dict[UUID, Citation] = {}

    def replace(match: re.Match[str]) -> str:
        try:
            chunk_id = UUID(match.group(1))
        except ValueError:
            return ""
        chunk = sources.get(chunk_id)
        if chunk is None:
            return ""
        cited[chunk_id] = Citation(
            article_id=chunk.article_id,
            chunk_id=chunk.chunk_id,
            article_title=chunk.article_title,
            section=chunk.section,
        )
        return f"[source:{chunk_id}]"

    cleaned = SOURCE_REFERENCE.sub(replace, text)
    # If the model used retrieval but omitted explicit markers, expose the sources
    # it consulted without claiming that any particular passage proves the answer.
    if cleaned.strip() and not cited and retrieved:
        for chunk in retrieved:
            cited[chunk.chunk_id] = Citation(
                article_id=chunk.article_id,
                chunk_id=chunk.chunk_id,
                article_title=chunk.article_title,
                section=chunk.section,
            )
        cleaned += "\n\nSources consulted: " + " ".join(
            f"[source:{chunk_id}]" for chunk_id in cited
        )
    return cleaned, list(cited.values())
