from packages.llm.citations import extract_citations


def test_extract_citations() -> None:
    answer = (
        "Employees must request leave in advance "
        "[Source 1]."
    )

    citations = extract_citations(answer)

    assert len(citations) == 1
    assert citations[0].source_number == 1

def test_duplicate_citations_are_deduplicated() -> None:
    answer = (
        "Leave requires approval [Source 1]. "
        "The manager must approve it [Source 1]."
    )

    citations = extract_citations(answer)

    assert len(citations) == 1

from packages.llm.citation_validator import CitationValidator
from packages.retrieval.evidence import Evidence
from uuid import uuid4


def test_invalid_source_number() -> None:
    evidence = [
        Evidence(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_title="Doc",
            text="Some information.",
            section_title=None,
            page_number=None,
            retrieval_score=1.0,
            rerank_score=1.0,
        ),
        Evidence(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_title="Doc 2",
            text="Other information.",
            section_title=None,
            page_number=None,
            retrieval_score=0.9,
            rerank_score=0.9,
        ),
    ]

    validation = CitationValidator().validate(
        "This is supported by [Source 3].",
        evidence,
    )

    assert not validation.is_valid
    assert validation.invalid_source_numbers == [3]