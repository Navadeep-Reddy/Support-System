from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ArticleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=200)
    category: str = Field(max_length=80)
    body: str

    @field_validator("title", "category", "body")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be blank")
        return value


class ArticleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    category: str
    created_at: datetime
    updated_at: datetime


class Article(ArticleSummary):
    body: str


class ArticleList(BaseModel):
    items: list[ArticleSummary]


class RetrievedChunk(BaseModel):
    article_id: UUID
    chunk_id: UUID
    article_title: str
    section: str
    category: str
    text: str
    score: float
