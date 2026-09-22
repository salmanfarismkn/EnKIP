from .models import ParsedDocument, ParsedSection


class TextParser:
    _SUPPORTED_TYPES = {
        "text/plain",
        "text/markdown",
    }

    def supports(self, mime_type: str) -> bool:
        return mime_type in self._SUPPORTED_TYPES

    def parse(
        self,
        content: bytes,
        filename: str,
    ) -> ParsedDocument:
        text = content.decode("utf-8")

        return ParsedDocument(
            title=filename,
            mime_type="text/plain",
            sections=[
                ParsedSection(
                    title=None,
                    text=text,
                )
            ],
        )