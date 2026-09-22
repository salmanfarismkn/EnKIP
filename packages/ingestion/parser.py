from typing import Protocol

from .models import ParsedDocument


class DocumentParser(Protocol):
    def supports(self, mime_type: str) -> bool:
        ...

    def parse(
        self,
        content: bytes,
        filename: str,
    ) -> ParsedDocument:
        ...