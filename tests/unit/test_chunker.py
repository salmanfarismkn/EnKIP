from packages.ingestion.chunker import DocumentChunker
from packages.ingestion.models import (
    ParsedDocument,
    ParsedSection,
)


def test_document_is_chunked() -> None:
    document = ParsedDocument(
        title="test.txt",
        mime_type="text/plain",
        sections=[
            ParsedSection(
                title="Architecture",
                text=(
                    "A" * 2500
                ),
                page_number=1,
            )
        ],
    )

    chunker = DocumentChunker(
        max_characters=1000,
        overlap_characters=100,
    )

    chunks = chunker.chunk(document)

    assert len(chunks) == 3

    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1
    assert chunks[2].chunk_index == 2

    assert chunks[0].section_title == "Architecture"
    assert chunks[0].page_number == 1