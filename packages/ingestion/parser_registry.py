from .parser import DocumentParser
from .pdf_parser import PdfParser
from .text_parser import TextParser


class ParserRegistry:
    def __init__(self, max_pdf_pages: int = 1_000) -> None:
        self._parsers: list[DocumentParser] = [
            PdfParser(max_pages=max_pdf_pages),
            TextParser(),
        ]

    def get_parser(
        self,
        mime_type: str,
    ) -> DocumentParser:

        for parser in self._parsers:
            if parser.supports(mime_type):
                return parser

        raise ValueError(
            f"No parser available for MIME type: {mime_type}"
        )