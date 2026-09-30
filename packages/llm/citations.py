import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    source_number: int


_CITATION_PATTERN = re.compile(
    r"\[Source\s+(\d+)\]",
    re.IGNORECASE,
)


def extract_citations(text: str) -> list[Citation]:
    citations: list[Citation] = []

    seen: set[int] = set()

    for match in _CITATION_PATTERN.finditer(text):
        source_number = int(match.group(1))

        if source_number in seen:
            continue

        seen.add(source_number)

        citations.append(
            Citation(
                source_number=source_number,
            )
        )

    return citations