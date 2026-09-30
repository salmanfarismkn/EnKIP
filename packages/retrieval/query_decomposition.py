from dataclasses import dataclass


@dataclass(frozen=True)
class SubQuery:
    query: str
    purpose: str


@dataclass(frozen=True)
class DecomposedQuery:
    original_query: str
    sub_queries: list[SubQuery]