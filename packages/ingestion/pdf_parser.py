from io import BytesIO

from pypdf import PdfReader

from .models import ParsedDocument, ParsedSection


class PdfParser:
    def __init__(self, max_pages: int = 1_000) -> None:
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")
        self._max_pages = max_pages

    def supports(self, mime_type: str) -> bool:
        return mime_type == "application/pdf"

    def parse(
        self,
        content: bytes,
        filename: str,
    ) -> ParsedDocument:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF documents are not supported")
        if len(reader.pages) > self._max_pages:
            raise ValueError(
                f"PDF document exceeds the {self._max_pages}-page limit"
            )

        sections: list[ParsedSection] = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            text = page.extract_text() or ""

            if not text.strip():
                continue

            sections.append(
                ParsedSection(
                    title=None,
                    text=text,
                    page_number=page_number,
                )
            )

        return ParsedDocument(
            title=filename,
            mime_type="application/pdf",
            sections=sections,
        )