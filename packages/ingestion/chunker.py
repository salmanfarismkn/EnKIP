from dataclasses import dataclass

from .models import ParsedDocument, ParsedSection


@dataclass(frozen=True)
class Chunk:
    text: str
    chunk_index: int
    section_title: str | None
    page_number: int | None
    start_offset: int
    end_offset: int


class DocumentChunker:
    def __init__(
        self,
        max_characters: int = 2000,
        overlap_characters: int = 200,
    ) -> None:
        if max_characters <= 0:
            raise ValueError(
                "max_characters must be greater than zero"
            )

        if overlap_characters < 0:
            raise ValueError(
                "overlap_characters cannot be negative"
            )

        if overlap_characters >= max_characters:
            raise ValueError(
                "overlap_characters must be smaller "
                "than max_characters"
            )

        self._max_characters = max_characters
        self._overlap_characters = overlap_characters

    def chunk(
        self,
        document: ParsedDocument,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []

        for section in document.sections:
            chunks.extend(
                self._chunk_section(
                    section,
                    starting_index=len(chunks),
                )
            )

        return chunks

    def _chunk_section(
        self,
        section: ParsedSection,
        starting_index: int,
    ) -> list[Chunk]:

        text = section.text.strip()

        if not text:
            return []

        chunks: list[Chunk] = []

        start = 0
        chunk_index = starting_index

        while start < len(text):
            end = min(
                start + self._max_characters,
                len(text),
            )

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_index=chunk_index,
                        section_title=section.title,
                        page_number=section.page_number,
                        start_offset=start,
                        end_offset=end,
                    )
                )

                chunk_index += 1

            if end >= len(text):
                break

            start = end - self._overlap_characters

        return chunks