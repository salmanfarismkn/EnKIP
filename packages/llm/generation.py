from dataclasses import dataclass
from typing import Protocol

from packages.retrieval.evidence import Evidence


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    evidence: list[Evidence]
    grounded: bool


class AnswerGenerator(Protocol):
    def generate(
        self,
        query: str,
        evidence: list[Evidence],
    ) -> GeneratedAnswer:
        ...