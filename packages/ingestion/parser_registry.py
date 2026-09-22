from .parser import DocumentParser
from .pdf_parser import PdfParser
from .text_parser import TextParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[DocumentParser] = [
            PdfParser(),
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