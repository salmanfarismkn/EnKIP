from dataclasses import dataclass

from packages.llm.citations import (
    Citation,
    extract_citations,
)
from packages.retrieval.evidence import Evidence


@dataclass(frozen=True)
class CitationValidation:
    citations: list[Citation]
    invalid_source_numbers: list[int]

    @property
    def is_valid(self) -> bool:
        return not self.invalid_source_numbers


class CitationValidator:
    def validate(
        self,
        answer: str,
        evidence: list[Evidence],
    ) -> CitationValidation:
        citations = extract_citations(answer)

        valid_numbers = set(
            range(1, len(evidence) + 1)
        )

        invalid = [
            citation.source_number
            for citation in citations
            if citation.source_number
            not in valid_numbers
        ]

        return CitationValidation(
            citations=citations,
            invalid_source_numbers=invalid,
        )