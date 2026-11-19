# Refactor: Moving search models into their own file
from typing import Literal

from pydantic import BaseModel, Field, field_validator

class SearchRequest(BaseModel):
    # Change: Normalizing and validating the query
    @field_validator("query")
    @classmethod

    def normalize_query(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Query cannot be empty or whitespace.")

        return value

    query: str = Field(
        ...,
        min_length=1,
        description="Free-text search query (Indonesian or English).",
    )
    max_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        description="Maximum cosine distance allowed for a result (lower = stricter).",
    )

class SearchResult(BaseModel):
    peringkat: int
    skor: float
    judul: str
    penulis: str
    deskripsi: str
    url: str
    date: str

class SearchResponse(BaseModel):
    query: str
    max_threshold: float
    count: int
    results: list[SearchResult]
    status: Literal["full", "list_only", "no_results"]
    ringkasan: str | None = None
    arahan: list[str] = Field(default_factory=list)

class SearchMetadata(BaseModel):
    title: str = Field(..., min_length=1)
    creators: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    date: str = Field(..., min_length=1)