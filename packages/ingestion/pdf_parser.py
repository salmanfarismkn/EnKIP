from io import BytesIO

from pypdf import PdfReader

from .models import ParsedDocument, ParsedSection


class PdfParser:
    def supports(self, mime_type: str) -> bool:
        return mime_type == "application/pdf"

    def parse(
        self,
        content: bytes,
        filename: str,
    ) -> ParsedDocument:
        reader = PdfReader(BytesIO(content))

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